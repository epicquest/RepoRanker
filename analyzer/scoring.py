"""Scoring functions for RepoRanker analysis categories."""

# Weights must sum to 1.0
SCORING_WEIGHTS: dict = {
    "style": 0.20,
    "security": 0.20,
    "architecture": 0.15,
    "type_safety": 0.15,
    "coverage": 0.15,
    "dead_code": 0.10,
    "todo": 0.05,
}


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
                style * SCORING_WEIGHTS["style"]
                + security * SCORING_WEIGHTS["security"]
                + architecture * SCORING_WEIGHTS["architecture"]
                + type_safety * SCORING_WEIGHTS["type_safety"]
                + coverage * SCORING_WEIGHTS["coverage"]
                + dead_code * SCORING_WEIGHTS["dead_code"]
                + todo * SCORING_WEIGHTS["todo"]
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
