#!/bin/bash
# Phase 8 demo-guide sync: re-translate all 17 UC demo-guides from JP source.
# This ensures all language variants match the current JP version which has:
# - Screenshot sections (Phase 8 Theme D)
# - OutputDestination sections (Phase 7/8 Theme I)
# - Phase 8 SUCCEEDED screenshots embedded
#
# Usage: bash scripts/_batch_translate_phase8_sync.sh [--dry-run] [--resume-from <uc>]
set -u

DRY_RUN=0
RESUME_FROM=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --resume-from) RESUME_FROM="$2"; shift ;;
  esac
  shift
done

UCS=(
  "solutions/industry/legal-compliance"
  "solutions/industry/financial-idp"
  "solutions/industry/manufacturing-analytics"
  "solutions/industry/media-vfx"
  "solutions/industry/healthcare-dicom"
  "solutions/industry/semiconductor-eda"
  "solutions/industry/genomics-pipeline"
  "solutions/industry/energy-seismic"
  "solutions/industry/autonomous-driving"
  "solutions/industry/construction-bim"
  "solutions/industry/retail-catalog"
  "solutions/industry/logistics-ocr"
  "solutions/industry/education-research"
  "solutions/industry/insurance-claims"
  "solutions/industry/defense-satellite"
  "solutions/industry/government-archives"
  "solutions/industry/smart-city-geospatial"
)

DOCS=("demo-guide")
LANGS=("en" "ko" "zh-CN" "zh-TW" "fr" "de" "es")

TOTAL=$((${#UCS[@]} * ${#DOCS[@]} * ${#LANGS[@]}))
DONE=0
SUCCESS=0
FAILED=0
SKIPPING=0
if [ -n "$RESUME_FROM" ]; then
  SKIPPING=1
fi

LOG_FILE="/tmp/phase8-sync-$(date +%Y%m%d-%H%M%S).log"
echo "Phase 8 demo-guide sync batch"
echo "Total files to translate: $TOTAL"
echo "Logging to: $LOG_FILE"
echo ""

for uc in "${UCS[@]}"; do
  if [ "$SKIPPING" = "1" ] && [ "$uc" != "$RESUME_FROM" ]; then
    for doc in "${DOCS[@]}"; do
      for lang in "${LANGS[@]}"; do
        DONE=$((DONE + 1))
      done
    done
    echo "RESUMING — skipped $uc"
    continue
  fi
  SKIPPING=0

  for doc in "${DOCS[@]}"; do
    for lang in "${LANGS[@]}"; do
      DONE=$((DONE + 1))
      source_file="${uc}/docs/${doc}.md"
      if [ ! -f "$source_file" ]; then
        echo "[$DONE/$TOTAL] SKIP (no source): $source_file" | tee -a "$LOG_FILE"
        continue
      fi
      echo "[$DONE/$TOTAL] Translating ${uc}/${doc}.md → ${lang}" | tee -a "$LOG_FILE"
      if [ "$DRY_RUN" = "1" ]; then
        echo "    (dry-run)" | tee -a "$LOG_FILE"
      else
        if python3 scripts/_translate_uc_docs.py "$uc" "$doc" "$lang" 2>&1 | tee -a "$LOG_FILE" | grep -q "Written"; then
          SUCCESS=$((SUCCESS + 1))
        else
          FAILED=$((FAILED + 1))
          echo "    ⚠️ FAILED" | tee -a "$LOG_FILE"
        fi
        # Rate limiting: 1 second between calls to avoid throttling
        sleep 1
      fi
    done
  done
done

echo ""
echo "=== Phase 8 sync batch complete ==="
echo "Total: $TOTAL | Success: $SUCCESS | Failed: $FAILED"
echo "Log file: $LOG_FILE"
