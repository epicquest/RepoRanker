"""Database persistence for RepoRanker analysis results."""

from .models import RepositoryAnalysis


class AnalysisRepository:  # pylint: disable=too-few-public-methods
    """Thin wrapper around the RepositoryAnalysis ORM model."""

    def save(
        self, repo_url: str, scores: dict, report_details: dict
    ) -> RepositoryAnalysis:
        """Persist an analysis result and return the saved instance."""
        return RepositoryAnalysis.objects.create(  # pylint: disable=no-member
            repo_url=repo_url,
            style_score=scores["style"],
            security_score=scores["security"],
            architecture_score=scores["architecture"],
            type_score=scores["type_safety"],
            coverage_score=scores["coverage"],
            dead_code_score=scores["dead_code"],
            todo_score=scores["todo"],
            overall_score=scores["overall"],
            report_details=report_details,
        )
