#!/bin/bash
# Gate: every operations pattern whose handlers import shared/ must have the
# staging wrapper that puts shared/ into the deployment package, and must ignore
# the staged copies.
#
# Why a gate is needed: the OPS handlers import shared/ lazily inside functions,
# so a missing copy raises ImportError only in Lambda, at first call. The unit
# tests run from the repo root where shared/ is already importable, so they pass
# either way. Five of the six patterns shipped with no staging step at all and
# every test was green.
#
# Usage: bash scripts/check_ops_shared_staged.sh
set -uo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

fail=0
checked=0

for pattern in operations/*/; do
    [[ -f "$pattern/template.yaml" ]] || continue
    name="${pattern#operations/}"
    name="${name%/}"

    # Does any handler in this pattern reference the shared package?
    if ! grep -rqE '(^|[^.[:alnum:]_])(from|import)[[:space:]]+shared[.[:space:]]' \
        "$pattern"functions/*/handler.py 2>/dev/null; then
        continue
    fi
    checked=$((checked + 1))

    if [[ ! -f "$pattern/build.sh" ]]; then
        echo "FAIL  $name: handlers import shared/ but there is no build.sh to stage it" >&2
        echo "      the package will deploy without shared/ and ImportError at first call" >&2
        fail=1
        continue
    fi

    if ! grep -q 'build_ops_pattern.sh' "$pattern/build.sh"; then
        echo "FAIL  $name: build.sh does not delegate to scripts/build_ops_pattern.sh" >&2
        echo "      keep the staging logic in one place so all patterns stay in step" >&2
        fail=1
    fi

    if [[ ! -f "$pattern/.gitignore" ]] || ! grep -q 'functions/\*/shared/' "$pattern/.gitignore"; then
        echo "FAIL  $name: .gitignore does not ignore functions/*/shared/" >&2
        echo "      staged copies of shared/ would be committed" >&2
        fail=1
    fi
done

if [[ "$fail" -ne 0 ]]; then
    exit 1
fi

echo "OPS SHARED STAGING: PASS ($checked pattern(s) import shared/ and stage it)"
