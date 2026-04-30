"""Complexity tool runner: radon (cyclomatic complexity + maintainability index)."""

import json
import subprocess  # nosec B404

from .base import find_tool


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
        mi_result = subprocess.run(  # nosec B603
            [find_tool("radon"), "mi", "-j", path],
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
    try:
        cc_result = subprocess.run(  # nosec B603
            [find_tool("radon"), "cc", "-j", path],
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
