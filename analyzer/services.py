"""
services.py — orchestration layer for RepoRanker.

Public API:
    analyze_repository(repo_url) -> RepositoryAnalysis
"""

import os
import shutil
import tempfile

import git

from .repository import AnalysisRepository
from .scoring import calculate_scores
from .tools import (
    run_bandit,
    run_black,
    run_flake8,
    run_mypy,
    run_pylint,
    run_pytest_coverage,
    run_radon,
    run_ruff,
    run_todo_fixme,
    run_vulture,
)
from .validators import GITHUB_URL_RE


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


def analyze_repository(repo_url: str) -> "AnalysisRepository":
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

        repo = AnalysisRepository()
        return repo.save(repo_url, scores, report_details)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
