"""Shared utilities for all tool runners."""

import shutil
from typing import Callable

# Type alias for tool runner functions.
Tool = Callable[[str], dict]


def find_tool(name: str) -> str:
    """Return the absolute path to *name* on PATH.

    Raises FileNotFoundError if the tool is not installed.
    Caught by the ``except OSError`` blocks in each ``run_*`` function.
    """
    resolved = shutil.which(name)
    if resolved is None:
        raise FileNotFoundError(f"Required tool not found: {name!r}")
    return resolved
