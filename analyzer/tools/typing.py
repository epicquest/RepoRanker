"""Type-safety tool runner: mypy."""

import re
import subprocess  # nosec B404

from .base import find_tool

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
        result = subprocess.run(  # nosec B603
            [
                find_tool("mypy"),
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
