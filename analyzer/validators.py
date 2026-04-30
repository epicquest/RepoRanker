"""URL validation for RepoRanker."""

import re

GITHUB_URL_RE = re.compile(r"^https://github\.com/[\w.\-]+/[\w.\-]+(\.git)?/?$")
