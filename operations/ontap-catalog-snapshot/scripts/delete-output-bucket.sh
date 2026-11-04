#!/usr/bin/env bash
# Remove the output bucket that the stack keeps when it is deleted.
#
#   scripts/delete-output-bucket.sh <bucket> [region]          # lists what would go. Changes nothing.
#   scripts/delete-output-bucket.sh <bucket> [region] --yes    # empties the bucket, every version, and removes it
#
# Why this is a separate step: the snapshots are the record this pattern exists to keep, so the
# template sets DeletionPolicy: Retain and turns on versioning. A plain "empty the bucket" leaves
# the old versions and delete markers behind, and the bucket then refuses to go.
#
# Guards: it removes only a bucket that carries the tags this template puts on its own bucket
# (Project=fsxn-ontap-catalog-snapshot), it lists before it removes, and it needs --yes.
# The removal cannot be undone.
set -uo pipefail

BUCKET="${1:-}"
REGION="${2:-${AWS_REGION:-${AWS_DEFAULT_REGION:-}}}"
CONFIRM="no"
for a in "$@"; do [[ "$a" == "--yes" ]] && CONFIRM="yes"; done
[[ "$REGION" == "--yes" ]] && REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-}}"

if [[ -z "$BUCKET" || "$BUCKET" == --* ]]; then
  echo "usage: $0 <bucket> [region] [--yes]" >&2
  exit 2
fi
if [[ -z "$REGION" ]]; then
  echo "no region: pass it as the second argument or set AWS_REGION" >&2
  exit 2
fi

aws_q() {
  local out
  if ! out="$(aws --region "$REGION" "$@" 2>&1)"; then
    echo "FAILED: aws $*" >&2
    echo "$out" >&2
    exit 1
  fi
  printf '%s' "$out"
}

# 1. Refuse a bucket this pattern did not create.
project="$(aws_q s3api get-bucket-tagging --bucket "$BUCKET" --query "TagSet[?Key=='Project']|[0].Value" --output text)" || exit 1
if [[ "$project" != "fsxn-ontap-catalog-snapshot" ]]; then
  echo "REFUSED: $BUCKET is not tagged Project=fsxn-ontap-catalog-snapshot (found: ${project:-none})." >&2
  exit 1
fi

# 2. List what would go.
versions="$(aws_q s3api list-object-versions --bucket "$BUCKET" --query 'length(Versions || `[]`)' --output text)" || exit 1
markers="$(aws_q s3api list-object-versions --bucket "$BUCKET" --query 'length(DeleteMarkers || `[]`)' --output text)" || exit 1
echo "Bucket $BUCKET ($REGION): $versions object version(s), $markers delete marker(s)"
aws_q s3api list-object-versions --bucket "$BUCKET" --query 'Versions[].[LastModified,Size,Key]' --output text | head -50
echo

if [[ "$CONFIRM" != "yes" ]]; then
  echo "Nothing was changed. Review the list above, then run again with --yes to remove it for good."
  exit 0
fi

# 3. Empty the bucket one page (up to 1000) at a time: versions first, then delete markers.
for kind in Versions DeleteMarkers; do
  while :; do
    batch="$(aws_q s3api list-object-versions --bucket "$BUCKET" --no-paginate \
      --query "{Objects: ${kind}[].{Key: Key, VersionId: VersionId}}" --output json)" || exit 1
    if [[ "$batch" == *'"Objects": null'* || "$batch" == *'"Objects": []'* ]]; then
      break
    fi
    errors="$(aws_q s3api delete-objects --bucket "$BUCKET" --delete "$batch" --query 'length(Errors || `[]`)' --output text)" || exit 1
    if [[ "$errors" != "0" ]]; then
      # Stop here: listing the same objects again would loop forever.
      echo "FAILED: $errors object(s) could not be removed from $BUCKET." >&2
      exit 1
    fi
  done
done

aws_q s3api delete-bucket --bucket "$BUCKET" > /dev/null || exit 1
echo "Removed bucket $BUCKET."
