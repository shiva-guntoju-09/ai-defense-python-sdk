# Integration Test Run Summary (--new-resources, .env_venkat)

**Run:** All integration tests with `--new-resources` and `--deploy`, using `examples/agentsec/.env` (copied from `.env_venkat`).  
**Total runtime:** ~9.5 minutes.

---

## What passed

| Suite | Result |
|-------|--------|
| **Simple Examples** | **22/22 passed** (API + Gateway for all 11 examples) |
| **AWS Amazon Bedrock AgentCore** | Direct [api], Direct [gateway], Container [api], Container [gateway], MCP [api], MCP [gateway] **passed**. Deploy: Direct ✓, Container ✓. |
| **Microsoft Foundry** | MCP Protection [api] and [gateway] **passed**. |

---

## Failures and reasons

### 1. Agent framework tests (5 failed: strands, langgraph, langchain, crewai, autogen, openai)

- **Failure:** Each exited with `Unknown argument: --deploy` and exit code 1.
- **Reason:** The top-level script was passing `--deploy` to `test-all-providers.sh`, but the agent framework test scripts only accept `--verbose`, `--api`, `--gateway`, and provider names. They do not support `--deploy`.
- **Fix applied:** `scripts/run-integration-tests.sh` was updated so that agent framework tests are run with only `$MODE_FLAG` (no `$DEPLOY_FLAG`). Re-run the suite and the agent framework tests should run (and may fail for provider/credential reasons instead of argument error).

---

### 2. Amazon Bedrock AgentCore (1 “suite” failure; 2 test failures within it)

- **Lambda deployment:** **Failed.**  
  - **Reason:** `pip install` during Lambda package build failed with **SSL certificate verification error** (`SSLCertVerificationError`, `OSStatus -26276`) when contacting PyPI. So the Lambda deployment package was never built and the new Lambda (e.g. `agentcore-sre-lambda-20260216-204316`) was not created/updated.  
  - **Log:** `examples/agentsec/3-agent-runtimes/amazon-bedrock-agentcore/tests/integration/logs/deploy-lambda.log`
- **Lambda Deploy [api] and [gateway] tests:** **Failed.**  
  - **Reason:** Lambda deploy failed, so the timestamped Lambda either doesn’t exist or wasn’t updated. Invocations then report “No result in Lambda response” and “Security block or Lambda error found” because the function isn’t the newly built one (or doesn’t return the expected shape).  
- **Fix:** Resolve SSL/certs on the machine that runs Lambda deploy (e.g. run **Install Certificates.command** for Python, or fix proxy/certs so PyPI is reachable). The deploy script already has a retry with `--trusted-host`; if that still fails, fix the environment and re-run.

---

### 3. GCP Vertex AI Agent Engine

- **Failure:** Exited during “Installing dependencies...” with exit code 1.
- **Reason:** **Poetry dependency resolution failed:**  
  `Because gcp-vertex-ai-agent-engine-example depends on langchain-google-vertexai (>=2.0.0) which doesn't match any versions, version solving failed.`
- **Fix:** Update the GCP example’s `pyproject.toml` / `poetry.lock` so that `langchain-google-vertexai>=2.0.0` (or the version you need) is resolvable (correct package name and index), or relax the version constraint if a valid version is available.

---

### 4. Microsoft Foundry (6 deploy-related failures)

- **Failures:**  
  - Foundry Agent App DEPLOY [api] and [gateway]  
  - Azure Functions DEPLOY [api] and [gateway]  
  - Foundry Container DEPLOY [api] and [gateway]  
  All reported “Deployment failed” and point to logs under `microsoft-foundry/tests/integration/logs/`.
- **Reason (from `agent-app-deploy-setup.log`):** **Azure CLI cannot write session file:**  
  `PermissionError: [Errno 1] Operation not permitted: '/Users/shivaguntoju/.azure/az.sess'`  
  So `az` cannot save its session when setting the subscription; deploy fails before any Azure resource is created.
- **Fix:** Run the integration tests from an environment where the Azure CLI can write to `~/.azure/` (e.g. not a read-only or restricted sandbox). Ensure no process or policy is blocking writes to that path.

---

## Summary table

| Component | Status | Reason |
|-----------|--------|--------|
| Simple examples | Passed | All 22 tests passed. |
| Agent frameworks (strands, langgraph, …) | Failed | Script passed `--deploy`; these scripts don’t support it. **Fixed in run-integration-tests.sh.** |
| AWS Direct | Passed | — |
| AWS Container | Passed | Deploy and invocation both passed. |
| AWS Lambda deploy | Failed | PyPI unreachable (SSL cert error). |
| AWS Lambda tests | Failed | Lambda deploy failed, so no/new Lambda to test. |
| AWS MCP | Passed | — |
| GCP Vertex AI Agent Engine | Failed | Poetry: `langchain-google-vertexai (>=2.0.0)` version solving failed. |
| Microsoft Foundry deploy | Failed | `az` cannot write to `~/.azure/az.sess` (permission). |
| Microsoft Foundry MCP | Passed | — |

---

## Next steps

1. **Re-run all integration tests** so agent framework tests run without `--deploy` and any remaining failures are real provider/env issues.
2. **Lambda:** Fix SSL/certs (or network) so Lambda deploy can install dependencies and build the package.
3. **GCP:** Fix `langchain-google-vertexai` dependency/version in the GCP example.
4. **Azure:** Run tests in an environment where `~/.azure/` is writable by the Azure CLI.
