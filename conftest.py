import os


def pytest_configure(config):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "reporanker.settings")
    import django

    django.setup()
