"""
services.py — orchestration layer for RepoRanker.

Public API:
    analyze_repository(repo_url) -> RepositoryAnalysis
"""

import asyncio
import contextlib
import logging
import os
import shutil
import subprocess  # nosec - Used safely with shell=False and hardcoded commands
import tempfile
import time

import git

from .repository import AnalysisRepository
from .scoring import calculate_scores
from .tools import (
    async_run_bandit,
    async_run_black,
    async_run_flake8,
    async_run_mypy,
    async_run_pylint,
    async_run_pytest_coverage,
    async_run_radon,
    async_run_ruff,
    async_run_todo_fixme,
    async_run_vulture,
)
from .validators import GITHUB_URL_RE

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def temporary_repo_directory(repo_url: str):
    """
    Context manager that clones a repository and ensures temp directory cleanup.

    Yields the path to the cloned repository directory. On exit, attempts to
    remove the directory with retry logic. Logs all cleanup attempts and failures.

    Raises ValueError for invalid URLs, RuntimeError for clone failures.
    """
    tmpdir = clone_repository(repo_url)  # may raise ValueError / RuntimeError
    try:
        logger.debug("Cloned repository to %s", tmpdir)
        yield tmpdir
    finally:
        logger.debug("Cleaning up temporary directory: %s", tmpdir)
        _cleanup_temp_directory(tmpdir)


def _cleanup_temp_directory(tmpdir: str, max_retries: int = 3) -> None:
    """
    Attempt to remove a temporary directory with retry logic.

    Logs cleanup attempts and any errors encountered. If cleanup fails after
    max_retries, logs a warning but does not raise an exception.

    Args:
        tmpdir: Path to the temporary directory to remove.
        max_retries: Maximum number of cleanup attempts (default 3).
    """
    for attempt in range(1, max_retries + 1):
        try:
            shutil.rmtree(tmpdir, ignore_errors=False)
            logger.debug("Successfully removed %s on attempt %d", tmpdir, attempt)
            return
        except (OSError, PermissionError) as exc:
            if attempt < max_retries:
                logger.debug(
                    "Cleanup attempt %d failed for %s: %s. Retrying...",
                    attempt,
                    tmpdir,
                    exc,
                )
                time.sleep(0.5)  # Brief pause before retry
            else:
                logger.warning(
                    "Failed to clean up %s after %d attempts: %s",
                    tmpdir,
                    max_retries,
                    exc,
                )


async def _run_all_tools_parallel(tmpdir: str) -> dict:
    """
    Run all analysis tools concurrently with a maximum of 5 workers.

    Executes all 10 analysis tools in parallel using asyncio. If any tool
    fails, the error is captured in the result but doesn't prevent other
    tools from running.

    Args:
        tmpdir: Path to the repository directory to analyze.

    Returns:
        A dict mapping tool names to their results:
        {
            "flake8_result": {...},
            "bandit_result": {...},
            "radon_result": {...},
            ...
        }
    """
    # Create a semaphore to limit concurrent workers to 5
    semaphore = asyncio.Semaphore(5)

    async def run_with_semaphore(tool_name: str, coro):
        """Run a coroutine with semaphore limiting."""
        async with semaphore:
            logger.debug("Starting tool: %s", tool_name)
            start_time = time.time()
            try:
                result = await coro
                elapsed = time.time() - start_time
                logger.debug(
                    "Completed tool: %s in %.2fs",
                    tool_name,
                    elapsed,
                )
                return tool_name, result
            except (
                OSError,
                subprocess.SubprocessError,
                ValueError,
                RuntimeError,
            ) as exc:
                logger.warning(
                    "Tool %s failed: %s",
                    tool_name,
                    exc,
                )
                # Return error result for this tool
                return tool_name, {
                    "error": f"Exception during {tool_name}: {exc}",
                    "issues": [],
                    "items": [],
                    "occurrences": [],
                    "summary": f"{tool_name} execution failed",
                }

    # Create all tool tasks
    tasks = [
        run_with_semaphore("flake8_result", async_run_flake8(tmpdir)),
        run_with_semaphore("bandit_result", async_run_bandit(tmpdir)),
        run_with_semaphore("radon_result", async_run_radon(tmpdir)),
        run_with_semaphore("black_result", async_run_black(tmpdir)),
        run_with_semaphore("mypy_result", async_run_mypy(tmpdir)),
        run_with_semaphore("ruff_result", async_run_ruff(tmpdir)),
        run_with_semaphore("pylint_result", async_run_pylint(tmpdir)),
        run_with_semaphore("coverage_result", async_run_pytest_coverage(tmpdir)),
        run_with_semaphore("vulture_result", async_run_vulture(tmpdir)),
        run_with_semaphore("todo_result", async_run_todo_fixme(tmpdir)),
    ]

    # Run all tasks concurrently
    logger.debug("Starting parallel execution of 10 analysis tools")
    start_time = time.time()
    results = await asyncio.gather(*tasks, return_exceptions=False)
    elapsed = time.time() - start_time
    logger.debug("All tools completed in %.2fs", elapsed)

    # Convert list of (name, result) tuples to dict
    return dict(results)


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
    Clone *repo_url*, run all analysis tools concurrently, compute scores,
    persist the result to the database, clean up temp files, and return the
    saved ``RepositoryAnalysis`` instance.

    Tools are executed in parallel (max 5 concurrent workers) to improve
    analysis speed. Cleanup is guaranteed via context manager.

    Raises ``ValueError`` for invalid URLs and ``RuntimeError`` for
    clone failures; all other exceptions propagate as-is.
    """
    logger.info("Starting analysis of %s", repo_url)

    with temporary_repo_directory(repo_url) as tmpdir:
        if not _has_python_files(tmpdir):
            raise ValueError(
                "This repository does not contain any Python files. "
                "RepoRanker only supports Python projects."
            )

        # Run all tools concurrently
        tool_results = asyncio.run(_run_all_tools_parallel(tmpdir))

        # Compute scores from tool results
        scores = calculate_scores(tool_results)

        # Build report details from tool results
        report_details = _build_report_details(tool_results)

        repo = AnalysisRepository()
        analysis = repo.save(repo_url, scores, report_details)
        logger.info(
            "Analysis complete for %s: overall_score=%d",
            repo_url,
            analysis.overall_score,
        )
        return analysis


def _build_report_details(tool_results: dict) -> dict:
    """Build detailed report from tool results.

    Extracts and structures tool results into a nested dict for storage.

    Args:
        tool_results: Dict mapping tool names to their result dicts.

    Returns:
        A structured report_details dict for database storage.
    """
    return {
        "style": {
            "issues": tool_results["flake8_result"]["issues"],
            "summary": tool_results["flake8_result"]["summary"],
            "error": tool_results["flake8_result"].get("error"),
        },
        "security": {
            "issues": tool_results["bandit_result"]["issues"],
            "summary": tool_results["bandit_result"]["summary"],
            "error": tool_results["bandit_result"].get("error"),
        },
        "architecture": {
            "avg_complexity": tool_results["radon_result"]["avg_complexity"],
            "avg_grade": tool_results["radon_result"]["avg_grade"],
            "issues": tool_results["radon_result"]["issues"],
            "mi_scores": tool_results["radon_result"]["mi_scores"],
            "summary": tool_results["radon_result"]["summary"],
            "error": tool_results["radon_result"].get("error"),
        },
        "black": {
            "files": tool_results["black_result"]["files"],
            "summary": tool_results["black_result"]["summary"],
            "error": tool_results["black_result"].get("error"),
        },
        "mypy": {
            "issues": tool_results["mypy_result"]["issues"],
            "summary": tool_results["mypy_result"]["summary"],
            "error": tool_results["mypy_result"].get("error"),
        },
        "ruff": {
            "issues": tool_results["ruff_result"]["issues"],
            "summary": tool_results["ruff_result"]["summary"],
            "error": tool_results["ruff_result"].get("error"),
        },
        "pylint": {
            "issues": tool_results["pylint_result"]["issues"],
            "summary": tool_results["pylint_result"]["summary"],
            "error": tool_results["pylint_result"].get("error"),
        },
        "coverage": {
            "coverage_pct": tool_results["coverage_result"].get("coverage_pct"),
            "files": tool_results["coverage_result"].get("files", {}),
            "summary": tool_results["coverage_result"]["summary"],
            "error": tool_results["coverage_result"].get("error"),
        },
        "dead_code": {
            "items": tool_results["vulture_result"]["items"],
            "summary": tool_results["vulture_result"]["summary"],
            "error": tool_results["vulture_result"].get("error"),
        },
        "todo": {
            "occurrences": tool_results["todo_result"]["occurrences"],
            "counts": tool_results["todo_result"].get("counts", {}),
            "summary": tool_results["todo_result"]["summary"],
            "error": tool_results["todo_result"].get("error"),
        },
    }
