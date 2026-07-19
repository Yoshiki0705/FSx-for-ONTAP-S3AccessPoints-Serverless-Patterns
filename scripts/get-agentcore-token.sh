#!/usr/bin/env bash
# =============================================================================
# get-agentcore-token.sh
#
# Get JWT token from Cognito for AgentCore MCP Gateway (CUSTOM_JWT) authentication.
# Used by Quick Desktop Remote MCP connection.
#
# Usage:
#   # With environment variables
#   export COGNITO_USER_POOL_ID=us-east-1_XXXXXXXXX
#   export COGNITO_CLIENT_ID=your-client-id
#   export COGNITO_CLIENT_SECRET=your-client-secret
#   export COGNITO_USERNAME=quick-test-user
#   export COGNITO_PASSWORD='YourPassword!'
#   ./scripts/get-agentcore-token.sh
#
#   # With .env file
#   source .private/agentcore-env.sh
#   ./scripts/get-agentcore-token.sh
#
# Output:
#   Prints the JWT ID Token and copies to clipboard (macOS pbcopy).
#   Paste into Quick Desktop → Settings → Connectors → MCP Server → Token field.
#
# Token validity: 1 hour (default Cognito setting)
# =============================================================================
set -euo pipefail

# --- Configuration (override via environment variables) ---
USER_POOL_ID="${COGNITO_USER_POOL_ID:?Set COGNITO_USER_POOL_ID}"
CLIENT_ID="${COGNITO_CLIENT_ID:?Set COGNITO_CLIENT_ID}"
CLIENT_SECRET="${COGNITO_CLIENT_SECRET:?Set COGNITO_CLIENT_SECRET}"
USERNAME="${COGNITO_USERNAME:?Set COGNITO_USERNAME}"
PASSWORD="${COGNITO_PASSWORD:?Set COGNITO_PASSWORD}"
REGION="${COGNITO_REGION:-us-east-1}"

# --- Calculate SECRET_HASH ---
SECRET_HASH=$(printf '%s' "${USERNAME}${CLIENT_ID}" | \
  openssl dgst -sha256 -hmac "${CLIENT_SECRET}" -binary | base64)

# --- Get token via Cognito InitiateAuth ---
echo "[INFO] Authenticating as ${USERNAME} against User Pool ${USER_POOL_ID}..."

RESPONSE=$(aws cognito-idp initiate-auth \
  --auth-flow USER_PASSWORD_AUTH \
  --client-id "$CLIENT_ID" \
  --auth-parameters "USERNAME=${USERNAME},PASSWORD=${PASSWORD},SECRET_HASH=${SECRET_HASH}" \
  --region "$REGION" \
  --output json 2>&1)

if echo "$RESPONSE" | grep -q "error\|Error\|ERROR"; then
  echo "[ERROR] Authentication failed:"
  echo "$RESPONSE"
  exit 1
fi

# --- Extract ID Token ---
ID_TOKEN=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['AuthenticationResult']['IdToken'])")
EXPIRES_IN=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['AuthenticationResult']['ExpiresIn'])")

echo ""
echo "=== AgentCore MCP Gateway JWT Token ==="
echo "  Valid for: ${EXPIRES_IN} seconds ($(( EXPIRES_IN / 60 )) minutes)"
echo "  Token length: ${#ID_TOKEN} chars"
echo ""
echo "--- Quick Desktop Remote MCP Settings ---"
echo "  Name:  EDA Log Analyzer"
echo "  URL:   https://eda-mcp-oauth-3q1yzkfshb.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp"
echo "  Token: (copied to clipboard)"
echo ""

# Copy to clipboard (macOS)
if command -v pbcopy &> /dev/null; then
  echo -n "$ID_TOKEN" | pbcopy
  echo "[OK] Token copied to clipboard. Paste into Quick Desktop Token field."
else
  echo "[INFO] Token (paste manually):"
  echo "$ID_TOKEN"
fi
