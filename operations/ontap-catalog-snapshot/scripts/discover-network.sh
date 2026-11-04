#!/usr/bin/env bash
# Look up the values the template asks for, so that none of them has to be guessed.
#
#   scripts/discover-network.sh <file-system-id> [region]
#
# Read only: every AWS call is describe-*, list-* or get-*. It creates nothing, changes nothing and
# never reads a secret value (it lists secrets by tag and prints only the name and ARN).
# It stops at the first failed call instead of printing a partial answer.
set -uo pipefail

FS_ID="${1:-}"
REGION="${2:-${AWS_REGION:-${AWS_DEFAULT_REGION:-}}}"
if [[ ! "$FS_ID" =~ ^fs-[0-9a-f]{8,17}$ ]]; then
  echo "usage: $0 <file-system-id> [region]" >&2
  exit 2
fi
if [[ -z "$REGION" ]]; then
  echo "no region: pass it as the second argument or set AWS_REGION" >&2
  exit 2
fi

# Run one AWS call; on failure say which one and stop.
aws_q() {
  local out
  if ! out="$(aws --region "$REGION" "$@" 2>&1)"; then
    echo "FAILED: aws $*" >&2
    echo "$out" >&2
    exit 1
  fi
  printf '%s' "$out"
}

vpc_id="$(aws_q fsx describe-file-systems --file-system-ids "$FS_ID" --query 'FileSystems[0].VpcId' --output text)" || exit 1
mgmt="$(aws_q fsx describe-file-systems --file-system-ids "$FS_ID" --query 'FileSystems[0].OntapConfiguration.Endpoints.Management.DNSName' --output text)" || exit 1
subnets="$(aws_q fsx describe-file-systems --file-system-ids "$FS_ID" --query 'FileSystems[0].SubnetIds' --output text)" || exit 1
enis="$(aws_q fsx describe-file-systems --file-system-ids "$FS_ID" --query 'FileSystems[0].NetworkInterfaceIds' --output text)" || exit 1

if [[ "$mgmt" == "None" || -z "$mgmt" ]]; then
  echo "$FS_ID has no ONTAP management endpoint in $REGION. Is it an FSx for ONTAP file system?" >&2
  exit 1
fi

# shellcheck disable=SC2086  # the ENI ids are a space separated list on purpose
fsx_sgs="$(aws_q ec2 describe-network-interfaces --network-interface-ids $enis --query 'NetworkInterfaces[].Groups[].GroupId' --output text | tr '\t' '\n' | sort -u)" || exit 1
sg_count="$(printf '%s\n' "$fsx_sgs" | grep -c .)"

secrets_ep_raw="$(aws_q ec2 describe-vpc-endpoints \
  --filters "Name=vpc-id,Values=$vpc_id" "Name=service-name,Values=com.amazonaws.$REGION.secretsmanager" \
  --query 'VpcEndpoints[0].Groups[].GroupId' --output text)" || exit 1
secrets_ep_sg="$(printf '%s' "$secrets_ep_raw" | tr '\t' '\n' | grep -v '^None$' | sort -u || true)"
s3_gw="$(aws_q ec2 describe-vpc-endpoints \
  --filters "Name=vpc-id,Values=$vpc_id" "Name=service-name,Values=com.amazonaws.$REGION.s3" "Name=vpc-endpoint-type,Values=Gateway" \
  --query 'VpcEndpoints[0].VpcEndpointId' --output text)" || exit 1
s3_pl="$(aws_q ec2 describe-prefix-lists --filters "Name=prefix-list-name,Values=com.amazonaws.$REGION.s3" \
  --query 'PrefixLists[0].PrefixListId' --output text)" || exit 1
nat="$(aws_q ec2 describe-nat-gateways --filter "Name=vpc-id,Values=$vpc_id" "Name=state,Values=available" \
  --query 'NatGateways[0].NatGatewayId' --output text)" || exit 1
secret_lines="$(aws_q secretsmanager list-secrets \
  --query "SecretList[?Tags[?Key=='FileSystemId' && Value=='$FS_ID']].[Name,ARN]" --output text)"

echo "# Values for $FS_ID in $REGION (read only; nothing was created or changed)"
echo
echo "FileSystemId        = $FS_ID"
echo "ManagementEndpoint  = $mgmt"
echo "VpcId               = $vpc_id"
echo "VpcSubnetIds        = $(printf '%s' "$subnets" | tr '\t' ',')"
echo

echo "## FsxSecurityGroupId (groups on the file system network interfaces)"
if [[ "$sg_count" -eq 1 ]]; then
  echo "FsxSecurityGroupId  = $fsx_sgs"
else
  echo "More than one group is attached. Use the one that already allows HTTPS from your admin hosts:"
  printf '  %s\n' $fsx_sgs
fi
echo

echo "## Secrets Manager"
if [[ -n "$secrets_ep_sg" ]]; then
  echo "A Secrets Manager interface VPC endpoint exists in $vpc_id."
  echo "SecretsEndpointSecurityGroupId = $(printf '%s' "$secrets_ep_sg" | tr '\n' ',' | sed 's/,$//')"
else
  echo "No Secrets Manager VPC endpoint in $vpc_id. Reaching it needs a NAT gateway: AllowOutboundHttpsToInternet=true."
fi
echo

echo "## S3"
if [[ "$s3_gw" != "None" && -n "$s3_gw" ]]; then
  echo "An S3 gateway VPC endpoint exists in $vpc_id ($s3_gw)."
  echo "S3PrefixListId      = $s3_pl"
else
  echo "No S3 gateway VPC endpoint in $vpc_id. Reaching S3 needs a NAT gateway: AllowOutboundHttpsToInternet=true."
fi
echo

echo "## NAT gateway"
if [[ "$nat" != "None" && -n "$nat" ]]; then
  echo "A NAT gateway exists in $vpc_id ($nat). Whether the subnets route to it is not checked here."
else
  echo "No available NAT gateway in $vpc_id."
fi
echo

echo "## Secret for this file system (chosen by the FileSystemId tag, not by name)"
if [[ -z "$secret_lines" ]]; then
  echo "No secret carries the tag FileSystemId=$FS_ID. Do not borrow another file system's secret:"
  echo "every FSx for ONTAP file system uses the user name fsxadmin, and a wrong secret counts as a failed login."
else
  printf '%s\n' "$secret_lines" | while IFS=$'\t' read -r name arn; do
    echo "OntapSecretArn      = $arn   ($name)"
  done
fi
echo
echo "Check, before the first run, that the secret's password is the current one for this file system."
