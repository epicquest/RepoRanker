"""
services.py — all business logic for RepoRanker.

Public API:
    analyze_repository(repo_url) -> RepositoryAnalysis
"""
import json
import re
import shutil
import subprocess
import tempfile

import git

from .models import RepositoryAnalysis

GITHUB_URL_RE = re.compile(
    r'^https://github\.com/[\w.\-]+/[\w.\-]+(\.git)?/?$'
)

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
        )
    except Exception as exc:  # noqa: BLE001
        return {"issues": [], "summary": "flake8 execution failed", "error": str(exc)}

    issues = []
    for line in result.stdout.splitlines():
        parts = line.split(":", 4)
        if len(parts) >= 5:
            try:
                issues.append({
                    "file": parts[0].replace(path, "").lstrip("/\\"),
                    "line": int(parts[1]),
                    "col": int(parts[2]),
                    "code": parts[3].strip(),
                    "message": parts[4].strip(),
                })
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
        )
    except Exception as exc:  # noqa: BLE001
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
        issues.append({
            "file": item.get("filename", "").replace(path, "").lstrip("/\\"),
            "line": item.get("line_number", 0),
            "severity": item.get("issue_severity", "UNKNOWN").upper(),
            "confidence": item.get("issue_confidence", "UNKNOWN").upper(),
            "message": item.get("issue_text", ""),
        })

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
        )
        cc_data = json.loads(cc_result.stdout)
    except Exception as exc:  # noqa: BLE001
        return {
            "avg_complexity": 0.0,
            "avg_grade": "A",
            "issues": [],
            "mi_scores": {},
            "summary": "radon execution failed",
            "error": str(exc),
        }

    issues = []
    all_complexities = []
    for filepath, functions in cc_data.items():
        short_path = filepath.replace(path, "").lstrip("/\\")
        for func in functions:
            complexity = func.get("complexity", 0)
            rank = func.get("rank", "A")
            all_complexities.append(complexity)
            if rank not in ("A", "B"):
                issues.append({
                    "file": short_path,
                    "name": func.get("name", "?"),
                    "complexity": complexity,
                    "rank": rank,
                })

    avg_complexity = (
        sum(all_complexities) / len(all_complexities) if all_complexities else 0.0
    )
    avg_grade = _complexity_to_grade(avg_complexity)

    # --- Maintainability Index ------------------------------------------------
    mi_scores = {}
    try:
        mi_result = subprocess.run(
            ["radon", "mi", "-j", path],
            capture_output=True,
            text=True,
            timeout=120,
        )
        mi_data = json.loads(mi_result.stdout)
        for filepath, info in mi_data.items():
            short_path = filepath.replace(path, "").lstrip("/\\")
            mi_scores[short_path] = (
                info.get("mi", info) if isinstance(info, dict) else info
            )
    except Exception:  # noqa: BLE001
        pass  # MI is supplementary; failures are tolerated

    summary = (
        f"Average cyclomatic complexity: {avg_complexity:.1f} (grade {avg_grade}). "
        f"{len(issues)} function(s) rated C or worse."
    )
    return {
        "avg_complexity": round(avg_complexity, 2),
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
        )
    except Exception as exc:  # noqa: BLE001
        return {"files": [], "summary": "black execution failed", "error": str(exc)}

    files = []
    for line in result.stderr.splitlines():
        if line.startswith("would reformat "):
            filepath = line[len("would reformat "):].strip()
            files.append(filepath.replace(path, "").lstrip("/\\"))

    summary = (
        f"{len(files)} file(s) would be reformatted by black."
        if files
        else "All files are already black-formatted."
    )
    return {"files": files, "summary": summary, "error": None}


_MYPY_LINE_RE = re.compile(r'^(.+?):(\d+):\s+(error|warning|note):\s+(.*)$')


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
        )
    except Exception as exc:  # noqa: BLE001
        return {"issues": [], "summary": "mypy execution failed", "error": str(exc)}

    issues = []
    for line in result.stdout.splitlines():
        m = _MYPY_LINE_RE.match(line)
        if m:
            issues.append({
                "file": m.group(1).replace(path, "").lstrip("/\\"),
                "line": int(m.group(2)),
                "severity": m.group(3),
                "message": m.group(4).strip(),
            })

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
        )
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        stderr = result.stderr[:500] if result.stderr else "no output"
        return {
            "issues": [],
            "summary": "ruff produced no parseable output",
            "error": stderr,
        }
    except Exception as exc:  # noqa: BLE001
        return {"issues": [], "summary": "ruff execution failed", "error": str(exc)}

    issues = []
    for item in data:
        issues.append({
            "file": item.get("filename", "").replace(path, "").lstrip("/\\"),
            "line": item.get("location", {}).get("row", 0),
            "col": item.get("location", {}).get("column", 0),
            "code": item.get("code", ""),
            "message": item.get("message", ""),
        })

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
                "--output-format=json",
                "--exit-zero",
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        stderr = result.stderr[:500] if result.stderr else "no output"
        return {
            "issues": [],
            "summary": "pylint produced no parseable output",
            "error": stderr,
        }
    except Exception as exc:  # noqa: BLE001
        return {"issues": [], "summary": "pylint execution failed", "error": str(exc)}

    issues = []
    for item in data:
        issues.append({
            "file": item.get("path", "").replace(path, "").lstrip("/\\"),
            "line": item.get("line", 0),
            "type": item.get("type", ""),
            "symbol": item.get("symbol", ""),
            "message": item.get("message", ""),
            "message_id": item.get("message-id", ""),
        })

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
# Scoring
# ---------------------------------------------------------------------------


def calculate_scores(
    flake8_result: dict,
    bandit_result: dict,
    radon_result: dict,
    black_result: dict,
    mypy_result: dict,
    ruff_result: dict,
    pylint_result: dict,
) -> dict:
    """
    Compute scores for each category and return a dict with keys
    ``style``, ``security``, ``architecture``, ``type_safety`` — each an int in [0, 100].

    Style is the average of four independent tool scores so that no single
    tool can dominate.  Type-safety is driven solely by mypy.
    """
    def _tool_style_score(issues_count: int, per_issue: int = 1) -> int:
        return max(0, 100 - issues_count * per_issue)

    # --- Style: average of four tool scores ----------------------------------
    flake8_score = (
        _tool_style_score(len(flake8_result.get("issues", [])))
        if flake8_result.get("error") is None else 100
    )
    ruff_score = (
        _tool_style_score(len(ruff_result.get("issues", [])))
        if ruff_result.get("error") is None else 100
    )
    black_score = (
        _tool_style_score(len(black_result.get("files", [])), per_issue=10)
        if black_result.get("error") is None else 100
    )
    pylint_deductions = {"convention": 1, "refactor": 1, "warning": 2, "error": 5, "fatal": 10}
    pylint_total = (
        sum(pylint_deductions.get(i.get("type", ""), 0) for i in pylint_result.get("issues", []))
        if pylint_result.get("error") is None else 0
    )
    pylint_score = max(0, 100 - pylint_total)

    style = (flake8_score + ruff_score + black_score + pylint_score) // 4

    # --- Security: bandit (unchanged) ----------------------------------------
    security = 100
    if bandit_result.get("error") is None:
        severity_deductions = {"LOW": 2, "MEDIUM": 5, "HIGH": 10}
        for issue in bandit_result.get("issues", []):
            security -= severity_deductions.get(issue.get("severity", ""), 0)
    security = max(0, min(100, security))

    # --- Architecture: radon grade-based (unchanged) -------------------------
    architecture = 100
    if radon_result.get("error") is None:
        grade = radon_result.get("avg_grade", "A")
        grade_deductions = {"A": 0, "B": 0, "C": 10, "D": 20, "E": 40, "F": 40}
        architecture -= grade_deductions.get(grade, 0)
    architecture = max(0, min(100, architecture))

    # --- Type safety: mypy ---------------------------------------------------
    type_safety = 100
    if mypy_result.get("error") is None:
        errors = sum(1 for i in mypy_result.get("issues", []) if i.get("severity") == "error")
        type_safety = max(0, 100 - errors * 5)

    return {
        "style": style,
        "security": security,
        "architecture": architecture,
        "type_safety": type_safety,
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
        flake8_result = run_flake8(tmpdir)
        bandit_result = run_bandit(tmpdir)
        radon_result = run_radon(tmpdir)
        black_result = run_black(tmpdir)
        mypy_result = run_mypy(tmpdir)
        ruff_result = run_ruff(tmpdir)
        pylint_result = run_pylint(tmpdir)

        scores = calculate_scores(
            flake8_result, bandit_result, radon_result,
            black_result, mypy_result, ruff_result, pylint_result,
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
        }

        analysis = RepositoryAnalysis.objects.create(
            repo_url=repo_url,
            style_score=scores["style"],
            security_score=scores["security"],
            architecture_score=scores["architecture"],
            type_score=scores["type_safety"],
            report_details=report_details,
        )
        return analysis
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
