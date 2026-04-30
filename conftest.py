"""Pytest configuration: bootstraps Django settings before test collection."""

import os

import django


def pytest_configure(config):  # pylint: disable=unused-argument
    """Set up Django before pytest collects tests."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "reporanker.settings")
    django.setup()
