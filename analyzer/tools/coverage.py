"""Coverage tool runner: pytest-cov."""

import re
import subprocess  # nosec B404
import sys


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
        result = subprocess.run(  # nosec B603
            [
                sys.executable,
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
