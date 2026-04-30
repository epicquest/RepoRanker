"""Django ORM models for RepoRanker."""

from django.db import models


class RepositoryAnalysis(models.Model):
    """Persisted result of analysing a single GitHub repository."""

    repo_url = models.URLField(max_length=500)
    style_score = models.IntegerField(default=0)
    security_score = models.IntegerField(default=0)
    architecture_score = models.IntegerField(default=0)
    type_score = models.IntegerField(default=0)
    coverage_score = models.IntegerField(default=0)
    dead_code_score = models.IntegerField(default=0)
    todo_score = models.IntegerField(default=0)
    overall_score = models.IntegerField(default=0)
    report_details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:  # pylint: disable=too-few-public-methods
        """Django model metadata."""

        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.repo_url} ({self.created_at:%Y-%m-%d %H:%M})"
