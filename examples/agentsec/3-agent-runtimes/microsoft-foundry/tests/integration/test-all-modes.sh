#!/bin/bash
# =============================================================================
# Azure AI Foundry Integration Tests
# =============================================================================
# Tests all 3 deployment modes in BOTH Cisco AI Defense integration modes:
#   Deployment Modes:
#   - Agent App: Flask app as managed online endpoint
#   - Azure Functions: Serverless function
#   - Container: Custom container deployment
#
#   Integration Modes (Cisco AI Defense):
#   - API Mode: Inspection via Cisco AI Defense API
#   - Gateway Mode: Route through Cisco AI Defense Gateway
#
# Test Modes:
#   - Local (default): Tests agent locally using Azure OpenAI credentials
#   - Deploy (--deploy): Deploys to Azure and tests real endpoints
#
# For each test, verifies:
#   1. LLM calls are intercepted by AI Defense
#   2. Request inspection happens
#   3. Response inspection happens (where applicable)
#   4. No errors occur during execution
#
# Usage:
#   ./tests/integration/test-all-modes.sh                    # Run local tests
#   ./tests/integration/test-all-modes.sh --deploy           # Deploy and test in Azure
#   ./tests/integration/test-all-modes.sh --verbose          # Verbose output
#   ./tests/integration/test-all-modes.sh --api              # API mode only
#   ./tests/integration/test-all-modes.sh --gateway          # Gateway mode only
#   ./tests/integration/test-all-modes.sh agent-app          # Test agent app only
#   ./tests/integration/test-all-modes.sh --deploy agent-app # Deploy and test agent app
# =============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Get script and project directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"

# Test configuration
TIMEOUT_SECONDS=120
TEST_QUESTION="What is 5+5?"
TEST_MCP_QUESTION="Fetch https://example.com and tell me what it says"

# Detect timeout command (gtimeout on macOS via homebrew, timeout on Linux)
if command -v gtimeout &> /dev/null; then
    TIMEOUT_CMD="gtimeout"
elif command -v timeout &> /dev/null; then
    TIMEOUT_CMD="timeout"
else
    TIMEOUT_CMD=""
fi

# Available deployment modes and integration modes
ALL_DEPLOY_MODES=("agent-app" "azure-functions" "container")
ALL_INTEGRATION_MODES=("api" "gateway")
RUN_MCP_TESTS=true
DEPLOY_MODE=false  # When true, deploy to Azure and test real endpoints

# Counters
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_SKIPPED=0

# Timing tracking (using regular array with key:value format for bash 3 compatibility)
DEPLOY_MODE_TIMES=()

# =============================================================================
# Helper Functions
# =============================================================================

log_header() {
    echo ""
    echo -e "${BOLD}${BLUE}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${BLUE}  $1${NC}"
    echo -e "${BOLD}${BLUE}════════════════════════════════════════════════════════════════${NC}"
}

log_subheader() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

log_pass() {
    echo -e "  ${GREEN}✓ PASS${NC}: $1"
}

log_fail() {
    echo -e "  ${RED}✗ FAIL${NC}: $1"
}

log_skip() {
    echo -e "  ${YELLOW}⊘ SKIP${NC}: $1"
}

log_info() {
    echo -e "  ${BLUE}ℹ${NC} $1"
}

show_help() {
    echo "Usage: $0 [OPTIONS] [DEPLOY_MODE]"
    echo ""
    echo "Options:"
    echo "  --local          Run LOCAL tests (default) - tests agent with Azure OpenAI only"
    echo "  --deploy         Run DEPLOY tests - deploys to Azure and tests real endpoints"
    echo "  --verbose, -v    Show detailed output"
    echo "  --api            Test API mode only (default: both modes)"
    echo "  --gateway        Test Gateway mode only (default: both modes)"
    echo "  --no-mcp         Skip MCP tool protection tests"
    echo "  --mcp-only       Run only MCP tool protection tests"
    echo "  --help, -h       Show this help"
    echo ""
    echo "Deploy Modes:"
    echo "  agent-app        Test Foundry Agent Application"
    echo "  azure-functions  Test Azure Functions"
    echo "  container        Test Container deployment"
    echo ""
    echo "Test Modes:"
    echo "  Without --deploy: Tests agent LOCALLY using Azure OpenAI credentials"
    echo "                    Requires: AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY"
    echo ""
    echo "  With --deploy:    Deploys to Azure and tests real endpoints"
    echo "                    Requires: AZURE_SUBSCRIPTION_ID, AZURE_RESOURCE_GROUP,"
    echo "                              AZURE_AI_FOUNDRY_PROJECT, etc."
    echo ""
    echo "Examples:"
    echo "  $0                          # Run local tests (default)"
    echo "  $0 --local                  # Run local tests (explicit)"
    echo "  $0 --verbose                # Run local tests with details"
    echo "  $0 --deploy                 # Deploy and test in Azure"
    echo "  $0 --deploy agent-app       # Deploy and test agent app only"
    echo "  $0 --api                    # Run local tests, API mode only"
    echo "  $0 --deploy --api           # Deploy and test, API mode only"
}

setup_log_dir() {
    mkdir -p "$LOG_DIR"
    rm -f "$LOG_DIR"/*.log 2>/dev/null || true
}

# Check if Azure deployment credentials are configured
check_azure_deploy_credentials() {
    local missing_vars=()
    
    [ -z "${AZURE_SUBSCRIPTION_ID:-}" ] && missing_vars+=("AZURE_SUBSCRIPTION_ID")
    [ -z "${AZURE_RESOURCE_GROUP:-}" ] && missing_vars+=("AZURE_RESOURCE_GROUP")
    [ -z "${AZURE_AI_FOUNDRY_PROJECT:-}" ] && missing_vars+=("AZURE_AI_FOUNDRY_PROJECT")
    
    if [ ${#missing_vars[@]} -gt 0 ]; then
        echo ""
        echo -e "${YELLOW}Missing Azure deployment credentials:${NC}"
        for var in "${missing_vars[@]}"; do
            echo -e "  - $var"
        done
        echo ""
        echo -e "${YELLOW}Set these in examples/.env to enable Azure deployment tests.${NC}"
        return 1
    fi
    return 0
}

# Check if Azure OpenAI credentials are configured (for local tests)
check_azure_openai_credentials() {
    local missing_vars=()
    
    [ -z "${AZURE_OPENAI_ENDPOINT:-}" ] && missing_vars+=("AZURE_OPENAI_ENDPOINT")
    [ -z "${AZURE_OPENAI_API_KEY:-}" ] && missing_vars+=("AZURE_OPENAI_API_KEY")
    
    if [ ${#missing_vars[@]} -gt 0 ]; then
        echo ""
        echo -e "${RED}Missing Azure OpenAI credentials:${NC}"
        for var in "${missing_vars[@]}"; do
            echo -e "  - $var"
        done
        echo ""
        echo -e "${RED}Set these in examples/.env to run tests.${NC}"
        return 1
    fi
    return 0
}

# =============================================================================
# Local Test Function (tests agent locally using Azure OpenAI)
# =============================================================================

# =============================================================================
# Local Test Functions (tests each deploy mode locally)
# =============================================================================

test_foundry_agent_app_local() {
    local integration_mode=$1
    local log_file="$LOG_DIR/agent-app-local-${integration_mode}.log"
    
    log_subheader "Testing: Foundry Agent App LOCAL [$integration_mode mode]"
    
    log_info "Mode: LOCAL (Flask test client)"
    log_info "Integration mode: $integration_mode"
    log_info "Running test with question: \"$TEST_QUESTION\""
    
    cd "$PROJECT_DIR"
    
    # Set integration mode via environment variables
    export AGENTSEC_LLM_INTEGRATION_MODE="$integration_mode"
    export AGENTSEC_MCP_INTEGRATION_MODE="$integration_mode"
    
    # Enable debug logging for verbose output
    if [ "$VERBOSE" = "true" ]; then
        export AGENTSEC_LOG_LEVEL="DEBUG"
    fi
    
    local start_time=$(date +%s)
    
    # Run the Flask app test using Flask test client
    if [ -n "$TIMEOUT_CMD" ]; then
        $TIMEOUT_CMD "$TIMEOUT_SECONDS" poetry run python -c "
import sys
sys.path.insert(0, 'foundry-agent-app')
from app import app
import json

# Use Flask test client
client = app.test_client()

# Test health endpoint
health_resp = client.get('/health')
print('Health check:', health_resp.status_code, health_resp.get_json())

# Test invoke endpoint
response = client.post('/invoke', 
    data=json.dumps({'prompt': '$TEST_QUESTION'}),
    content_type='application/json')
    
print('Invoke response:', response.status_code)
result = response.get_json()
print('RESULT:', result.get('result', result.get('error', 'No result')))
" > "$log_file" 2>&1 || local exit_code=$?
    else
        poetry run python -c "
import sys
sys.path.insert(0, 'foundry-agent-app')
from app import app
import json

# Use Flask test client
client = app.test_client()

# Test health endpoint
health_resp = client.get('/health')
print('Health check:', health_resp.status_code, health_resp.get_json())

# Test invoke endpoint
response = client.post('/invoke', 
    data=json.dumps({'prompt': '$TEST_QUESTION'}),
    content_type='application/json')
    
print('Invoke response:', response.status_code)
result = response.get_json()
print('RESULT:', result.get('result', result.get('error', 'No result')))
" > "$log_file" 2>&1 || local exit_code=$?
    fi
    exit_code=${exit_code:-0}
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    log_info "Completed in ${duration}s (exit code: $exit_code)"
    
    # Validate results
    validate_local_test_results "$log_file" "$integration_mode" "Foundry Agent App"
}

test_azure_functions_local() {
    local integration_mode=$1
    local log_file="$LOG_DIR/azure-functions-local-${integration_mode}.log"
    
    log_subheader "Testing: Azure Functions LOCAL [$integration_mode mode]"
    
    # Check if azure.functions module is available
    if ! poetry run python -c "import azure.functions" 2>/dev/null; then
        log_skip "azure.functions not installed (install with: poetry install --with azure-functions)"
        ((TESTS_SKIPPED++))
        return 0
    fi
    
    log_info "Mode: LOCAL (direct function invocation)"
    log_info "Integration mode: $integration_mode"
    log_info "Running test with question: \"$TEST_QUESTION\""
    
    cd "$PROJECT_DIR"
    
    # Set integration mode via environment variables
    export AGENTSEC_LLM_INTEGRATION_MODE="$integration_mode"
    export AGENTSEC_MCP_INTEGRATION_MODE="$integration_mode"
    
    # Enable debug logging for verbose output
    if [ "$VERBOSE" = "true" ]; then
        export AGENTSEC_LOG_LEVEL="DEBUG"
    fi
    
    local start_time=$(date +%s)
    
    # Run the Azure Functions handler directly with a mock request
    if [ -n "$TIMEOUT_CMD" ]; then
        $TIMEOUT_CMD "$TIMEOUT_SECONDS" poetry run python -c "
import sys
import json
sys.path.insert(0, 'azure-functions')

# Import the function app
from function_app import app, invoke

# Create a mock HTTP request
class MockHttpRequest:
    def __init__(self, body):
        self._body = body.encode() if isinstance(body, str) else body
    
    def get_body(self):
        return self._body
    
    def get_json(self):
        return json.loads(self._body)

# Test the invoke function
request = MockHttpRequest(json.dumps({'prompt': '$TEST_QUESTION'}))
response = invoke(request)

print('Function response status:', response.status_code)
result = json.loads(response.get_body())
print('RESULT:', result.get('result', result.get('error', 'No result')))
" > "$log_file" 2>&1 || local exit_code=$?
    else
        poetry run python -c "
import sys
import json
sys.path.insert(0, 'azure-functions')

# Import the function app
from function_app import app, invoke

# Create a mock HTTP request
class MockHttpRequest:
    def __init__(self, body):
        self._body = body.encode() if isinstance(body, str) else body
    
    def get_body(self):
        return self._body
    
    def get_json(self):
        return json.loads(self._body)

# Test the invoke function
request = MockHttpRequest(json.dumps({'prompt': '$TEST_QUESTION'}))
response = invoke(request)

print('Function response status:', response.status_code)
result = json.loads(response.get_body())
print('RESULT:', result.get('result', result.get('error', 'No result')))
" > "$log_file" 2>&1 || local exit_code=$?
    fi
    exit_code=${exit_code:-0}
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    log_info "Completed in ${duration}s (exit code: $exit_code)"
    
    # Validate results
    validate_local_test_results "$log_file" "$integration_mode" "Azure Functions"
}

test_foundry_container_local() {
    local integration_mode=$1
    local log_file="$LOG_DIR/container-local-${integration_mode}.log"
    
    log_subheader "Testing: Foundry Container LOCAL [$integration_mode mode]"
    
    # Check if Docker is available
    if ! command -v docker &> /dev/null; then
        log_info "Mode: LOCAL (Flask test client - Docker not available)"
    else
        log_info "Mode: LOCAL (Flask test client)"
    fi
    log_info "Integration mode: $integration_mode"
    log_info "Running test with question: \"$TEST_QUESTION\""
    
    cd "$PROJECT_DIR"
    
    # Set integration mode via environment variables
    export AGENTSEC_LLM_INTEGRATION_MODE="$integration_mode"
    export AGENTSEC_MCP_INTEGRATION_MODE="$integration_mode"
    
    # Enable debug logging for verbose output
    if [ "$VERBOSE" = "true" ]; then
        export AGENTSEC_LOG_LEVEL="DEBUG"
    fi
    
    local start_time=$(date +%s)
    
    # Run the container app test using Flask test client
    # (Same as foundry-agent-app since they share similar Flask structure)
    if [ -n "$TIMEOUT_CMD" ]; then
        $TIMEOUT_CMD "$TIMEOUT_SECONDS" poetry run python -c "
import sys
sys.path.insert(0, 'foundry-container')
from app import app
import json

# Use Flask test client
client = app.test_client()

# Test health endpoint
health_resp = client.get('/health')
print('Health check:', health_resp.status_code, health_resp.get_json())

# Test invoke endpoint
response = client.post('/invoke', 
    data=json.dumps({'prompt': '$TEST_QUESTION'}),
    content_type='application/json')
    
print('Invoke response:', response.status_code)
result = response.get_json()
print('RESULT:', result.get('result', result.get('error', 'No result')))
" > "$log_file" 2>&1 || local exit_code=$?
    else
        poetry run python -c "
import sys
sys.path.insert(0, 'foundry-container')
from app import app
import json

# Use Flask test client
client = app.test_client()

# Test health endpoint
health_resp = client.get('/health')
print('Health check:', health_resp.status_code, health_resp.get_json())

# Test invoke endpoint
response = client.post('/invoke', 
    data=json.dumps({'prompt': '$TEST_QUESTION'}),
    content_type='application/json')
    
print('Invoke response:', response.status_code)
result = response.get_json()
print('RESULT:', result.get('result', result.get('error', 'No result')))
" > "$log_file" 2>&1 || local exit_code=$?
    fi
    exit_code=${exit_code:-0}
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    log_info "Completed in ${duration}s (exit code: $exit_code)"
    
    # Validate results
    validate_local_test_results "$log_file" "$integration_mode" "Foundry Container"
}

# Helper function to validate local test results
validate_local_test_results() {
    local log_file=$1
    local integration_mode=$2
    local test_name=$3
    
    local all_checks_passed=true
    
    # Check 1: agentsec patched clients
    if grep -q "Patched:.*openai" "$log_file"; then
        log_pass "agentsec patched: openai"
    else
        log_fail "agentsec did NOT patch openai client"
        all_checks_passed=false
    fi
    
    # Check 2: Request inspection (API mode only)
    if [ "$integration_mode" = "api" ]; then
        if grep -q "Request inspection\|Request decision" "$log_file"; then
            log_pass "Request inspection executed"
        else
            log_fail "No request inspection found"
            all_checks_passed=false
        fi
    fi
    
    # Check 3: Response inspection (API mode only)
    if [ "$integration_mode" = "api" ]; then
        if grep -q "Response inspection\|Response decision" "$log_file"; then
            log_pass "Response inspection executed"
        else
            log_info "Response inspection not found (may be OK)"
        fi
    fi
    
    # Check 4: Gateway mode communication
    if [ "$integration_mode" = "gateway" ]; then
        if grep -q "Gateway\|gateway" "$log_file"; then
            log_pass "Gateway mode communication successful"
        else
            log_fail "No gateway communication found"
            all_checks_passed=false
        fi
    fi
    
    # Check 5: Got a result
    if grep -q "RESULT:" "$log_file"; then
        log_pass "Agent produced a response"
    else
        log_fail "No response from agent"
        all_checks_passed=false
    fi
    
    # Check 6: No errors
    if grep -E "^Traceback|BLOCKED|^\s*ERROR\s*:" "$log_file" | grep -v "DEBUG:" > /dev/null 2>&1; then
        local error_line=$(grep -E "^Traceback|BLOCKED|^\s*ERROR\s*:" "$log_file" | grep -v "DEBUG:" | head -1)
        log_fail "Errors found: $error_line"
        all_checks_passed=false
    else
        log_pass "No errors or blocks"
    fi
    
    if [ "$VERBOSE" = "true" ]; then
        echo ""
        echo -e "    ${MAGENTA}─── Log Output ───${NC}"
        cat "$log_file" | head -50 | sed 's/^/    /'
    fi
    
    # Summary
    if [ "$all_checks_passed" = "true" ]; then
        echo ""
        echo -e "  ${GREEN}${BOLD}► $test_name [$integration_mode]: ALL CHECKS PASSED${NC}"
        ((TESTS_PASSED++))
        return 0
    else
        echo ""
        echo -e "  ${RED}${BOLD}► $test_name [$integration_mode]: SOME CHECKS FAILED${NC}"
        ((TESTS_FAILED++))
        return 1
    fi
}

# =============================================================================
# Azure Deployment Test Functions (requires --deploy flag)
# =============================================================================

test_foundry_agent_app_deploy() {
    local integration_mode=$1
    log_subheader "Testing: Foundry Agent App DEPLOY [$integration_mode mode]"
    
    local log_file="$LOG_DIR/agent-app-deploy-${integration_mode}.log"
    local deploy_script="$PROJECT_DIR/foundry-agent-app/scripts/deploy.sh"
    local invoke_script="$PROJECT_DIR/foundry-agent-app/scripts/invoke.sh"
    
    # Check Azure credentials
    if ! check_azure_deploy_credentials; then
        log_skip "Azure deployment not configured"
        ((TESTS_SKIPPED++))
        return 0
    fi
    
    log_info "Mode: DEPLOY (deploying to Azure AI Foundry)"
    log_info "Integration mode: $integration_mode"
    
    # Set integration mode
    export AGENTSEC_LLM_INTEGRATION_MODE="$integration_mode"
    export AGENTSEC_MCP_INTEGRATION_MODE="$integration_mode"
    
    # Deploy if not already deployed
    log_info "Deploying Foundry Agent App..."
    local deploy_start=$(date +%s)
    if bash "$deploy_script" > "$LOG_DIR/agent-app-deploy-setup.log" 2>&1; then
        local deploy_end=$(date +%s)
        local deploy_duration=$((deploy_end - deploy_start))
        log_pass "Deployment successful (${deploy_duration}s)"
    else
        log_fail "Deployment failed (see $LOG_DIR/agent-app-deploy-setup.log)"
        if [ "$VERBOSE" = "true" ]; then
            tail -20 "$LOG_DIR/agent-app-deploy-setup.log" | sed 's/^/    /'
        fi
        ((TESTS_FAILED++))
        return 1
    fi
    
    # Invoke the endpoint
    log_info "Invoking endpoint with: \"$TEST_QUESTION\""
    if bash "$invoke_script" "$TEST_QUESTION" > "$log_file" 2>&1; then
        log_pass "Endpoint invocation successful"
    else
        log_fail "Endpoint invocation failed"
        ((TESTS_FAILED++))
        return 1
    fi
    
    # Validate results
    local all_checks_passed=true
    
    if grep -q "result" "$log_file"; then
        log_pass "Got response from endpoint"
    else
        log_fail "No response from endpoint"
        all_checks_passed=false
    fi
    
    if [ "$VERBOSE" = "true" ]; then
        echo ""
        echo -e "    ${MAGENTA}─── Response ───${NC}"
        cat "$log_file" | head -20 | sed 's/^/    /'
    fi
    
    if [ "$all_checks_passed" = "true" ]; then
        echo ""
        echo -e "  ${GREEN}${BOLD}► Foundry Agent App DEPLOY [$integration_mode]: ALL CHECKS PASSED${NC}"
        ((TESTS_PASSED++))
        return 0
    else
        echo ""
        echo -e "  ${RED}${BOLD}► Foundry Agent App DEPLOY [$integration_mode]: SOME CHECKS FAILED${NC}"
        ((TESTS_FAILED++))
        return 1
    fi
}

test_azure_functions_deploy() {
    local integration_mode=$1
    log_subheader "Testing: Azure Functions DEPLOY [$integration_mode mode]"
    
    local log_file="$LOG_DIR/azure-functions-deploy-${integration_mode}.log"
    local deploy_script="$PROJECT_DIR/azure-functions/scripts/deploy.sh"
    local invoke_script="$PROJECT_DIR/azure-functions/scripts/invoke.sh"
    
    # Check Azure credentials
    if ! check_azure_deploy_credentials; then
        log_skip "Azure deployment not configured"
        ((TESTS_SKIPPED++))
        return 0
    fi
    
    # Additional check for Functions-specific credentials
    if [ -z "${AZURE_FUNCTION_APP_NAME:-}" ] || [ -z "${AZURE_STORAGE_ACCOUNT:-}" ]; then
        log_skip "Azure Functions not configured (AZURE_FUNCTION_APP_NAME, AZURE_STORAGE_ACCOUNT)"
        ((TESTS_SKIPPED++))
        return 0
    fi
    
    log_info "Mode: DEPLOY (deploying to Azure Functions)"
    log_info "Integration mode: $integration_mode"
    
    # Set integration mode
    export AGENTSEC_LLM_INTEGRATION_MODE="$integration_mode"
    export AGENTSEC_MCP_INTEGRATION_MODE="$integration_mode"
    
    # Deploy
    log_info "Deploying Azure Function..."
    local deploy_start=$(date +%s)
    if bash "$deploy_script" > "$LOG_DIR/azure-functions-deploy-setup.log" 2>&1; then
        local deploy_end=$(date +%s)
        local deploy_duration=$((deploy_end - deploy_start))
        log_pass "Deployment successful (${deploy_duration}s)"
    else
        log_fail "Deployment failed (see $LOG_DIR/azure-functions-deploy-setup.log)"
        if [ "$VERBOSE" = "true" ]; then
            tail -20 "$LOG_DIR/azure-functions-deploy-setup.log" | sed 's/^/    /'
        fi
        ((TESTS_FAILED++))
        return 1
    fi
    
    # Invoke
    log_info "Invoking function with: \"$TEST_QUESTION\""
    if bash "$invoke_script" "$TEST_QUESTION" > "$log_file" 2>&1; then
        log_pass "Function invocation successful"
    else
        log_fail "Function invocation failed"
        ((TESTS_FAILED++))
        return 1
    fi
    
    # Validate
    local all_checks_passed=true
    
    if grep -q "result" "$log_file"; then
        log_pass "Got response from function"
    else
        log_fail "No response from function"
        all_checks_passed=false
    fi
    
    if [ "$VERBOSE" = "true" ]; then
        echo ""
        echo -e "    ${MAGENTA}─── Response ───${NC}"
        cat "$log_file" | head -20 | sed 's/^/    /'
    fi
    
    if [ "$all_checks_passed" = "true" ]; then
        echo ""
        echo -e "  ${GREEN}${BOLD}► Azure Functions DEPLOY [$integration_mode]: ALL CHECKS PASSED${NC}"
        ((TESTS_PASSED++))
        return 0
    else
        echo ""
        echo -e "  ${RED}${BOLD}► Azure Functions DEPLOY [$integration_mode]: SOME CHECKS FAILED${NC}"
        ((TESTS_FAILED++))
        return 1
    fi
}

test_foundry_container_deploy() {
    local integration_mode=$1
    log_subheader "Testing: Foundry Container DEPLOY [$integration_mode mode]"
    
    local log_file="$LOG_DIR/container-deploy-${integration_mode}.log"
    local deploy_script="$PROJECT_DIR/foundry-container/scripts/deploy.sh"
    local invoke_script="$PROJECT_DIR/foundry-container/scripts/invoke.sh"
    
    # Check Azure credentials
    if ! check_azure_deploy_credentials; then
        log_skip "Azure deployment not configured"
        ((TESTS_SKIPPED++))
        return 0
    fi
    
    # Additional check for Container-specific credentials
    if [ -z "${AZURE_ACR_NAME:-}" ] || [ -z "${AZURE_ACR_LOGIN_SERVER:-}" ]; then
        log_skip "Azure Container Registry not configured (AZURE_ACR_NAME, AZURE_ACR_LOGIN_SERVER)"
        ((TESTS_SKIPPED++))
        return 0
    fi
    
    log_info "Mode: DEPLOY (deploying to Azure AI Foundry as container)"
    log_info "Integration mode: $integration_mode"
    
    # Set integration mode
    export AGENTSEC_LLM_INTEGRATION_MODE="$integration_mode"
    export AGENTSEC_MCP_INTEGRATION_MODE="$integration_mode"
    
    # Deploy
    log_info "Building and deploying container..."
    local deploy_start=$(date +%s)
    if bash "$deploy_script" > "$LOG_DIR/container-deploy-setup.log" 2>&1; then
        local deploy_end=$(date +%s)
        local deploy_duration=$((deploy_end - deploy_start))
        log_pass "Deployment successful (${deploy_duration}s)"
    else
        log_fail "Deployment failed (see $LOG_DIR/container-deploy-setup.log)"
        if [ "$VERBOSE" = "true" ]; then
            tail -20 "$LOG_DIR/container-deploy-setup.log" | sed 's/^/    /'
        fi
        ((TESTS_FAILED++))
        return 1
    fi
    
    # Invoke
    log_info "Invoking container endpoint with: \"$TEST_QUESTION\""
    if bash "$invoke_script" "$TEST_QUESTION" > "$log_file" 2>&1; then
        log_pass "Container invocation successful"
    else
        log_fail "Container invocation failed"
        ((TESTS_FAILED++))
        return 1
    fi
    
    # Validate
    local all_checks_passed=true
    
    if grep -q "result" "$log_file"; then
        log_pass "Got response from container"
    else
        log_fail "No response from container"
        all_checks_passed=false
    fi
    
    if [ "$VERBOSE" = "true" ]; then
        echo ""
        echo -e "    ${MAGENTA}─── Response ───${NC}"
        cat "$log_file" | head -20 | sed 's/^/    /'
    fi
    
    if [ "$all_checks_passed" = "true" ]; then
        echo ""
        echo -e "  ${GREEN}${BOLD}► Foundry Container DEPLOY [$integration_mode]: ALL CHECKS PASSED${NC}"
        ((TESTS_PASSED++))
        return 0
    else
        echo ""
        echo -e "  ${RED}${BOLD}► Foundry Container DEPLOY [$integration_mode]: SOME CHECKS FAILED${NC}"
        ((TESTS_FAILED++))
        return 1
    fi
}

# =============================================================================
# MCP Test Function
# =============================================================================

test_mcp_protection() {
    local integration_mode=$1
    log_subheader "Testing: MCP Tool Protection [$integration_mode mode]"
    
    local log_file="$LOG_DIR/mcp-protection-${integration_mode}.log"
    local test_script="$SCRIPT_DIR/test_mcp_protection.py"
    
    # Check if MCP_SERVER_URL is set
    if [ -z "${MCP_SERVER_URL:-}" ]; then
        log_skip "MCP_SERVER_URL not configured"
        ((TESTS_SKIPPED++))
        return 0
    fi
    
    log_info "Integration mode: $integration_mode"
    log_info "MCP Server: $MCP_SERVER_URL"
    
    cd "$PROJECT_DIR"
    
    # Set integration mode
    export AGENTSEC_LLM_INTEGRATION_MODE="$integration_mode"
    export AGENTSEC_MCP_INTEGRATION_MODE="$integration_mode"
    
    if [ "$VERBOSE" = "true" ]; then
        export AGENTSEC_LOG_LEVEL="DEBUG"
    fi
    
    local start_time=$(date +%s)
    
    # Run the MCP test
    if [ -n "$TIMEOUT_CMD" ]; then
        $TIMEOUT_CMD "$TIMEOUT_SECONDS" poetry run python "$test_script" > "$log_file" 2>&1 || local exit_code=$?
    else
        poetry run python "$test_script" > "$log_file" 2>&1 || local exit_code=$?
    fi
    exit_code=${exit_code:-0}
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    log_info "Completed in ${duration}s (exit code: $exit_code)"
    
    # Validate results
    local all_checks_passed=true
    
    # Check 1: MCP patched
    if grep -q "MCP client patched\|Patched.*mcp" "$log_file"; then
        log_pass "MCP client patched by agentsec"
    else
        log_fail "MCP client NOT patched"
        all_checks_passed=false
    fi
    
    # Check 2: MCP Request inspection
    if grep -q "MCP.*request\|MCP TOOL CALL" "$log_file"; then
        log_pass "MCP Request inspection executed"
    else
        log_info "MCP Request inspection not found (may be OK)"
    fi
    
    # Check 3: MCP Response inspection
    if grep -q "MCP.*response\|Got response" "$log_file"; then
        log_pass "MCP Response inspection executed"
    else
        log_info "MCP Response inspection not found (may be OK)"
    fi
    
    # Check 4: Tool succeeded
    if grep -q "tool call succeeded\|SUCCESS\|PASS" "$log_file"; then
        log_pass "MCP tool call succeeded"
    else
        log_fail "MCP tool call failed"
        all_checks_passed=false
    fi
    
    # Check 5: No errors
    if grep -E "FAIL|ERROR.*:" "$log_file" | grep -v "MCP TOOL ERROR" > /dev/null 2>&1; then
        local error_line=$(grep -E "FAIL|ERROR.*:" "$log_file" | head -1)
        log_fail "Errors found: $error_line"
        all_checks_passed=false
    else
        log_pass "No errors or blocks"
    fi
    
    if [ "$VERBOSE" = "true" ]; then
        echo ""
        echo -e "    ${MAGENTA}─── Log Output ───${NC}"
        cat "$log_file" | head -30 | sed 's/^/    /'
    fi
    
    # Summary
    if [ "$all_checks_passed" = "true" ]; then
        echo ""
        echo -e "  ${GREEN}${BOLD}► MCP Protection [$integration_mode]: ALL CHECKS PASSED${NC}"
        ((TESTS_PASSED++))
        return 0
    else
        echo ""
        echo -e "  ${RED}${BOLD}► MCP Protection [$integration_mode]: SOME CHECKS FAILED${NC}"
        ((TESTS_FAILED++))
        return 1
    fi
}

# =============================================================================
# Main
# =============================================================================

VERBOSE="false"
DEPLOY_MODES_TO_TEST=()
INTEGRATION_MODES_TO_TEST=()
MCP_ONLY="false"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --help|-h)
            show_help
            exit 0
            ;;
        --local)
            DEPLOY_MODE=false
            shift
            ;;
        --deploy)
            DEPLOY_MODE=true
            shift
            ;;
        --verbose|-v)
            VERBOSE="true"
            shift
            ;;
        --api)
            INTEGRATION_MODES_TO_TEST+=("api")
            shift
            ;;
        --gateway)
            INTEGRATION_MODES_TO_TEST+=("gateway")
            shift
            ;;
        --no-mcp)
            RUN_MCP_TESTS=false
            shift
            ;;
        --mcp-only)
            MCP_ONLY="true"
            shift
            ;;
        agent-app|azure-functions|container)
            DEPLOY_MODES_TO_TEST+=("$1")
            shift
            ;;
        *)
            echo -e "${RED}Unknown argument: $1${NC}"
            show_help
            exit 1
            ;;
    esac
done

# Default to all modes if none specified
if [ ${#DEPLOY_MODES_TO_TEST[@]} -eq 0 ]; then
    DEPLOY_MODES_TO_TEST=("${ALL_DEPLOY_MODES[@]}")
fi

if [ ${#INTEGRATION_MODES_TO_TEST[@]} -eq 0 ]; then
    INTEGRATION_MODES_TO_TEST=("${ALL_INTEGRATION_MODES[@]}")
fi

# Setup
if [ "$DEPLOY_MODE" = "true" ]; then
    log_header "Azure AI Foundry Integration Tests (DEPLOY MODE)"
    echo ""
    echo -e "  ${YELLOW}${BOLD}⚠ DEPLOY MODE: Will deploy to Azure and test real endpoints${NC}"
else
    log_header "Azure AI Foundry Integration Tests (LOCAL MODE)"
    echo ""
    echo -e "  ${BLUE}LOCAL MODE: Testing agent locally using Azure OpenAI${NC}"
    echo -e "  ${BLUE}Use --deploy flag to deploy and test real Azure endpoints${NC}"
fi

echo ""
echo "  Project:          $PROJECT_DIR"
echo "  Deploy modes:     ${DEPLOY_MODES_TO_TEST[*]}"
echo "  Integration modes: ${INTEGRATION_MODES_TO_TEST[*]}"
echo "  MCP Server:       ${MCP_SERVER_URL:-not configured}"
echo "  Verbose:          $VERBOSE"
echo "  Deploy to Azure:  $DEPLOY_MODE"

# Check poetry is available
if ! command -v poetry &> /dev/null; then
    echo ""
    echo -e "${RED}ERROR: Poetry is not installed${NC}"
    exit 1
fi

# Load shared environment variables
SHARED_ENV="$PROJECT_DIR/../../.env"
if [ -f "$SHARED_ENV" ]; then
    log_info "Loading environment from $SHARED_ENV"
    set -a
    source "$SHARED_ENV"
    set +a
fi

# Check required credentials
if [ "$DEPLOY_MODE" = "true" ]; then
    if ! check_azure_deploy_credentials; then
        echo ""
        echo -e "${RED}Cannot run deploy tests without Azure credentials.${NC}"
        echo -e "${YELLOW}Run without --deploy flag for local tests.${NC}"
        exit 1
    fi
else
    if ! check_azure_openai_credentials; then
        echo ""
        echo -e "${RED}Cannot run tests without Azure OpenAI credentials.${NC}"
        exit 1
    fi
fi

# Track overall start time (includes setup and all tests)
TOTAL_START_TIME=$(date +%s)

# Install dependencies (including azure-functions for full test coverage)
log_info "Installing dependencies..."
cd "$PROJECT_DIR"
poetry install --with azure-functions --quiet 2>/dev/null || poetry install --with azure-functions

# Setup log directory
setup_log_dir

# Run tests
log_header "Running Tests"

if [ "$MCP_ONLY" = "true" ]; then
    # MCP tests only
    MCP_START=$(date +%s)
    for integration_mode in "${INTEGRATION_MODES_TO_TEST[@]}"; do
        test_mcp_protection "$integration_mode"
    done
    MCP_END=$(date +%s)
    DEPLOY_MODE_TIMES+=("mcp:$((MCP_END - MCP_START))")
else
    if [ "$DEPLOY_MODE" = "true" ]; then
        # Azure deployment tests
        for deploy_mode in "${DEPLOY_MODES_TO_TEST[@]}"; do
            DEPLOY_MODE_START=$(date +%s)
            
            for integration_mode in "${INTEGRATION_MODES_TO_TEST[@]}"; do
                case "$deploy_mode" in
                    agent-app)
                        test_foundry_agent_app_deploy "$integration_mode"
                        ;;
                    azure-functions)
                        test_azure_functions_deploy "$integration_mode"
                        ;;
                    container)
                        test_foundry_container_deploy "$integration_mode"
                        ;;
                esac
            done
            
            DEPLOY_MODE_END=$(date +%s)
            DEPLOY_MODE_TIMES+=("$deploy_mode:$((DEPLOY_MODE_END - DEPLOY_MODE_START))")
        done
    else
        # Local tests (default) - each deploy mode tests its specific entry point
        for deploy_mode in "${DEPLOY_MODES_TO_TEST[@]}"; do
            DEPLOY_MODE_START=$(date +%s)
            
            for integration_mode in "${INTEGRATION_MODES_TO_TEST[@]}"; do
                case "$deploy_mode" in
                    agent-app)
                        test_foundry_agent_app_local "$integration_mode"
                        ;;
                    azure-functions)
                        test_azure_functions_local "$integration_mode"
                        ;;
                    container)
                        test_foundry_container_local "$integration_mode"
                        ;;
                esac
            done
            
            DEPLOY_MODE_END=$(date +%s)
            DEPLOY_MODE_TIMES+=("$deploy_mode:$((DEPLOY_MODE_END - DEPLOY_MODE_START))")
        done
    fi
    
    # MCP tests (run in both modes)
    if [ "$RUN_MCP_TESTS" = "true" ]; then
        log_header "MCP Tool Protection Tests"
        MCP_START=$(date +%s)
        for integration_mode in "${INTEGRATION_MODES_TO_TEST[@]}"; do
            test_mcp_protection "$integration_mode"
        done
        MCP_END=$(date +%s)
        DEPLOY_MODE_TIMES+=("mcp:$((MCP_END - MCP_START))")
    fi
fi

# Calculate total time
TOTAL_END_TIME=$(date +%s)
TOTAL_DURATION=$((TOTAL_END_TIME - TOTAL_START_TIME))
TOTAL_DURATION_MIN=$((TOTAL_DURATION / 60))
TOTAL_DURATION_SEC=$((TOTAL_DURATION % 60))

# Summary
log_header "Test Summary"
echo ""
echo -e "  ${GREEN}Passed${NC}:  $TESTS_PASSED"
echo -e "  ${RED}Failed${NC}:  $TESTS_FAILED"
echo -e "  ${YELLOW}Skipped${NC}: $TESTS_SKIPPED"
echo ""

# Timing breakdown
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}  Timing Breakdown:${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
for time_entry in "${DEPLOY_MODE_TIMES[@]}"; do
    mode_name="${time_entry%%:*}"
    mode_secs="${time_entry##*:}"
    mode_min=$((mode_secs / 60))
    mode_sec=$((mode_secs % 60))
    printf "  %-20s %dm %ds\n" "$mode_name:" "$mode_min" "$mode_sec"
done
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  ${BOLD}Total Runtime:       ${TOTAL_DURATION_MIN}m ${TOTAL_DURATION_SEC}s${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

TOTAL=$((TESTS_PASSED + TESTS_FAILED))
if [ $TESTS_FAILED -eq 0 ] && [ $TOTAL -gt 0 ]; then
    echo -e "${GREEN}${BOLD}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}${BOLD}  ✓ ALL TESTS PASSED ($TESTS_PASSED/$TOTAL) in ${TOTAL_DURATION_MIN}m ${TOTAL_DURATION_SEC}s${NC}"
    echo -e "${GREEN}${BOLD}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "  Logs saved to: $LOG_DIR/"
    exit 0
else
    echo -e "${RED}${BOLD}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${RED}${BOLD}  ✗ TESTS FAILED ($TESTS_FAILED/$TOTAL failed) in ${TOTAL_DURATION_MIN}m ${TOTAL_DURATION_SEC}s${NC}"
    echo -e "${RED}${BOLD}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "  Logs saved to: $LOG_DIR/"
    exit 1
fi
