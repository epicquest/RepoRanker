"""Dead code tool runner: vulture."""

import re
import subprocess  # nosec B404

from .base import find_tool


def run_vulture(path: str) -> dict:
    """
    Run vulture on *path* to detect dead code.

    Return shape::

        {
            "items": [{"file": str, "line": int, "kind": str,
                       "name": str, "confidence": int}, ...],
            "summary": str,
            "error": str | None,
        }
    """
    try:
        result = subprocess.run(  # nosec B603
            [find_tool("vulture"), path, "--min-confidence", "60"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"items": [], "summary": "vulture execution failed", "error": str(exc)}

    # Line format: /abs/path/file.py:42: unused function 'foo' (60% confidence)
    _vulture_re = re.compile(
        r"^(.+?):(\d+): unused (\w+(?:\s+\w+)*) \'(.+?)\' \((\d+)% confidence\)$"
    )
    items = []
    for line in result.stdout.splitlines():
        m = _vulture_re.match(line)
        if m:
            items.append(
                {
                    "file": m.group(1).replace(path, "").lstrip("/\\"),
                    "line": int(m.group(2)),
                    "kind": m.group(3),
                    "name": m.group(4),
                    "confidence": int(m.group(5)),
                }
            )

    summary = f"{len(items)} unused code item(s) found by vulture."
    return {"items": items, "summary": summary, "error": None}
