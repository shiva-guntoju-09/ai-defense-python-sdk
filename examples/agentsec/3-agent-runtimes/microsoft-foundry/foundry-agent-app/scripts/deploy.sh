#!/usr/bin/env bash
# =============================================================================
# Deploy to Azure AI Foundry - Managed Online Endpoint
# =============================================================================
# This script deploys the agent as an Azure AI Foundry managed online endpoint.
#
# Prerequisites:
#   - Azure CLI installed (az)
#   - Azure ML CLI extension (az extension add -n ml)
#   - Logged in to Azure (az login)
#   - Environment variables configured in examples/.env
#
# Usage:
#   ./scripts/deploy.sh
#
# Environment Variables Required:
#   AZURE_SUBSCRIPTION_ID - Azure subscription ID
#   AZURE_RESOURCE_GROUP - Resource group name
#   AZURE_AI_FOUNDRY_PROJECT - AI Foundry project/workspace name
#   AZURE_OPENAI_ENDPOINT - Azure OpenAI endpoint
#   AZURE_OPENAI_API_KEY - Azure OpenAI API key
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEPLOY_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT_DIR="$(cd "$DEPLOY_DIR/.." && pwd)"

cd "$ROOT_DIR"

# Load environment variables from shared examples/.env
EXAMPLES_DIR="$(cd "$ROOT_DIR/.." && pwd)"
if [ -f "$EXAMPLES_DIR/.env" ]; then
    set -a
    source "$EXAMPLES_DIR/.env"
    set +a
fi

# Validate required environment variables
: "${AZURE_SUBSCRIPTION_ID:?AZURE_SUBSCRIPTION_ID is required}"
: "${AZURE_RESOURCE_GROUP:?AZURE_RESOURCE_GROUP is required}"
: "${AZURE_AI_FOUNDRY_PROJECT:?AZURE_AI_FOUNDRY_PROJECT is required}"

# Configuration
ENDPOINT_NAME="${ENDPOINT_NAME:-foundry-sre-agent}"
DEPLOYMENT_NAME="${DEPLOYMENT_NAME:-default}"
INSTANCE_TYPE="${INSTANCE_TYPE:-Standard_DS3_v2}"
INSTANCE_COUNT="${INSTANCE_COUNT:-1}"

echo "=============================================="
echo "Azure AI Foundry - Managed Online Endpoint"
echo "=============================================="
echo "Subscription: $AZURE_SUBSCRIPTION_ID"
echo "Resource Group: $AZURE_RESOURCE_GROUP"
echo "Workspace: $AZURE_AI_FOUNDRY_PROJECT"
echo "Endpoint: $ENDPOINT_NAME"
echo "Deployment: $DEPLOYMENT_NAME"
echo ""

# Set Azure subscription
echo "Setting Azure subscription..."
az account set --subscription "$AZURE_SUBSCRIPTION_ID"

# Copy aidefense SDK source to the deployment directory (includes agentsec at aidefense/runtime/agentsec)
echo "Copying aidefense SDK source..."
AIDEFENSE_SRC="$ROOT_DIR/../../../../aidefense"
if [ -d "$AIDEFENSE_SRC" ]; then
    rm -rf "$DEPLOY_DIR/aidefense" 2>/dev/null || true
    cp -R "$AIDEFENSE_SRC" "$DEPLOY_DIR/"
    echo "Copied aidefense from $AIDEFENSE_SRC"
else
    echo "ERROR: aidefense SDK source not found at $AIDEFENSE_SRC"
    exit 1
fi

# Copy shared code
echo "Copying shared code..."
cp -R "$ROOT_DIR/_shared" "$DEPLOY_DIR/"

# Create endpoint configuration YAML
cat > "$DEPLOY_DIR/endpoint.yaml" << EOF
\$schema: https://azuremlschemas.azureedge.net/latest/managedOnlineEndpoint.schema.json
name: $ENDPOINT_NAME
auth_mode: key
EOF

# Create deployment configuration YAML
cat > "$DEPLOY_DIR/deployment.yaml" << EOF
\$schema: https://azuremlschemas.azureedge.net/latest/managedOnlineDeployment.schema.json
name: $DEPLOYMENT_NAME
endpoint_name: $ENDPOINT_NAME
model:
  path: $DEPLOY_DIR
  type: custom_model
code_configuration:
  code: $DEPLOY_DIR
  scoring_script: app.py
environment:
  image: mcr.microsoft.com/azureml/minimal-python:3.11
  conda_file: null
  inference_config:
    liveness_route:
      path: /health
      port: 8080
    readiness_route:
      path: /health
      port: 8080
    scoring_route:
      path: /score
      port: 8080
instance_type: $INSTANCE_TYPE
instance_count: $INSTANCE_COUNT
environment_variables:
  AZURE_OPENAI_ENDPOINT: "$AZURE_OPENAI_ENDPOINT"
  AZURE_OPENAI_API_KEY: "$AZURE_OPENAI_API_KEY"
  AGENTSEC_LLM_INTEGRATION_MODE: "${AGENTSEC_LLM_INTEGRATION_MODE:-api}"
  AGENTSEC_MCP_INTEGRATION_MODE: "${AGENTSEC_MCP_INTEGRATION_MODE:-api}"
  AGENTSEC_API_MODE_LLM: "${AGENTSEC_API_MODE_LLM:-monitor}"
  AGENTSEC_API_MODE_MCP: "${AGENTSEC_API_MODE_MCP:-monitor}"
  AI_DEFENSE_API_MODE_LLM_ENDPOINT: "${AI_DEFENSE_API_MODE_LLM_ENDPOINT:-}"
  AI_DEFENSE_API_MODE_LLM_API_KEY: "${AI_DEFENSE_API_MODE_LLM_API_KEY:-}"
  MCP_SERVER_URL: "${MCP_SERVER_URL:-}"
EOF

# Create or update endpoint
echo "Creating/updating endpoint..."
if az ml online-endpoint show --name "$ENDPOINT_NAME" \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --workspace-name "$AZURE_AI_FOUNDRY_PROJECT" &>/dev/null; then
    echo "Endpoint exists, updating..."
else
    echo "Creating new endpoint..."
    az ml online-endpoint create \
        --file "$DEPLOY_DIR/endpoint.yaml" \
        --resource-group "$AZURE_RESOURCE_GROUP" \
        --workspace-name "$AZURE_AI_FOUNDRY_PROJECT"
fi

# Create or update deployment
echo "Creating/updating deployment..."
az ml online-deployment create \
    --file "$DEPLOY_DIR/deployment.yaml" \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --workspace-name "$AZURE_AI_FOUNDRY_PROJECT" \
    --all-traffic

# Get endpoint URL
ENDPOINT_URL=$(az ml online-endpoint show \
    --name "$ENDPOINT_NAME" \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --workspace-name "$AZURE_AI_FOUNDRY_PROJECT" \
    --query "scoring_uri" -o tsv)

echo ""
echo "=============================================="
echo "Deployment complete!"
echo "=============================================="
echo "Endpoint URL: $ENDPOINT_URL"
echo ""
echo "Run ./scripts/invoke.sh \"Your message\" to test"
echo "=============================================="
