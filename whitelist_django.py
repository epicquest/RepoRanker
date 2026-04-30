"""
Vulture whitelist — suppresses false positives from Django's convention-based
attribute access that static analysis cannot trace.

This file is never executed; vulture reads it to mark symbols as "used".
"""

# pylint: skip-file
# ruff: noqa

from analyzer.admin import RepositoryAnalysisAdmin
from analyzer.apps import AnalyzerConfig
from analyzer.forms import RepositoryForm
from analyzer.models import RepositoryAnalysis
import importlib as _il
_migration = _il.import_module("analyzer.migrations.0001_initial").Migration

# Django admin class attributes
RepositoryAnalysisAdmin.list_display
RepositoryAnalysisAdmin.readonly_fields

# AppConfig attribute
AnalyzerConfig.default_auto_field

# Form validation hook (called by Django via naming convention)
RepositoryForm.clean_repo_url

# Migration attributes (read by Django's migration loader)
_migration.initial
_migration.dependencies
_migration.operations

# Model fields (accessed as instance attributes by the ORM)
RepositoryAnalysis.style_score
RepositoryAnalysis.security_score
RepositoryAnalysis.architecture_score
RepositoryAnalysis.type_score
RepositoryAnalysis.coverage_score
RepositoryAnalysis.dead_code_score
RepositoryAnalysis.todo_score
RepositoryAnalysis.overall_score
RepositoryAnalysis.Meta
RepositoryAnalysis.Meta.ordering

# URL configuration (discovered by Django's URL resolver)
import analyzer.urls
import reporanker.urls
analyzer.urls.urlpatterns
reporanker.urls.urlpatterns

# WSGI/ASGI entry points (referenced by the app server, not Python imports)
import reporanker.wsgi
import reporanker.asgi
reporanker.wsgi.application
reporanker.asgi.application

# Django settings variables (read via django.conf.settings at runtime)
import reporanker.settings as _s
_s.SECRET_KEY
_s.DEBUG
_s.ALLOWED_HOSTS
_s.INSTALLED_APPS
_s.MIDDLEWARE
_s.ROOT_URLCONF
_s.TEMPLATES
_s.WSGI_APPLICATION
_s.DATABASES
_s.AUTH_PASSWORD_VALIDATORS
_s.LANGUAGE_CODE
_s.TIME_ZONE
_s.USE_I18N
_s.USE_TZ
_s.STATIC_URL
_s.DEFAULT_AUTO_FIELD

# unittest / mock attributes (called by the test runner via naming convention)
from unittest.mock import MagicMock as _Mock
from django.test import TestCase as _TC
_TC.setUp
_Mock.side_effect
_Mock.return_value
