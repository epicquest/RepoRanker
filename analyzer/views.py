"""Views for the analyzer app."""

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import RepositoryForm
from .models import RepositoryAnalysis
from .pdf_export import generate_pdf
from .services import analyze_repository


def index(request):
    """Render the analysis form and handle form submission."""
    if request.method == "POST":
        form = RepositoryForm(request.POST)
        if form.is_valid():
            repo_url = form.cleaned_data["repo_url"]
            try:
                analysis = analyze_repository(repo_url)
                return redirect("results", pk=analysis.pk)
            except (ValueError, RuntimeError) as exc:
                form.add_error("repo_url", str(exc))
            except Exception as exc:  # pylint: disable=broad-exception-caught
                form.add_error(None, f"Unexpected error during analysis: {exc}")
    else:
        form = RepositoryForm()
    return render(request, "analyzer/index.html", {"form": form})


def results(request, pk):
    """Render the analysis results page for the given primary key."""
    analysis = get_object_or_404(RepositoryAnalysis, pk=pk)
    return render(request, "analyzer/results.html", {"analysis": analysis})


def history(request):
    """List all previously analyzed repositories."""
    analyses = RepositoryAnalysis.objects.all()  # pylint: disable=no-member
    return render(request, "analyzer/history.html", {"analyses": analyses})


def delete(request, pk):
    """Delete an analysis record (POST only) and redirect to history."""
    if request.method == "POST":
        analysis = get_object_or_404(RepositoryAnalysis, pk=pk)
        analysis.delete()
    return redirect("history")


def export_pdf(request, pk):
    """Export analysis results as PDF."""
    analysis = get_object_or_404(RepositoryAnalysis, pk=pk)
    pdf_content = generate_pdf(analysis)

    response = HttpResponse(pdf_content, content_type="application/pdf")
    response["Content-Disposition"] = (
        f"attachment; filename=analysis_{analysis.pk}_{analysis.created_at.strftime('%Y%m%d_%H%M%S')}.pdf"
    )
    return response
