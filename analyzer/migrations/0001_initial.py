"""Initial database migration for the analyzer app."""  # pylint: disable=invalid-name

from django.db import migrations, models


class Migration(migrations.Migration):
    """Creates the initial RepositoryAnalysis table."""

    initial = True

    dependencies: list[tuple[str, str]] = []

    operations = [
        migrations.CreateModel(
            name="RepositoryAnalysis",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("repo_url", models.URLField(max_length=500)),
                ("style_score", models.IntegerField(default=0)),
                ("security_score", models.IntegerField(default=0)),
                ("architecture_score", models.IntegerField(default=0)),
                ("type_score", models.IntegerField(default=0)),
                ("coverage_score", models.IntegerField(default=0)),
                ("dead_code_score", models.IntegerField(default=0)),
                ("todo_score", models.IntegerField(default=0)),
                ("overall_score", models.IntegerField(default=0)),
                ("report_details", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
