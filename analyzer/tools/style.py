"""Style tool runners: flake8, ruff, black, pylint."""

import json
import re
import subprocess  # nosec B404

from .base import find_tool


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
        result = subprocess.run(  # nosec B603
            [
                find_tool("flake8"),
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
        result = subprocess.run(  # nosec B603
            [find_tool("ruff"), "check", path, "--output-format=json", "--exit-zero"],
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
        result = subprocess.run(  # nosec B603
            [find_tool("black"), "--check", path],
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
        result = subprocess.run(  # nosec B603
            [
                find_tool("pylint"),
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


_MYPY_LINE_RE = re.compile(r"^(.+?):(\d+):\s+(error|warning|note):\s+(.*)$")
