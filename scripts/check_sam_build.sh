#!/bin/bash
# Diagnostic: run `sam validate --lint` on every pattern's template.yaml
# and report PASS/FAIL. Read-only; does not modify anything.
set -u
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}"
for f in $(find solutions -name "template.yaml" | sort); do
  d=$(dirname "$f")
  name=$(echo "$d" | sed 's|solutions/||')
  out=$(cd "$d" && sam validate --lint 2>&1)
  if echo "$out" | grep -q "is a valid SAM Template"; then
    echo "PASS  $name"
  else
    firsterr=$(echo "$out" | grep -iE "error|E[0-9]{4}|invalid" | head -1)
    echo "FAIL  $name  :: ${firsterr:0:90}"
  fi
done
