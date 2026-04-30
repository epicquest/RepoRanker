"""URL configuration for the analyzer app."""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("results/<int:pk>/", views.results, name="results"),
    path("history/", views.history, name="history"),
    path("delete/<int:pk>/", views.delete, name="delete"),
]
