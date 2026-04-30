#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
source "$ROOT/.venv/bin/activate"

# Explicit source paths — keeps linters out of .venv and other non-project dirs
SRC_DIRS=(analyzer reporanker manage.py)

PASS=0
FAIL=0

run_tool() {
    local name="$1"
    shift
    echo ""
    echo "----------------------------------------"
    echo "  $name"
    echo "----------------------------------------"
    if "$@"; then
        echo "PASS: $name"
        PASS=$((PASS + 1))
    else
        echo "FAIL: $name"
        FAIL=$((FAIL + 1))
    fi
}

cd "$ROOT"
export DJANGO_SETTINGS_MODULE=reporanker.settings

run_tool "black"    black --check "${SRC_DIRS[@]}"
run_tool "ruff"     ruff check "${SRC_DIRS[@]}"
run_tool "pylint"   pylint "${SRC_DIRS[@]}" --load-plugins=pylint_django --ignore=migrations --exit-zero
run_tool "mypy"     mypy "${SRC_DIRS[@]}" --ignore-missing-imports --no-error-summary
run_tool "vulture"  vulture "${SRC_DIRS[@]}" whitelist_django.py --min-confidence 60
run_tool "pytest"   python -m pytest --cov=. --cov-report=term-missing --no-header -q

echo ""
echo "----------------------------------------"
echo "  Results: $PASS passed, $FAIL failed"
echo "----------------------------------------"

[ "$FAIL" -eq 0 ]

