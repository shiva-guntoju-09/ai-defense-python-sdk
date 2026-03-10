# Plan to Fix Integration Test Failures

This document lists each failure, root cause, and concrete steps to fix.

---

## Full failure list (from run 2026-02-17 with --new-resources)

**Passed:** Simple Examples (22/22), crewai-agent (8/8), openai-agent (4/4), amazon-bedrock-agentcore (8/8), microsoft-foundry (8/8).

**Failed (5):** strands-agent, langgraph-agent, langchain-agent, autogen-agent, gcp-vertex-ai-agent-engine.

### Failures and causes (from script output)

| # | Component | What failed | Cause |
|---|-----------|-------------|--------|
| 1 | **strands-agent** | Vertex [api]: MCP NOT executed + Errors in output (Traceback). Vertex [gateway]: Errors in output (ERROR: cycle failed). | Vertex path in Strands: API mode hits exception (traceback) and MCP is not executed; gateway mode hits "cycle failed" in agent loop. |
| 2 | **langgraph-agent** | Vertex [api] only: MCP NOT executed + Traceback in output. Vertex [gateway] passed. | Vertex + LangGraph in API mode: agent produces traceback and does not execute MCP tool call. |
| 3 | **langchain-agent** | Vertex [api] only: MCP NOT executed + Traceback. Vertex [gateway] passed. | Same as langgraph: Vertex API mode throws or logs traceback; MCP not executed. |
| 4 | **autogen-agent** | Vertex [gateway] only: MCP NOT executed + No Gateway communication found in log. Vertex [api] passed. | Autogen with Vertex in gateway mode: test sees no gateway communication in log and MCP call not executed. |
| 5 | **gcp-vertex-ai-agent-engine** | All 6 LLM tests (agent-engine api/gateway, cloud-run api/gateway, gke api/gateway). MCP tests (10) passed. | **401 Unauthenticated:** Application Default Credentials (ADC) not available. Run without `GOOGLE_APPLICATION_CREDENTIALS` or valid `gcloud auth application-default login`. |

**Log locations:** Agent frameworks: `examples/agentsec/2-agent-frameworks/<agent>/tests/integration/logs/`. AWS: `.../amazon-bedrock-agentcore/tests/integration/logs/`. GCP: `.../gcp-vertex-ai-agent-engine/tests/integration/logs/`. Azure: `.../microsoft-foundry/tests/integration/logs/`.

---

## 1. Agent framework tests (strands, langgraph, langchain, crewai, autogen, openai)

| Item | Detail |
|------|--------|
| **Status** | ✅ **Fixed in repo** |
| **Cause** | Top-level script passed `--deploy` to agent framework test scripts, which only accept `--verbose`, `--api`, `--gateway`. |
| **Fix** | `scripts/run-integration-tests.sh` was updated to pass only `$MODE_FLAG` to agent framework tests (no `$DEPLOY_FLAG`). |
| **Action** | None. Re-run the suite to confirm agent framework tests execute (they may still fail on provider/credentials). |

---

## 2. AWS Lambda deploy (SSL) and Lambda tests

| Item | Detail |
|------|--------|
| **Cause** | During `lambda-deploy/scripts/deploy.sh`, `pip install -r requirements.txt` fails with `SSLCertVerificationError` (e.g. OSStatus -26276 on macOS). PyPI is unreachable, so the Lambda package is never built. |
| **Fix (code)** | Add a **retry with `--trusted-host`** in the Lambda deploy script when the first `pip install` fails (see §2.1 below). |
| **Fix (environment)** | If retry still fails: fix system SSL certificates (e.g. run **Install Certificates.command** from your Python 3.x app folder, or `pip install --upgrade certifi`; on corporate networks, ensure proxy/certs allow PyPI). |
| **Lambda tests** | Will pass once Lambda deploy succeeds (new function is created/updated and returns the expected response shape). |

### 2.1 Implementation: Lambda deploy SSL retry

In `examples/agentsec/3-agent-runtimes/amazon-bedrock-agentcore/lambda-deploy/scripts/deploy.sh`, replace the single `poetry run pip install ...` block with:

- First attempt: current `pip install -r requirements.txt ... --target build/lambda`.
- If that fails: retry with the same options plus `--trusted-host pypi.org --trusted-host files.pythonhosted.org`.
- If the retry fails: print a clear error and exit 1 (suggest fixing certs or network).

---

## 3. GCP Vertex AI Agent Engine (Poetry solve)

| Item | Detail |
|------|--------|
| **Cause** | `poetry install` fails with: `Because gcp-vertex-ai-agent-engine-example depends on langchain-google-vertexai (>=2.0.0) which doesn't match any versions, version solving failed.` |
| **Likely reason** | Stale or inconsistent `poetry.lock`; or resolver can’t find a compatible set (path dependency `cisco-aidefense-sdk` or version constraints). |
| **Fix** | 3.1 Regenerate lock file in the GCP example directory. 3.2 If still failing, relax or pin the LangChain/Vertex dependency. |

### 3.1 Steps

1. **Regenerate lock file**
   ```bash
   cd examples/agentsec/3-agent-runtimes/gcp-vertex-ai-agent-engine
   poetry lock --no-update
   ```
   If that fails, try:
   ```bash
   poetry lock
   ```
2. **If “doesn’t match any versions” persists**, temporarily relax in `pyproject.toml`:
   - e.g. `langchain-google-vertexai = ">=2.0.0,<4.0.0"` (or pin to a known version like `>=2.0.0,<2.1.0`), then run `poetry lock` again.
3. **Ensure path dependency is valid**: `cisco-aidefense-sdk = { path = "../../../..", develop = true }` must point to a directory that contains the SDK (e.g. project root). If the repo layout differs, adjust `path` so `poetry install` can see the SDK.

---

## 4. Microsoft Foundry (Azure CLI permission)

| Item | Detail |
|------|--------|
| **Cause** | `PermissionError: [Errno 1] Operation not permitted: '/Users/<user>/.azure/az.sess'` — Azure CLI cannot write its session file. |
| **Reason** | Process is running in a restricted environment (e.g. sandbox, read-only home, or permission block on `~/.azure/`). |
| **Fix** | Run integration tests in an environment where the Azure CLI can write to `~/.azure/`. |

### 4.1 Steps

1. **Run tests from a normal shell** (not a sandbox that blocks writes to `~/.azure`).
2. **Check permissions**:
   ```bash
   ls -la ~/.azure
   # Ensure the directory exists and is writable; create if needed:
   mkdir -p ~/.azure && chmod 700 ~/.azure
   ```
3. **Re-authenticate** if needed: `az login`.
4. **CI/sandbox**: If tests run in CI or a sandbox, that environment must allow writes to the Azure config directory (or use a different config path if supported by `az`).

---

## 5. Summary checklist

| # | Failure | Fix type | Owner / action |
|---|---------|----------|----------------|
| 1 | Agent frameworks “Unknown argument: --deploy” | Code (done) | Done in `run-integration-tests.sh`. Re-run to confirm. |
| 2 | Lambda deploy SSL error | Code + env | Add trusted-host retry in Lambda `deploy.sh`; fix certs/network if retry fails. |
| 3 | Lambda tests “No result” / “Security block or error” | Follows from #2 | Fix Lambda deploy first. |
| 4 | GCP “langchain-google-vertexai doesn’t match any versions” | Repo (lock + deps) | Run `poetry lock` in GCP example; relax/pin dependency if needed. |
| 5 | Azure “Operation not permitted” on `~/.azure/az.sess` | Environment | Run tests where `az` can write to `~/.azure/`. |

---

## 6. Recommended order of work

1. **Lambda deploy script**: Add SSL retry (trusted-host) so Lambda deploy can succeed despite cert issues where possible.
2. **GCP**: Run `poetry lock` (and optionally relax `langchain-google-vertexai`) in the GCP example so `poetry install` succeeds.
3. **Azure**: Run the full suite (or only Microsoft Foundry) from a shell where `~/.azure` is writable.
4. **Re-run full integration suite** with `--new-resources` and `--deploy` and confirm agent frameworks run and any remaining failures are only env/credential-related.
