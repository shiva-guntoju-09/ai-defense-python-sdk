#!/usr/bin/env bash
# =============================================================================
# Invoke Azure Function
# =============================================================================
# This script invokes the deployed Azure Function.
#
# Prerequisites:
#   - Azure CLI installed (az)
#   - Function app deployed via deploy.sh
#
# Usage:
#   ./scripts/invoke.sh "Check the health of payments service"
#   ./scripts/invoke.sh "Fetch https://example.com and summarize it"
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Load environment variables
EXAMPLES_DIR="$(cd "$ROOT_DIR/.." && pwd)"
if [ -f "$EXAMPLES_DIR/.env" ]; then
    set -a
    source "$EXAMPLES_DIR/.env"
    set +a
fi

# Validate required environment variables
: "${AZURE_FUNCTION_APP_NAME:?AZURE_FUNCTION_APP_NAME is required}"

# Get prompt from argument
PROMPT="${1:-Hello! What can you help me with?}"

echo "=============================================="
echo "Invoking Azure Function"
echo "=============================================="
echo "Function App: $AZURE_FUNCTION_APP_NAME"
echo "Prompt: $PROMPT"
echo ""

# Get function key
FUNCTION_KEY=$(az functionapp keys list \
    --name "$AZURE_FUNCTION_APP_NAME" \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --query "functionKeys.default" -o tsv)

# Function URL
FUNCTION_URL="https://${AZURE_FUNCTION_APP_NAME}.azurewebsites.net/api/invoke?code=$FUNCTION_KEY"

# Invoke function
RESPONSE=$(curl -s -X POST "$FUNCTION_URL" \
    -H "Content-Type: application/json" \
    -d "{\"prompt\": \"$PROMPT\"}")

echo "=============================================="
echo "Response:"
echo "=============================================="
echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
