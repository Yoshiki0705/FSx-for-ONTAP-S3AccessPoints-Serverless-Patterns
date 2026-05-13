#!/bin/bash
set -euo pipefail

ONTAP_MGMT="10.0.3.72"
ONTAP_USER="fsxadmin"
ONTAP_PASS="$1"
NLB_IP="$2"
SVM_UUID="9ae87e42-068a-11f1-b1ff-ada95e61ee66"

echo "=== Configuring ONTAP FPolicy ==="
echo "ONTAP: $ONTAP_MGMT"
echo "NLB IP: $NLB_IP"
echo "SVM UUID: $SVM_UUID"

echo ""
echo "--- Checking existing FPolicy policies ---"
curl -sk -u "${ONTAP_USER}:${ONTAP_PASS}" \
  "https://${ONTAP_MGMT}/api/protocols/fpolicy/${SVM_UUID}/policies"

echo ""
echo "--- Creating FPolicy policy ---"
curl -sk -u "${ONTAP_USER}:${ONTAP_PASS}" -X POST \
  "https://${ONTAP_MGMT}/api/protocols/fpolicy/${SVM_UUID}/policies" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"fpolicy_aws\",
    \"enabled\": true,
    \"mandatory\": false,
    \"engine\": {
      \"name\": \"fpolicy_aws_engine\",
      \"type\": \"asynchronous\",
      \"primary_servers\": [\"${NLB_IP}\"],
      \"port\": 9898
    },
    \"events\": [{
      \"name\": \"fpolicy_file_events\",
      \"protocol\": \"cifs\",
      \"file_operations\": {
        \"create\": true,
        \"write\": true,
        \"delete\": true,
        \"rename\": true
      }
    }],
    \"scope\": {
      \"include_volumes\": [\"*\"]
    },
    \"priority\": 1
  }" -w "\nHTTP_CODE:%{http_code}"

echo ""
echo "--- Verifying FPolicy policy ---"
curl -sk -u "${ONTAP_USER}:${ONTAP_PASS}" \
  "https://${ONTAP_MGMT}/api/protocols/fpolicy/${SVM_UUID}/policies/fpolicy_aws"

echo ""
echo "--- Checking FPolicy connections ---"
curl -sk -u "${ONTAP_USER}:${ONTAP_PASS}" \
  "https://${ONTAP_MGMT}/api/protocols/fpolicy/${SVM_UUID}/connections"

echo ""
echo "=== Done ==="
