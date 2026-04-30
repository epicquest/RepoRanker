"""Unit tests for the analyzer app."""

import os
import tempfile
from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse

from .models import RepositoryAnalysis
from .scoring import calculate_scores
from .services import (
    _has_python_files,
    clone_repository,
)
from .tools.complexity import _complexity_to_grade
from .validators import GITHUB_URL_RE

# ---------------------------------------------------------------------------
# validators.py — URL regex
# ---------------------------------------------------------------------------


class TestGithubUrlRegex(TestCase):
    """Tests for the GITHUB_URL_RE regex pattern."""

    def test_valid_urls(self):
        """Valid GitHub URLs should match the regex."""
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
        """Non-GitHub or malformed URLs should not match."""
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
    """Tests for the _has_python_files helper."""

    def test_with_python_file(self):
        """A directory containing a .py file returns True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "main.py"), "w", encoding="utf-8"):
                pass
            self.assertTrue(_has_python_files(tmpdir))

    def test_without_python_file(self):
        """A directory with only non-.py files returns False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "README.md"), "w", encoding="utf-8"):
                pass
            self.assertFalse(_has_python_files(tmpdir))

    def test_empty_directory(self):
        """An empty directory returns False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertFalse(_has_python_files(tmpdir))

    def test_nested_python_file(self):
        """A .py file in a subdirectory is detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = os.path.join(tmpdir, "src")
            os.makedirs(subdir)
            with open(os.path.join(subdir, "module.py"), "w", encoding="utf-8"):
                pass
            self.assertTrue(_has_python_files(tmpdir))


# ---------------------------------------------------------------------------
# tools/complexity.py — _complexity_to_grade
# ---------------------------------------------------------------------------


class TestComplexityToGrade(TestCase):
    """Tests for the _complexity_to_grade helper function."""

    def test_grade_a(self):
        """Complexity 1-5 maps to grade A."""
        self.assertEqual(_complexity_to_grade(1), "A")
        self.assertEqual(_complexity_to_grade(5), "A")

    def test_grade_b(self):
        """Complexity 6-10 maps to grade B."""
        self.assertEqual(_complexity_to_grade(6), "B")
        self.assertEqual(_complexity_to_grade(10), "B")

    def test_grade_c(self):
        """Complexity 11-15 maps to grade C."""
        self.assertEqual(_complexity_to_grade(11), "C")
        self.assertEqual(_complexity_to_grade(15), "C")

    def test_grade_d(self):
        """Complexity 16-20 maps to grade D."""
        self.assertEqual(_complexity_to_grade(16), "D")
        self.assertEqual(_complexity_to_grade(20), "D")

    def test_grade_e(self):
        """Complexity 21-25 maps to grade E."""
        self.assertEqual(_complexity_to_grade(21), "E")
        self.assertEqual(_complexity_to_grade(25), "E")

    def test_grade_f(self):
        """Complexity above 25 maps to grade F."""
        self.assertEqual(_complexity_to_grade(26), "F")
        self.assertEqual(_complexity_to_grade(100), "F")


# ---------------------------------------------------------------------------
# scoring.py — calculate_scores
# ---------------------------------------------------------------------------


class TestCalculateScores(TestCase):
    """Tests for the calculate_scores aggregation function."""

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
        """Clean tool results produce 100 for all scores."""
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
        """Flake8 issues lower the style score."""
        results = self._make_results(
            flake8_result={"issues": [{}] * 20, "summary": "", "error": None}
        )
        self.assertLess(calculate_scores(results)["style"], 100)

    def test_bandit_high_severity_reduces_security(self):
        """High-severity bandit findings lower the security score."""
        results = self._make_results(
            bandit_result={
                "issues": [{"severity": "HIGH"}] * 5,
                "summary": "",
                "error": None,
            }
        )
        self.assertLess(calculate_scores(results)["security"], 100)

    def test_zero_coverage(self):
        """Zero percent coverage yields a coverage score of 0."""
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
        """Overall score is always between 0 and 100."""
        scores = calculate_scores(self._make_results())
        self.assertGreaterEqual(scores["overall"], 0)
        self.assertLessEqual(scores["overall"], 100)

    def test_tool_error_gives_neutral_style(self):
        """A tool error does not penalise the style score."""
        results = self._make_results(
            flake8_result={"issues": [], "summary": "", "error": "flake8 not found"}
        )
        self.assertEqual(calculate_scores(results)["style"], 100)


# ---------------------------------------------------------------------------
# services.py — clone_repository URL validation
# ---------------------------------------------------------------------------


class TestCloneRepositoryValidation(TestCase):
    """Tests for URL validation in clone_repository."""

    def test_invalid_url_raises_value_error(self):
        """A non-GitHub URL raises ValueError."""
        with self.assertRaises(ValueError):
            clone_repository("https://notgithub.com/user/repo")

    def test_non_url_raises_value_error(self):
        """A plain string raises ValueError."""
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
        """GET request renders the form."""
        response = self.client.get(reverse("index"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "analyzer/index.html")
        self.assertIn("form", response.context)

    def test_post_invalid_url_shows_error(self):
        """POST with an invalid URL re-renders the form with errors."""
        response = self.client.post(reverse("index"), {"repo_url": "not-a-url"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["form"].is_valid())

    @patch("analyzer.views.analyze_repository")
    def test_post_value_error_shows_form_error(self, mock_analyze):
        """POST that triggers ValueError re-renders the form."""
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
        """Create a sample analysis record."""
        self.client = Client()
        self.analysis = RepositoryAnalysis.objects.create(  # pylint: disable=no-member
            repo_url="https://github.com/user/repo",
            overall_score=75,
            report_details={},
        )

    def test_results_renders_analysis(self):
        """GET renders the results template with the correct analysis."""
        response = self.client.get(reverse("results", kwargs={"pk": self.analysis.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "analyzer/results.html")
        self.assertEqual(response.context["analysis"], self.analysis)

    def test_results_404_for_missing_pk(self):
        """GET with a non-existent PK returns 404."""
        response = self.client.get(reverse("results", kwargs={"pk": 9999}))
        self.assertEqual(response.status_code, 404)
