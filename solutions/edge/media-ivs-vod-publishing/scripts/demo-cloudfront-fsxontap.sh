#!/usr/bin/env bash
#
# demo-cloudfront-fsxontap.sh
#
# Verify the "FSx for ONTAP S3 Access Point -> Amazon CloudFront (OAC)" delivery leg with a real
# short HLS asset. Creates an OAC + a CloudFront distribution in front of an EXISTING FSx for ONTAP
# S3 Access Point, uploads a generated HLS package under a dedicated prefix, verifies delivery, and
# (with `teardown`) removes everything it created.
#
# It does NOT create the FSx for ONTAP filesystem/volume/access point (use existing resources).
# It only touches the prefix you specify.
#
# Requirements: awscli v2, ffmpeg (for `gen`), curl, python3.
#
# Usage:
#   FSX_S3AP_ALIAS=<your-fsxontap-s3ap-alias> \
#   FSX_S3AP_NAME=<your-access-point-name> \
#   ACCOUNT_ID=<your-account-id> \
#   AWS_REGION=ap-northeast-1 \
#     ./demo-cloudfront-fsxontap.sh gen      # generate a short HLS test asset locally
#     ./demo-cloudfront-fsxontap.sh up       # upload + create OAC + distribution + AP policy
#     ./demo-cloudfront-fsxontap.sh verify    # curl the CloudFront URL
#     ./demo-cloudfront-fsxontap.sh teardown  # delete distribution, OAC (AP policy left to you)
#
# Placeholders only in docs. Never commit real aliases/account IDs/distribution IDs.

set -euo pipefail

AWS_REGION="${AWS_REGION:-ap-northeast-1}"
PREFIX="${PREFIX:-vod/demo1}"
WORKDIR="${WORKDIR:-./.hls-demo}"
STATE_FILE="${STATE_FILE:-./.hls-demo/state.env}"

require() { [[ -n "${!1:-}" ]] || { echo "ERROR: set env $1" >&2; exit 1; }; }

cmd_gen() {
  mkdir -p "${WORKDIR}"
  ( cd "${WORKDIR}"
    ffmpeg -y \
      -f lavfi -i "testsrc2=duration=12:size=640x360:rate=25" \
      -f lavfi -i "sine=frequency=440:sample_rate=48000:duration=12" \
      -map 0:v:0 -map 1:a:0 \
      -c:v libx264 -pix_fmt yuv420p -profile:v main -b:v 800k -g 50 -keyint_min 50 \
      -c:a aac -b:a 96k -ar 48000 \
      -hls_time 4 -hls_playlist_type vod -hls_segment_filename "seg_%03d.ts" media.m3u8
    cat > master.m3u8 <<'EOF'
#EXTM3U
#EXT-X-VERSION:3
#EXT-X-STREAM-INF:BANDWIDTH=900000,RESOLUTION=640x360,CODECS="avc1.4d401e,mp4a.40.2"
media.m3u8
EOF
  )
  echo ">> Generated HLS in ${WORKDIR}"
}

cmd_up() {
  require FSX_S3AP_ALIAS; require FSX_S3AP_NAME; require ACCOUNT_ID
  echo ">> Uploading HLS via the S3 Access Point alias (S3 API)"
  aws s3api put-object --region "${AWS_REGION}" --bucket "${FSX_S3AP_ALIAS}" \
    --key "${PREFIX}/master.m3u8" --body "${WORKDIR}/master.m3u8" \
    --content-type application/vnd.apple.mpegurl >/dev/null
  aws s3api put-object --region "${AWS_REGION}" --bucket "${FSX_S3AP_ALIAS}" \
    --key "${PREFIX}/media.m3u8" --body "${WORKDIR}/media.m3u8" \
    --content-type application/vnd.apple.mpegurl >/dev/null
  for s in "${WORKDIR}"/seg_*.ts; do
    aws s3api put-object --region "${AWS_REGION}" --bucket "${FSX_S3AP_ALIAS}" \
      --key "${PREFIX}/$(basename "$s")" --body "$s" --content-type video/mp2t >/dev/null
  done

  echo ">> Creating Origin Access Control (OAC)"
  OAC_ID=$(aws cloudfront create-origin-access-control --region us-east-1 \
    --origin-access-control-config "{\"Name\":\"media-ivs-demo-oac-$$\",\"SigningProtocol\":\"sigv4\",\"SigningBehavior\":\"always\",\"OriginAccessControlOriginType\":\"s3\"}" \
    --query "OriginAccessControl.Id" --output text)

  echo ">> Creating CloudFront distribution (origin = FSx for ONTAP S3 AP)"
  DIST_CFG=$(python3 - "$FSX_S3AP_ALIAS" "$AWS_REGION" "$OAC_ID" "$PREFIX" <<'PY'
import json,sys,time
alias,region,oac,prefix=sys.argv[1:5]
cfg={"CallerReference":f"media-ivs-demo-{int(time.time())}","Comment":"media-ivs-vod demo",
"Enabled":True,"Origins":{"Quantity":1,"Items":[{"Id":"s3ap-origin",
"DomainName":f"{alias}.s3.{region}.amazonaws.com","OriginPath":f"/{prefix}",
"OriginAccessControlId":oac,"S3OriginConfig":{"OriginAccessIdentity":""},
"CustomHeaders":{"Quantity":0},"ConnectionAttempts":3,"ConnectionTimeout":10,
"OriginShield":{"Enabled":False}}]},
"DefaultCacheBehavior":{"TargetOriginId":"s3ap-origin","ViewerProtocolPolicy":"redirect-to-https",
"Compress":True,"AllowedMethods":{"Quantity":2,"Items":["GET","HEAD"],
"CachedMethods":{"Quantity":2,"Items":["GET","HEAD"]}},
"CachePolicyId":"658327ea-f89d-4fab-a63d-7e88639e58f6"},
"PriceClass":"PriceClass_200","ViewerCertificate":{"CloudFrontDefaultCertificate":True},
"Restrictions":{"GeoRestriction":{"RestrictionType":"none","Quantity":0}}}
print(json.dumps(cfg))
PY
)
  echo "${DIST_CFG}" > "${WORKDIR}/dist.json"
  OUT=$(aws cloudfront create-distribution --region us-east-1 \
    --distribution-config "file://${WORKDIR}/dist.json" \
    --query "Distribution.{Id:Id,Domain:DomainName,ARN:ARN}" --output json)
  DIST_ID=$(echo "$OUT" | python3 -c 'import sys,json;print(json.load(sys.stdin)["Id"])')
  DIST_DOMAIN=$(echo "$OUT" | python3 -c 'import sys,json;print(json.load(sys.stdin)["Domain"])')
  DIST_ARN=$(echo "$OUT" | python3 -c 'import sys,json;print(json.load(sys.stdin)["ARN"])')

  echo ">> Setting S3 Access Point policy to allow this CloudFront distribution (OAC)"
  POLICY=$(python3 - "$AWS_REGION" "$ACCOUNT_ID" "$FSX_S3AP_NAME" "$DIST_ARN" <<'PY'
import json,sys
region,acct,name,arn=sys.argv[1:5]
print(json.dumps({"Version":"2012-10-17","Statement":[{"Sid":"AllowCloudFrontOACRead",
"Effect":"Allow","Principal":{"Service":"cloudfront.amazonaws.com"},"Action":"s3:GetObject",
"Resource":f"arn:aws:s3:{region}:{acct}:accesspoint/{name}/object/*",
"Condition":{"StringEquals":{"AWS:SourceArn":arn}}}]}))
PY
)
  echo "${POLICY}" > "${WORKDIR}/ap-policy.json"
  aws s3control put-access-point-policy --region "${AWS_REGION}" \
    --account-id "${ACCOUNT_ID}" --name "${FSX_S3AP_NAME}" \
    --policy "file://${WORKDIR}/ap-policy.json"

  mkdir -p "${WORKDIR}"
  { echo "OAC_ID=${OAC_ID}"; echo "DIST_ID=${DIST_ID}"; echo "DIST_DOMAIN=${DIST_DOMAIN}"; } > "${STATE_FILE}"
  echo ">> Created. Distribution deploying (a few minutes). Playback URL:"
  echo "   https://${DIST_DOMAIN}/master.m3u8"
}

cmd_verify() {
  # shellcheck disable=SC1090
  source "${STATE_FILE}"
  echo ">> Waiting for Deployed ..."
  aws cloudfront wait distribution-deployed --region us-east-1 --id "${DIST_ID}"
  for f in master.m3u8 media.m3u8 seg_000.ts; do
    curl -sS -o /dev/null -w "${f} -> HTTP %{http_code} type=%{content_type} size=%{size_download}\n" \
      "https://${DIST_DOMAIN}/${f}"
  done
}

cmd_teardown() {
  # shellcheck disable=SC1090
  source "${STATE_FILE}"
  echo ">> Disabling + deleting CloudFront distribution ${DIST_ID}"
  aws cloudfront get-distribution-config --region us-east-1 --id "${DIST_ID}" --output json > "${WORKDIR}/cur.json"
  ETAG=$(python3 -c "import json;print(json.load(open('${WORKDIR}/cur.json'))['ETag'])")
  python3 - "${WORKDIR}/cur.json" "${WORKDIR}/dis.json" <<'PY'
import json,sys
cur,out=sys.argv[1:3]
d=json.load(open(cur));cfg=d['DistributionConfig'];cfg['Enabled']=False
json.dump(cfg,open(out,'w'))
PY
  aws cloudfront update-distribution --region us-east-1 --id "${DIST_ID}" \
    --distribution-config "file://${WORKDIR}/dis.json" --if-match "${ETAG}" >/dev/null
  aws cloudfront wait distribution-deployed --region us-east-1 --id "${DIST_ID}"
  ETAG2=$(aws cloudfront get-distribution-config --region us-east-1 --id "${DIST_ID}" --query ETag --output text)
  aws cloudfront delete-distribution --region us-east-1 --id "${DIST_ID}" --if-match "${ETAG2}"
  echo ">> Deleting OAC ${OAC_ID}"
  OETAG=$(aws cloudfront get-origin-access-control --region us-east-1 --id "${OAC_ID}" --query ETag --output text)
  aws cloudfront delete-origin-access-control --region us-east-1 --id "${OAC_ID}" --if-match "${OETAG}"
  echo ">> Done. (The FSx for ONTAP S3 AP policy and demo objects are left for you to remove if desired.)"
}

case "${1:-}" in
  gen) cmd_gen ;;
  up) cmd_up ;;
  verify) cmd_verify ;;
  teardown) cmd_teardown ;;
  *) echo "usage: $0 {gen|up|verify|teardown}" >&2; exit 1 ;;
esac
