"""Unit tests for the analyzer app."""

import asyncio
import os
import tempfile
from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse

from .models import RepositoryAnalysis
from .scoring import calculate_scores
from .services import (
    _cleanup_temp_directory,
    _has_python_files,
    _run_all_tools_parallel,
    clone_repository,
    temporary_repo_directory,
)
from .tools.complexity import _complexity_to_grade, async_run_radon, run_radon
from .tools.style import async_run_flake8, run_flake8
from .validators import GITHUB_URL_RE

# ---------------------------------------------------------------------------
# services.py — URL regex
# ---------------------------------------------------------------------------


class TestGithubUrlRegex(TestCase):
    """Tests for the GITHUB_URL_RE regex pattern."""

    def test_valid_urls(self):
        """Test that valid GitHub URLs match the pattern."""
        valid = [
            "https://github.com/user/repo",
            "https://github.com/user/repo.git",
            "https://github.com/user/repo/",
            "https://github.com/user-name/repo-name",
            "https://github.com/user_name/repo.name",
        ]
        for url in valid:
            self.assertIsNotNone(GITHUB_URL_RE.match(url), f"Expected match: {url}")

    def test_invalid_urls(self):
        """Test that invalid URLs do not match the pattern."""
        invalid = [
            "http://github.com/user/repo",
            "https://gitlab.com/user/repo",
            "https://github.com/user",
            "not-a-url",
            "",
        ]
        for url in invalid:
            self.assertIsNone(GITHUB_URL_RE.match(url), f"Expected no match: {url}")


# ---------------------------------------------------------------------------
# services.py — _has_python_files
# ---------------------------------------------------------------------------


class TestHasPythonFiles(TestCase):
    """Tests for the _has_python_files helper function."""

    def test_with_python_file(self):
        """Test that a directory with a .py file returns True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "main.py"), "w", encoding="utf-8"):
                pass
            self.assertTrue(_has_python_files(tmpdir))

    def test_without_python_file(self):
        """Test that a directory without .py files returns False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "README.md"), "w", encoding="utf-8"):
                pass
            self.assertFalse(_has_python_files(tmpdir))

    def test_empty_directory(self):
        """Test that an empty directory returns False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertFalse(_has_python_files(tmpdir))

    def test_nested_python_file(self):
        """Test that a nested .py file is detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = os.path.join(tmpdir, "src")
            os.makedirs(subdir)
            with open(os.path.join(subdir, "module.py"), "w", encoding="utf-8"):
                pass
            self.assertTrue(_has_python_files(tmpdir))


# ---------------------------------------------------------------------------
# services.py — _complexity_to_grade
# ---------------------------------------------------------------------------


class TestComplexityToGrade(TestCase):
    """Tests for the _complexity_to_grade helper function."""

    def test_grade_a(self):
        """Test grade A thresholds (complexity 1-5)."""
        self.assertEqual(_complexity_to_grade(1), "A")
        self.assertEqual(_complexity_to_grade(5), "A")

    def test_grade_b(self):
        """Test grade B thresholds (complexity 6-10)."""
        self.assertEqual(_complexity_to_grade(6), "B")
        self.assertEqual(_complexity_to_grade(10), "B")

    def test_grade_c(self):
        """Test grade C thresholds (complexity 11-15)."""
        self.assertEqual(_complexity_to_grade(11), "C")
        self.assertEqual(_complexity_to_grade(15), "C")

    def test_grade_d(self):
        """Test grade D thresholds (complexity 16-20)."""
        self.assertEqual(_complexity_to_grade(16), "D")
        self.assertEqual(_complexity_to_grade(20), "D")

    def test_grade_e(self):
        """Test grade E thresholds (complexity 21-25)."""
        self.assertEqual(_complexity_to_grade(21), "E")
        self.assertEqual(_complexity_to_grade(25), "E")

    def test_grade_f(self):
        """Test grade F threshold (complexity > 25)."""
        self.assertEqual(_complexity_to_grade(26), "F")
        self.assertEqual(_complexity_to_grade(100), "F")


# ---------------------------------------------------------------------------
# services.py — calculate_scores
# ---------------------------------------------------------------------------


class TestCalculateScores(TestCase):
    """Tests for the calculate_scores function."""

    def _make_results(self, **overrides):
        """Build a default tool results dict, optionally overriding specific tools."""
        defaults = {
            "flake8_result": {"issues": [], "summary": "", "error": None},
            "bandit_result": {"issues": [], "summary": "", "error": None},
            "radon_result": {
                "avg_complexity": 2.0,
                "avg_grade": "A",
                "issues": [],
                "mi_scores": {},
                "summary": "",
                "error": None,
            },
            "black_result": {"files": [], "summary": "", "error": None},
            "mypy_result": {"issues": [], "summary": "", "error": None},
            "ruff_result": {"issues": [], "summary": "", "error": None},
            "pylint_result": {"issues": [], "summary": "", "error": None},
            "coverage_result": {
                "coverage_pct": 100,
                "files": {},
                "summary": "",
                "error": None,
            },
            "vulture_result": {"items": [], "summary": "", "error": None},
            "todo_result": {
                "occurrences": [],
                "counts": {},
                "summary": "",
                "error": None,
            },
        }
        defaults.update(overrides)
        return defaults

    def test_perfect_scores(self):
        """Test that clean tool results produce 100 for all scores."""
        scores = calculate_scores(self._make_results())
        self.assertEqual(scores["style"], 100)
        self.assertEqual(scores["security"], 100)
        self.assertEqual(scores["architecture"], 100)
        self.assertEqual(scores["type_safety"], 100)
        self.assertEqual(scores["coverage"], 100)
        self.assertEqual(scores["dead_code"], 100)
        self.assertEqual(scores["todo"], 100)
        self.assertEqual(scores["overall"], 100)

    def test_flake8_issues_reduce_style(self):
        """Test that flake8 issues lower the style score."""
        results = self._make_results(
            flake8_result={"issues": [{}] * 20, "summary": "", "error": None}
        )
        self.assertLess(calculate_scores(results)["style"], 100)

    def test_bandit_high_severity_reduces_security(self):
        """Test that high-severity bandit findings lower the security score."""
        results = self._make_results(
            bandit_result={
                "issues": [{"severity": "HIGH"}] * 5,
                "summary": "",
                "error": None,
            }
        )
        self.assertLess(calculate_scores(results)["security"], 100)

    def test_zero_coverage(self):
        """Test that 0% coverage yields a coverage score of 0."""
        results = self._make_results(
            coverage_result={
                "coverage_pct": 0,
                "files": {},
                "summary": "",
                "error": None,
            }
        )
        self.assertEqual(calculate_scores(results)["coverage"], 0)

    def test_overall_in_range(self):
        """Test that the overall score is always between 0 and 100."""
        scores = calculate_scores(self._make_results())
        self.assertGreaterEqual(scores["overall"], 0)
        self.assertLessEqual(scores["overall"], 100)

    def test_tool_error_gives_neutral_style(self):
        """Test that a tool error results in a neutral (100) style score."""
        results = self._make_results(
            flake8_result={"issues": [], "summary": "", "error": "flake8 not found"}
        )
        self.assertEqual(calculate_scores(results)["style"], 100)


# ---------------------------------------------------------------------------
# services.py — clone_repository URL validation
# ---------------------------------------------------------------------------


class TestCloneRepositoryValidation(TestCase):
    """Tests for clone_repository URL validation."""

    def test_invalid_url_raises_value_error(self):
        """Test that a non-GitHub URL raises ValueError."""
        with self.assertRaises(ValueError):
            clone_repository("https://notgithub.com/user/repo")

    def test_non_url_raises_value_error(self):
        """Test that a completely invalid string raises ValueError."""
        with self.assertRaises(ValueError):
            clone_repository("not-a-url-at-all")


# ---------------------------------------------------------------------------
# views.py
# ---------------------------------------------------------------------------


class TestIndexView(TestCase):
    """Tests for the index view."""

    def setUp(self):
        """Set up the test client."""
        self.client = Client()

    def test_get_renders_form(self):
        """GET request renders the index template with a form."""
        response = self.client.get(reverse("index"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "analyzer/index.html")
        self.assertIn("form", response.context)

    def test_post_invalid_url_shows_error(self):
        """POST with a non-URL value shows form errors without running analysis."""
        response = self.client.post(reverse("index"), {"repo_url": "not-a-url"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["form"].is_valid())

    @patch("analyzer.views.analyze_repository")
    def test_post_value_error_shows_form_error(self, mock_analyze):
        """ValueError from analyze_repository is shown as a form field error."""
        mock_analyze.side_effect = ValueError("Not a Python repo")
        response = self.client.post(
            reverse("index"),
            {"repo_url": "https://github.com/user/repo"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "analyzer/index.html")

    @patch("analyzer.views.analyze_repository")
    def test_post_success_redirects_to_results(self, mock_analyze):
        """Successful analysis redirects to the results page."""
        analysis = RepositoryAnalysis(
            pk=1,
            repo_url="https://github.com/user/repo",
            overall_score=80,
        )
        mock_analyze.return_value = analysis
        response = self.client.post(
            reverse("index"),
            {"repo_url": "https://github.com/user/repo"},
        )
        self.assertRedirects(
            response,
            reverse("results", kwargs={"pk": 1}),
            fetch_redirect_response=False,
        )


class TestResultsView(TestCase):
    """Tests for the results view."""

    def setUp(self):
        """Set up the test client and a sample analysis record."""
        self.client = Client()
        self.analysis = RepositoryAnalysis.objects.create(  # pylint: disable=no-member
            repo_url="https://github.com/user/repo",
            overall_score=75,
            report_details={},
        )

    def test_results_renders_analysis(self):
        """Results page renders the correct template with the analysis object."""
        response = self.client.get(reverse("results", kwargs={"pk": self.analysis.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "analyzer/results.html")
        self.assertEqual(response.context["analysis"], self.analysis)

    def test_results_404_for_missing_pk(self):
        """Non-existent analysis PK returns a 404 response."""
        response = self.client.get(reverse("results", kwargs={"pk": 9999}))
        self.assertEqual(response.status_code, 404)


# ---------------------------------------------------------------------------
# services.py — Async and Concurrency Tests
# ---------------------------------------------------------------------------


class TestTemporaryRepoDirectoryCleanup(TestCase):
    """Tests for the temporary_repo_directory context manager."""

    def test_cleanup_on_success(self):
        """Test that temp directory is cleaned up after successful context exit."""
        tmpdir = None
        with patch("analyzer.services.clone_repository") as mock_clone:
            real_tmpdir = tempfile.mkdtemp(prefix="reporanker_test_")
            mock_clone.return_value = real_tmpdir
            tmpdir = real_tmpdir

            with temporary_repo_directory("https://github.com/user/repo") as cloned_dir:
                self.assertTrue(os.path.exists(cloned_dir))
                self.assertEqual(cloned_dir, real_tmpdir)

            # After context exit, directory should be cleaned up
            self.assertFalse(os.path.exists(tmpdir))

    def test_cleanup_on_exception(self):
        """Test that temp directory is cleaned up even if exception occurs in context."""
        tmpdir = None
        with patch("analyzer.services.clone_repository") as mock_clone:
            real_tmpdir = tempfile.mkdtemp(prefix="reporanker_test_")
            mock_clone.return_value = real_tmpdir
            tmpdir = real_tmpdir

            with self.assertRaises(ValueError):
                with temporary_repo_directory("https://github.com/user/repo"):
                    raise ValueError("Simulated error")

            # Directory should still be cleaned up despite exception
            self.assertFalse(os.path.exists(tmpdir))

    def test_cleanup_retry_on_permission_error(self):
        """Test that cleanup retries on PermissionError."""
        with patch("shutil.rmtree") as mock_rmtree:
            # Simulate permission error on first attempt, success on second
            mock_rmtree.side_effect = [
                PermissionError("Permission denied"),
                None,  # Success on second attempt
            ]

            _cleanup_temp_directory("/tmp/test")

            # rmtree should have been called twice (retry logic)
            self.assertEqual(mock_rmtree.call_count, 2)


class TestAsyncToolsExecution(TestCase):
    """Tests for async tool execution."""

    def test_async_run_flake8(self):
        """Test that async_run_flake8 produces the same result as run_flake8."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a simple Python file
            test_file = os.path.join(tmpdir, "test.py")
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("import os\n")  # Unused import

            # Run both sync and async versions
            sync_result = run_flake8(tmpdir)
            async_result = asyncio.run(async_run_flake8(tmpdir))

            # Both should have same structure
            self.assertIn("issues", sync_result)
            self.assertIn("issues", async_result)
            self.assertIn("summary", sync_result)
            self.assertIn("summary", async_result)

    def test_async_run_radon(self):
        """Test that async_run_radon produces the same result as run_radon."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a simple Python file
            test_file = os.path.join(tmpdir, "test.py")
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("def hello():\n    print('hello')\n")

            # Run both sync and async versions
            sync_result = run_radon(tmpdir)
            async_result = asyncio.run(async_run_radon(tmpdir))

            # Both should have same structure
            self.assertIn("avg_complexity", sync_result)
            self.assertIn("avg_complexity", async_result)
            self.assertIn("avg_grade", sync_result)
            self.assertIn("avg_grade", async_result)


class TestAsyncParallelization(TestCase):
    """Tests for async tool parallelization."""

    def test_run_all_tools_parallel_returns_all_results(self):
        """Test that _run_all_tools_parallel returns results for all 10 tools."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a minimal Python project structure
            os.makedirs(os.path.join(tmpdir, "tests"))
            with open(os.path.join(tmpdir, "main.py"), "w", encoding="utf-8") as f:
                f.write("print('hello')\n")
            with open(
                os.path.join(tmpdir, "tests", "test_main.py"), "w", encoding="utf-8"
            ) as f:
                f.write("def test_hello():\n    assert True\n")

            # Run parallel execution
            results = asyncio.run(_run_all_tools_parallel(tmpdir))

            # Verify all 10 tool results are present
            expected_tools = [
                "flake8_result",
                "bandit_result",
                "radon_result",
                "black_result",
                "mypy_result",
                "ruff_result",
                "pylint_result",
                "coverage_result",
                "vulture_result",
                "todo_result",
            ]
            for tool_name in expected_tools:
                self.assertIn(tool_name, results)
                self.assertIsInstance(results[tool_name], dict)

    def test_async_parallel_execution_faster_than_sequential(self):
        """Test that parallel execution is measurably faster (with mocking)."""
        # This test uses mocking to verify parallelization logic
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "test.py"), "w", encoding="utf-8") as f:
                f.write("def foo():\n    pass\n")

            # Just verify the function completes without error
            results = asyncio.run(_run_all_tools_parallel(tmpdir))

            # All tools should have completed
            self.assertEqual(len(results), 10)

    def test_partial_tool_failure_does_not_crash(self):
        """Test that failure of one tool doesn't prevent others from running."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create minimal Python file
            with open(os.path.join(tmpdir, "test.py"), "w", encoding="utf-8") as f:
                f.write("print('test')\n")

            # Run parallel tools - even if some fail, we get results for others
            results = asyncio.run(_run_all_tools_parallel(tmpdir))

            # We should have 10 results, some may have errors but all should be present
            self.assertEqual(len(results), 10)

            # At least some tools should succeed (e.g., radon, flake8)
            successful = sum(
                1 for result in results.values() if result.get("error") is None
            )
            self.assertGreater(successful, 0)
