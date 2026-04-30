"""Tech debt scanner: TODO/FIXME/HACK/XXX comments."""

import os
import re

_TODO_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b.*", re.IGNORECASE)


def _scan_file_for_todos(filepath: str, base_path: str) -> list:
    """Scan a single .py file for TODO/FIXME/HACK/XXX comments."""
    results = []
    short_path = filepath.replace(base_path, "").lstrip("/\\")
    try:
        with open(filepath, encoding="utf-8", errors="ignore") as fh:
            for lineno, raw_line in enumerate(fh, start=1):
                m = _TODO_RE.search(raw_line)
                if m:
                    results.append(
                        {
                            "file": short_path,
                            "line": lineno,
                            "keyword": m.group(1).upper(),
                            "text": raw_line.strip(),
                        }
                    )
    except OSError:
        pass
    return results


def run_todo_fixme(path: str) -> dict:
    """
    Walk *path* recursively and count TODO/FIXME/HACK/XXX comments in .py files.

    Return shape::

        {
            "occurrences": [{"file": str, "line": int,
                             "keyword": str, "text": str}, ...],
            "counts": {"TODO": int, "FIXME": int, "HACK": int, "XXX": int},
            "summary": str,
            "error": str | None,
        }
    """
    try:
        occurrences = []
        counts: dict = {"TODO": 0, "FIXME": 0, "HACK": 0, "XXX": 0}
        for dirpath, _dirs, filenames in os.walk(path):
            for filename in filenames:
                if not filename.endswith(".py"):
                    continue
                for item in _scan_file_for_todos(os.path.join(dirpath, filename), path):
                    occurrences.append(item)
                    counts[item["keyword"]] = counts.get(item["keyword"], 0) + 1
        total = sum(counts.values())
        summary = (
            f"{total} technical debt comment(s): "
            f"{counts['TODO']} TODO, {counts['FIXME']} FIXME, "
            f"{counts['HACK']} HACK, {counts['XXX']} XXX."
        )
        return {
            "occurrences": occurrences,
            "counts": counts,
            "summary": summary,
            "error": None,
        }
    except OSError as exc:
        return {
            "occurrences": [],
            "counts": {},
            "summary": "todo scan failed",
            "error": str(exc),
        }
