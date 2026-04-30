"""
services.py — all business logic for RepoRanker.

Public API:
    analyze_repository(repo_url) -> RepositoryAnalysis
"""

import json
import os
import re
import shutil
import subprocess
import tempfile

import git

from .models import RepositoryAnalysis

GITHUB_URL_RE = re.compile(r"^https://github\.com/[\w.\-]+/[\w.\-]+(\.git)?/?$")

# ---------------------------------------------------------------------------
# Repository cloning
# ---------------------------------------------------------------------------


def clone_repository(repo_url: str) -> str:
    """
    Clone *repo_url* into a fresh temp directory (shallow clone, depth=1).

    Returns the path to the temp directory.
    Raises ValueError for invalid URLs, RuntimeError for clone failures.
    """
    if not GITHUB_URL_RE.match(repo_url):
        raise ValueError(f"Invalid GitHub URL: {repo_url!r}")

    tmpdir = tempfile.mkdtemp(prefix="reporanker_")
    try:
        git.Repo.clone_from(repo_url, tmpdir, depth=1)
    except git.GitCommandError as exc:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise RuntimeError(
            f"Could not clone repository. "
            f"Make sure it is public and the URL is correct. "
            f"(Detail: {exc})"
        ) from exc
    return tmpdir


def _has_python_files(path: str) -> bool:
    """Return True if *path* contains at least one .py file."""
    for _dirpath, _dirs, filenames in os.walk(path):
        if any(f.endswith(".py") for f in filenames):
            return True
    return False


# ---------------------------------------------------------------------------
# Analysis tools
# ---------------------------------------------------------------------------


def run_flake8(path: str) -> dict:
    """
    Run flake8 on *path* and return structured results.

    Return shape::

        {
            "issues": [{"file": str, "line": int, "col": int,
                        "code": str, "message": str}, ...],
            "summary": str,
            "error": str | None,
        }
    """
    try:
        result = subprocess.run(
            [
                "flake8",
                path,
                "--format=%(path)s:%(row)d:%(col)d:%(code)s:%(text)s",
                "--max-line-length=120",
                "--exit-zero",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"issues": [], "summary": "flake8 execution failed", "error": str(exc)}

    issues = []
    for line in result.stdout.splitlines():
        parts = line.split(":", 4)
        if len(parts) >= 5:
            try:
                issues.append(
                    {
                        "file": parts[0].replace(path, "").lstrip("/\\"),
                        "line": int(parts[1]),
                        "col": int(parts[2]),
                        "code": parts[3].strip(),
                        "message": parts[4].strip(),
                    }
                )
            except (ValueError, IndexError):
                continue

    summary = f"{len(issues)} style issue(s) found."
    return {"issues": issues, "summary": summary, "error": None}


def run_bandit(path: str) -> dict:
    """
    Run bandit on *path* and return structured results.

    Return shape::

        {
            "issues": [{"file": str, "line": int, "severity": str,
                        "confidence": str, "message": str}, ...],
            "summary": str,
            "error": str | None,
        }
    """
    try:
        result = subprocess.run(
            ["bandit", "-r", path, "-f", "json", "-q", "--exit-zero"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"issues": [], "summary": "bandit execution failed", "error": str(exc)}

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        stderr = result.stderr[:500] if result.stderr else "no output"
        return {
            "issues": [],
            "summary": "bandit produced no parseable output",
            "error": stderr,
        }

    issues = []
    for item in data.get("results", []):
        issues.append(
            {
                "file": item.get("filename", "").replace(path, "").lstrip("/\\"),
                "line": item.get("line_number", 0),
                "severity": item.get("issue_severity", "UNKNOWN").upper(),
                "confidence": item.get("issue_confidence", "UNKNOWN").upper(),
                "message": item.get("issue_text", ""),
            }
        )

    counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
    for issue in issues:
        sev = issue["severity"]
        if sev in counts:
            counts[sev] += 1

    summary = (
        f"{len(issues)} security finding(s): "
        f"{counts['HIGH']} high, {counts['MEDIUM']} medium, {counts['LOW']} low."
    )
    return {"issues": issues, "summary": summary, "error": None}


def _parse_radon_cc(cc_data: dict, base_path: str) -> tuple:
    """Parse radon CC JSON output into issues list, avg complexity, and grade."""
    issues = []
    all_complexities = []
    for filepath, functions in cc_data.items():
        short_path = filepath.replace(base_path, "").lstrip("/\\")
        for func in functions:
            complexity = func.get("complexity", 0)
            rank = func.get("rank", "A")
            all_complexities.append(complexity)
            if rank not in ("A", "B"):
                issues.append(
                    {
                        "file": short_path,
                        "name": func.get("name", "?"),
                        "complexity": complexity,
                        "rank": rank,
                    }
                )
    avg_complexity = (
        sum(all_complexities) / len(all_complexities) if all_complexities else 0.0
    )
    avg_grade = _complexity_to_grade(avg_complexity)
    return issues, round(avg_complexity, 2), avg_grade


def _fetch_radon_mi(path: str) -> dict:
    """Run radon mi on *path* and return a {short_filepath: mi_score} mapping."""
    try:
        mi_result = subprocess.run(
            ["radon", "mi", "-j", path],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        mi_data = json.loads(mi_result.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return {}
    mi_scores = {}
    for filepath, info in mi_data.items():
        short_path = filepath.replace(path, "").lstrip("/\\")
        mi_scores[short_path] = info.get("mi", info) if isinstance(info, dict) else info
    return mi_scores


def run_radon(path: str) -> dict:
    """
    Run radon cc and mi on *path* and return structured results.

    Return shape::

        {
            "avg_complexity": float,
            "avg_grade": str,          # A-F
            "issues": [{"file": str, "name": str, "complexity": int,
                        "rank": str}, ...],
            "mi_scores": {"file": mi_score, ...},
            "summary": str,
            "error": str | None,
        }
    """
    # --- Cyclomatic complexity -------------------------------------------------
    try:
        cc_result = subprocess.run(
            ["radon", "cc", "-j", path],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        cc_data = json.loads(cc_result.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        return {
            "avg_complexity": 0.0,
            "avg_grade": "A",
            "issues": [],
            "mi_scores": {},
            "summary": "radon execution failed",
            "error": str(exc),
        }

    issues, avg_complexity, avg_grade = _parse_radon_cc(cc_data, path)
    mi_scores = _fetch_radon_mi(path)

    summary = (
        f"Average cyclomatic complexity: {avg_complexity:.1f} (grade {avg_grade}). "
        f"{len(issues)} function(s) rated C or worse."
    )
    return {
        "avg_complexity": avg_complexity,
        "avg_grade": avg_grade,
        "issues": issues,
        "mi_scores": mi_scores,
        "summary": summary,
        "error": None,
    }


def run_black(path: str) -> dict:
    """
    Run black --check on *path* and return files that would be reformatted.

    Return shape::

        {
            "files": [str, ...],
            "summary": str,
            "error": str | None,
        }
    """
    try:
        result = subprocess.run(
            ["black", "--check", path],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"files": [], "summary": "black execution failed", "error": str(exc)}

    files = []
    for line in result.stderr.splitlines():
        if line.startswith("would reformat "):
            filepath = line[len("would reformat ") :].strip()
            files.append(filepath.replace(path, "").lstrip("/\\"))

    summary = (
        f"{len(files)} file(s) would be reformatted by black."
        if files
        else "All files are already black-formatted."
    )
    return {"files": files, "summary": summary, "error": None}


_MYPY_LINE_RE = re.compile(r"^(.+?):(\d+):\s+(error|warning|note):\s+(.*)$")


def run_mypy(path: str) -> dict:
    """
    Run mypy on *path* and return structured results.

    Return shape::

        {
            "issues": [{"file": str, "line": int, "severity": str,
                        "message": str}, ...],
            "summary": str,
            "error": str | None,
        }
    """
    try:
        result = subprocess.run(
            [
                "mypy",
                path,
                "--ignore-missing-imports",
                "--no-error-summary",
                "--no-pretty",
            ],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"issues": [], "summary": "mypy execution failed", "error": str(exc)}

    issues = []
    for line in result.stdout.splitlines():
        m = _MYPY_LINE_RE.match(line)
        if m:
            issues.append(
                {
                    "file": m.group(1).replace(path, "").lstrip("/\\"),
                    "line": int(m.group(2)),
                    "severity": m.group(3),
                    "message": m.group(4).strip(),
                }
            )

    errors = sum(1 for i in issues if i["severity"] == "error")
    warnings = sum(1 for i in issues if i["severity"] == "warning")
    summary = f"{errors} type error(s), {warnings} warning(s) found by mypy."
    return {"issues": issues, "summary": summary, "error": None}


def run_ruff(path: str) -> dict:
    """
    Run ruff check on *path* and return structured results.

    Return shape::

        {
            "issues": [{"file": str, "line": int, "col": int,
                        "code": str, "message": str}, ...],
            "summary": str,
            "error": str | None,
        }
    """
    try:
        result = subprocess.run(
            ["ruff", "check", path, "--output-format=json", "--exit-zero"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        stderr = result.stderr[:500] if result.stderr else "no output"
        return {
            "issues": [],
            "summary": "ruff produced no parseable output",
            "error": stderr,
        }
    except (OSError, subprocess.SubprocessError) as exc:
        return {"issues": [], "summary": "ruff execution failed", "error": str(exc)}

    issues = []
    for item in data:
        issues.append(
            {
                "file": item.get("filename", "").replace(path, "").lstrip("/\\"),
                "line": item.get("location", {}).get("row", 0),
                "col": item.get("location", {}).get("column", 0),
                "code": item.get("code", ""),
                "message": item.get("message", ""),
            }
        )

    summary = f"{len(issues)} linting issue(s) found by ruff."
    return {"issues": issues, "summary": summary, "error": None}


def run_pylint(path: str) -> dict:
    """
    Run pylint on *path* and return structured results.

    Return shape::

        {
            "issues": [{"file": str, "line": int, "type": str,
                        "symbol": str, "message": str, "message_id": str}, ...],
            "summary": str,
            "error": str | None,
        }
    """
    try:
        result = subprocess.run(
            [
                "pylint",
                path,
                "--recursive=y",
                "--load-plugins=pylint_django",
                "--ignore=migrations",
                "--output-format=json",
                "--exit-zero",
            ],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        stderr = result.stderr[:500] if result.stderr else "no output"
        return {
            "issues": [],
            "summary": "pylint produced no parseable output",
            "error": stderr,
        }
    except (OSError, subprocess.SubprocessError) as exc:
        return {"issues": [], "summary": "pylint execution failed", "error": str(exc)}

    issues = []
    for item in data:
        issues.append(
            {
                "file": item.get("path", "").replace(path, "").lstrip("/\\"),
                "line": item.get("line", 0),
                "type": item.get("type", ""),
                "symbol": item.get("symbol", ""),
                "message": item.get("message", ""),
                "message_id": item.get("message-id", ""),
            }
        )

    counts = {"convention": 0, "refactor": 0, "warning": 0, "error": 0, "fatal": 0}
    for issue in issues:
        t = issue["type"]
        if t in counts:
            counts[t] += 1

    summary = (
        f"{len(issues)} pylint issue(s): "
        f"{counts['error']} error(s), {counts['warning']} warning(s), "
        f"{counts['refactor']} refactor(s), {counts['convention']} convention(s)."
    )
    return {"issues": issues, "summary": summary, "error": None}


def run_pytest_coverage(path: str) -> dict:
    """
    Run pytest with coverage inside *path* and return the total coverage %.

    Return shape::

        {
            "coverage_pct": int,        # 0-100, or None if no tests found
            "files": {"file": pct, ...},
            "summary": str,
            "error": str | None,
        }
    """
    try:
        result = subprocess.run(
            [
                "python",
                "-m",
                "pytest",
                "--cov=.",
                "--cov-report=term-missing",
                "--no-header",
                "-q",
                "--tb=no",
            ],
            capture_output=True,
            text=True,
            timeout=180,
            cwd=path,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "coverage_pct": None,
            "files": {},
            "summary": "pytest execution failed",
            "error": str(exc),
        }

    # No tests collected
    if (
        "no tests ran" in result.stdout.lower()
        or "no tests ran" in result.stderr.lower()
    ):
        return {
            "coverage_pct": 0,
            "files": {},
            "summary": "No tests found. Coverage: 0%.",
            "error": None,
        }

    # Parse per-file coverage and TOTAL line
    files: dict = {}
    coverage_pct: int = 0
    _cov_line_re = re.compile(r"^(\S+\.py)\s+\d+\s+\d+\s+(\d+)%")
    _total_re = re.compile(r"^TOTAL\s+\d+\s+\d+\s+(\d+)%")

    for line in result.stdout.splitlines():
        m_total = _total_re.match(line)
        if m_total:
            coverage_pct = int(m_total.group(1))
            continue
        m_file = _cov_line_re.match(line)
        if m_file:
            files[m_file.group(1)] = int(m_file.group(2))

    summary = f"Test coverage: {coverage_pct}%."
    return {
        "coverage_pct": coverage_pct,
        "files": files,
        "summary": summary,
        "error": None,
    }


def run_vulture(path: str) -> dict:
    """
    Run vulture on *path* to detect dead code.

    Return shape::

        {
            "items": [{"file": str, "line": int, "kind": str,
                       "name": str, "confidence": int}, ...],
            "summary": str,
            "error": str | None,
        }
    """
    try:
        result = subprocess.run(
            ["vulture", path, "--min-confidence", "60"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"items": [], "summary": "vulture execution failed", "error": str(exc)}

    # Line format: /abs/path/file.py:42: unused function 'foo' (60% confidence)
    _vulture_re = re.compile(
        r"^(.+?):(\d+): unused (\w+(?:\s+\w+)*) \'(.+?)\' \((\d+)% confidence\)$"
    )
    items = []
    for line in result.stdout.splitlines():
        m = _vulture_re.match(line)
        if m:
            items.append(
                {
                    "file": m.group(1).replace(path, "").lstrip("/\\"),
                    "line": int(m.group(2)),
                    "kind": m.group(3),
                    "name": m.group(4),
                    "confidence": int(m.group(5)),
                }
            )

    summary = f"{len(items)} unused code item(s) found by vulture."
    return {"items": items, "summary": summary, "error": None}


_TODO_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b.*", re.IGNORECASE)


def _scan_file_for_todos(filepath: str, base_path: str) -> list:
    """Scan a single .py file for TODO/FIXME/HACK/XXX comments."""
    results = []
    short_path = filepath.replace(base_path, "").lstrip("/\\")
    try:
        with open(filepath, encoding="utf-8", errors="ignore") as fh:
            for lineno, raw_line in enumerate(fh, start=1):
                m = _TODO_RE.search(raw_line)
                if m:
                    results.append(
                        {
                            "file": short_path,
                            "line": lineno,
                            "keyword": m.group(1).upper(),
                            "text": raw_line.strip(),
                        }
                    )
    except OSError:
        pass
    return results


def run_todo_fixme(path: str) -> dict:
    """
    Walk *path* recursively and count TODO/FIXME/HACK/XXX comments in .py files.

    Return shape::

        {
            "occurrences": [{"file": str, "line": int,
                             "keyword": str, "text": str}, ...],
            "counts": {"TODO": int, "FIXME": int, "HACK": int, "XXX": int},
            "summary": str,
            "error": str | None,
        }
    """
    try:
        occurrences = []
        counts: dict = {"TODO": 0, "FIXME": 0, "HACK": 0, "XXX": 0}
        for dirpath, _dirs, filenames in os.walk(path):
            for filename in filenames:
                if not filename.endswith(".py"):
                    continue
                for item in _scan_file_for_todos(os.path.join(dirpath, filename), path):
                    occurrences.append(item)
                    counts[item["keyword"]] = counts.get(item["keyword"], 0) + 1
        total = sum(counts.values())
        summary = (
            f"{total} technical debt comment(s): "
            f"{counts['TODO']} TODO, {counts['FIXME']} FIXME, "
            f"{counts['HACK']} HACK, {counts['XXX']} XXX."
        )
        return {
            "occurrences": occurrences,
            "counts": counts,
            "summary": summary,
            "error": None,
        }
    except OSError as exc:
        return {
            "occurrences": [],
            "counts": {},
            "summary": "todo scan failed",
            "error": str(exc),
        }


def _complexity_to_grade(avg: float) -> str:
    if avg <= 5:
        return "A"
    if avg <= 10:
        return "B"
    if avg <= 15:
        return "C"
    if avg <= 20:
        return "D"
    if avg <= 25:
        return "E"
    return "F"


# ---------------------------------------------------------------------------
# Score helpers
# ---------------------------------------------------------------------------


def _compute_style_score(tool_results: dict) -> int:
    """Compute style score from flake8, ruff, black, and pylint results."""

    def _score(count: int, per: int = 1) -> int:
        return max(0, 100 - count * per)

    flake8_r = tool_results["flake8_result"]
    ruff_r = tool_results["ruff_result"]
    black_r = tool_results["black_result"]
    pylint_r = tool_results["pylint_result"]
    f8 = (
        _score(len(flake8_r.get("issues", [])))
        if flake8_r.get("error") is None
        else 100
    )
    rf = _score(len(ruff_r.get("issues", []))) if ruff_r.get("error") is None else 100
    bk = (
        _score(len(black_r.get("files", [])), 10)
        if black_r.get("error") is None
        else 100
    )
    deductions = {"convention": 1, "refactor": 1, "warning": 2, "error": 5, "fatal": 10}
    py_total = (
        sum(deductions.get(i.get("type", ""), 0) for i in pylint_r.get("issues", []))
        if pylint_r.get("error") is None
        else 0
    )
    return (f8 + rf + bk + max(0, 100 - py_total)) // 4


def _compute_security_score(tool_results: dict) -> int:
    """Compute security score from bandit result."""
    bandit_r = tool_results["bandit_result"]
    score = 100
    if bandit_r.get("error") is None:
        deductions = {"LOW": 2, "MEDIUM": 5, "HIGH": 10}
        for issue in bandit_r.get("issues", []):
            score -= deductions.get(issue.get("severity", ""), 0)
    return max(0, min(100, score))


def _compute_architecture_score(tool_results: dict) -> int:
    """Compute architecture score from radon result."""
    radon_r = tool_results["radon_result"]
    score = 100
    if radon_r.get("error") is None:
        grade_deductions = {"A": 0, "B": 0, "C": 10, "D": 20, "E": 40, "F": 40}
        score -= grade_deductions.get(radon_r.get("avg_grade", "A"), 0)
    return max(0, min(100, score))


def _compute_type_safety_score(tool_results: dict) -> int:
    """Compute type safety score from mypy result."""
    mypy_r = tool_results["mypy_result"]
    if mypy_r.get("error") is not None:
        return 100
    errors = sum(1 for i in mypy_r.get("issues", []) if i.get("severity") == "error")
    return max(0, 100 - errors * 5)


def _compute_coverage_score(tool_results: dict) -> int:
    """Compute test coverage score."""
    cov_r = tool_results["coverage_result"]
    if cov_r.get("error") is not None:
        return 0
    pct = cov_r.get("coverage_pct")
    if pct is None:
        return 0
    score = int(pct)
    if score < 60:
        score = max(0, score - (60 - score) // 2)
    return max(0, min(100, score))


def _compute_dead_code_score(tool_results: dict) -> int:
    """Compute dead code score from vulture result."""
    vulture_r = tool_results["vulture_result"]
    if vulture_r.get("error") is not None:
        return 100
    return max(0, 100 - len(vulture_r.get("items", [])) * 3)


def _compute_todo_score(tool_results: dict) -> int:
    """Compute TODO/FIXME density score."""
    todo_r = tool_results["todo_result"]
    total = sum(todo_r.get("counts", {}).values())
    return max(0, 100 - total * 2)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def calculate_scores(tool_results: dict) -> dict:
    """
    Compute scores for each category and an overall weighted score.

    *tool_results* must be a dict with keys: flake8_result, bandit_result,
    radon_result, black_result, mypy_result, ruff_result, pylint_result,
    coverage_result, vulture_result, todo_result.

    Returns keys: style, security, architecture, type_safety,
                  coverage, dead_code, todo, overall  — each int in [0, 100].
    """
    style = _compute_style_score(tool_results)
    security = _compute_security_score(tool_results)
    architecture = _compute_architecture_score(tool_results)
    type_safety = _compute_type_safety_score(tool_results)
    coverage = _compute_coverage_score(tool_results)
    dead_code = _compute_dead_code_score(tool_results)
    todo = _compute_todo_score(tool_results)
    overall = max(
        0,
        min(
            100,
            int(
                style * 0.20
                + security * 0.20
                + architecture * 0.15
                + type_safety * 0.15
                + coverage * 0.15
                + dead_code * 0.10
                + todo * 0.05
            ),
        ),
    )
    return {
        "style": style,
        "security": security,
        "architecture": architecture,
        "type_safety": type_safety,
        "coverage": coverage,
        "dead_code": dead_code,
        "todo": todo,
        "overall": overall,
    }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def analyze_repository(repo_url: str) -> "RepositoryAnalysis":
    """
    Clone *repo_url*, run all analysis tools, compute scores, persist
    the result to the database, clean up temp files, and return the
    saved ``RepositoryAnalysis`` instance.

    Raises ``ValueError`` for invalid URLs and ``RuntimeError`` for
    clone failures; all other exceptions propagate as-is.
    """
    tmpdir = clone_repository(repo_url)  # may raise ValueError / RuntimeError
    try:
        if not _has_python_files(tmpdir):
            raise ValueError(
                "This repository does not contain any Python files. "
                "RepoRanker only supports Python projects."
            )
        flake8_result = run_flake8(tmpdir)
        bandit_result = run_bandit(tmpdir)
        radon_result = run_radon(tmpdir)
        black_result = run_black(tmpdir)
        mypy_result = run_mypy(tmpdir)
        ruff_result = run_ruff(tmpdir)
        pylint_result = run_pylint(tmpdir)
        coverage_result = run_pytest_coverage(tmpdir)
        vulture_result = run_vulture(tmpdir)
        todo_result = run_todo_fixme(tmpdir)

        scores = calculate_scores(
            {
                "flake8_result": flake8_result,
                "bandit_result": bandit_result,
                "radon_result": radon_result,
                "black_result": black_result,
                "mypy_result": mypy_result,
                "ruff_result": ruff_result,
                "pylint_result": pylint_result,
                "coverage_result": coverage_result,
                "vulture_result": vulture_result,
                "todo_result": todo_result,
            }
        )

        report_details = {
            "style": {
                "issues": flake8_result["issues"],
                "summary": flake8_result["summary"],
                "error": flake8_result.get("error"),
            },
            "security": {
                "issues": bandit_result["issues"],
                "summary": bandit_result["summary"],
                "error": bandit_result.get("error"),
            },
            "architecture": {
                "avg_complexity": radon_result["avg_complexity"],
                "avg_grade": radon_result["avg_grade"],
                "issues": radon_result["issues"],
                "mi_scores": radon_result["mi_scores"],
                "summary": radon_result["summary"],
                "error": radon_result.get("error"),
            },
            "black": {
                "files": black_result["files"],
                "summary": black_result["summary"],
                "error": black_result.get("error"),
            },
            "mypy": {
                "issues": mypy_result["issues"],
                "summary": mypy_result["summary"],
                "error": mypy_result.get("error"),
            },
            "ruff": {
                "issues": ruff_result["issues"],
                "summary": ruff_result["summary"],
                "error": ruff_result.get("error"),
            },
            "pylint": {
                "issues": pylint_result["issues"],
                "summary": pylint_result["summary"],
                "error": pylint_result.get("error"),
            },
            "coverage": {
                "coverage_pct": coverage_result.get("coverage_pct"),
                "files": coverage_result.get("files", {}),
                "summary": coverage_result["summary"],
                "error": coverage_result.get("error"),
            },
            "dead_code": {
                "items": vulture_result["items"],
                "summary": vulture_result["summary"],
                "error": vulture_result.get("error"),
            },
            "todo": {
                "occurrences": todo_result["occurrences"],
                "counts": todo_result.get("counts", {}),
                "summary": todo_result["summary"],
                "error": todo_result.get("error"),
            },
        }

        analysis = RepositoryAnalysis.objects.create(  # pylint: disable=no-member
            repo_url=repo_url,
            style_score=scores["style"],
            security_score=scores["security"],
            architecture_score=scores["architecture"],
            type_score=scores["type_safety"],
            coverage_score=scores["coverage"],
            dead_code_score=scores["dead_code"],
            todo_score=scores["todo"],
            overall_score=scores["overall"],
            report_details=report_details,
        )
        return analysis
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
