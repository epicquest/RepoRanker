"""Security tool runner: bandit."""

import json
import subprocess  # nosec B404

from .base import find_tool


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
        result = subprocess.run(  # nosec B603
            [find_tool("bandit"), "-r", path, "-f", "json", "-q", "--exit-zero"],
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
