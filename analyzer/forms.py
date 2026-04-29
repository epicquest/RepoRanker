import re

from django import forms


GITHUB_URL_RE = re.compile(
    r'^https://github\.com/[\w.\-]+/[\w.\-]+(\.git)?/?$'
)


class RepositoryForm(forms.Form):
    repo_url = forms.URLField(
        label="GitHub Repository URL",
        max_length=500,
        widget=forms.URLInput(attrs={
            "placeholder": "https://github.com/owner/repo",
            "class": "form-control",
        }),
    )

    def clean_repo_url(self):
        url = self.cleaned_data["repo_url"].strip().rstrip("/")
        if not GITHUB_URL_RE.match(url):
            raise forms.ValidationError(
                "Please enter a valid public GitHub repository URL "
                "(e.g. https://github.com/owner/repo)."
            )
        # Normalise: strip trailing .git
        if url.endswith(".git"):
            url = url[:-4]
        return url
