#!/usr/bin/env bash
# =============================================================================
# Deploy to Azure AI Foundry - Container Deployment
# =============================================================================
# This script builds and deploys the agent as a container to Azure AI Foundry
# using Azure Container Registry (ACR).
#
# Prerequisites:
#   - Azure CLI installed (az)
#   - Azure ML CLI extension (az extension add -n ml)
#   - Docker installed and running
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
#   AZURE_ACR_NAME - Azure Container Registry name
#   AZURE_ACR_LOGIN_SERVER - ACR login server (e.g., myacr.azurecr.io)
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
: "${AZURE_ACR_NAME:?AZURE_ACR_NAME is required}"
: "${AZURE_ACR_LOGIN_SERVER:?AZURE_ACR_LOGIN_SERVER is required}"

# Configuration
IMAGE_NAME="${IMAGE_NAME:-foundry-sre-agent}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
ENDPOINT_NAME="${ENDPOINT_NAME:-foundry-sre-container}"
DEPLOYMENT_NAME="${DEPLOYMENT_NAME:-default}"
INSTANCE_TYPE="${INSTANCE_TYPE:-Standard_DS3_v2}"
INSTANCE_COUNT="${INSTANCE_COUNT:-1}"

FULL_IMAGE_NAME="$AZURE_ACR_LOGIN_SERVER/$IMAGE_NAME:$IMAGE_TAG"

echo "=============================================="
echo "Azure AI Foundry - Container Deployment"
echo "=============================================="
echo "Subscription: $AZURE_SUBSCRIPTION_ID"
echo "Resource Group: $AZURE_RESOURCE_GROUP"
echo "Workspace: $AZURE_AI_FOUNDRY_PROJECT"
echo "ACR: $AZURE_ACR_LOGIN_SERVER"
echo "Image: $FULL_IMAGE_NAME"
echo "Endpoint: $ENDPOINT_NAME"
echo ""

# Set Azure subscription
echo "Setting Azure subscription..."
az account set --subscription "$AZURE_SUBSCRIPTION_ID"

# Copy aidefense SDK source to the build context (includes agentsec at aidefense/runtime/agentsec)
echo "Copying aidefense SDK source to build context..."
AIDEFENSE_SRC="$ROOT_DIR/../../../../aidefense"
if [ -d "$AIDEFENSE_SRC" ]; then
    rm -rf "$ROOT_DIR/aidefense" 2>/dev/null || true
    cp -R "$AIDEFENSE_SRC" "$ROOT_DIR/"
    echo "Copied aidefense from $AIDEFENSE_SRC"
else
    echo "ERROR: aidefense SDK source not found at $AIDEFENSE_SRC"
    exit 1
fi

# Login to ACR
echo "Logging in to ACR..."
az acr login --name "$AZURE_ACR_NAME"

# Build and push the container image using ACR Build
echo "Building and pushing container image..."
az acr build \
    --registry "$AZURE_ACR_NAME" \
    --image "$IMAGE_NAME:$IMAGE_TAG" \
    --file foundry-container/Dockerfile \
    .

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
  path: .
  type: custom_model
environment:
  image: $FULL_IMAGE_NAME
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

# Cleanup
echo "Cleaning up build artifacts..."
rm -rf "$ROOT_DIR/aidefense" 2>/dev/null || true

echo ""
echo "=============================================="
echo "Deployment complete!"
echo "=============================================="
echo "Image: $FULL_IMAGE_NAME"
echo "Endpoint URL: $ENDPOINT_URL"
echo ""
echo "Run ./scripts/invoke.sh \"Your message\" to test"
echo "=============================================="
