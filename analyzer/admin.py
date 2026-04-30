"""Django admin configuration for the analyzer app."""

from django.contrib import admin

from .models import RepositoryAnalysis


@admin.register(RepositoryAnalysis)
class RepositoryAnalysisAdmin(admin.ModelAdmin):
    """Admin interface for RepositoryAnalysis."""

    list_display = (
        "repo_url",
        "style_score",
        "security_score",
        "architecture_score",
        "created_at",
    )
    readonly_fields = ("created_at",)
