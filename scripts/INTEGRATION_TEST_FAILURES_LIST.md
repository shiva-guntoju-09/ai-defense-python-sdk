# Integration Test Failures – Full List (to fix)

From the latest full run with `--new-resources`. Use this as the single checklist to fix failures.

---

## 1. Agent framework: Vertex provider (strands, langgraph, langchain)

**Affected:** `strands-agent`, `langgraph-agent`, `langchain-agent` (and likely crewai, autogen, openai if they test Vertex).

**What fails:**
- **Vertex [api]:** MCP tool call NOT executed + "Errors found in output: Traceback (most recent call last):"
- **Vertex [gateway]:** Either "ERROR: cycle failed" (strands) or "Errors found in output: Traceback" (langgraph/langchain). MCP may be executed but output still contains traceback.

**Root cause:** Vertex path in these agents hits an exception or cycle failure; MCP tool execution or agent loop behaves differently than for OpenAI/Azure/Bedrock. Likely Strands/LangGraph/LangChain + Vertex integration or agentsec patching on Vertex.

**Where to look:**
- Agent framework Vertex config: `examples/agentsec/2-agent-frameworks/{strands-agent,langgraph-agent,langchain-agent}/config/config-vertex.yaml`
- Test script checks: `examples/agentsec/2-agent-frameworks/*/tests/integration/` (how they detect "MCP tool call executed" and "Errors in output")
- SDK/framework: Vertex LLM + MCP tool binding or agent loop (e.g. cycle failure in Strands)

**Fix direction:**
- Reproduce locally with Vertex provider only; capture full traceback from log files under each agent's `tests/integration/logs/`.
- Align Vertex agent path with OpenAI/Azure (tool binding, error handling, or agentsec patch for Vertex).
- If "Traceback" in output is from non-fatal logging, consider relaxing the test's "Errors in output" check for known benign stack traces when MCP/LLM passed.

---

## 2. AWS Lambda deploy (SSL)

**Affected:** `amazon-bedrock-agentcore` – Lambda deploy step and therefore Lambda [api] and Lambda [gateway] tests.

**What fails:**
- Lambda deploy fails during `pip install` with `SSLCertVerificationError` (e.g. OSStatus -26276); PyPI unreachable.
- Lambda [api] and [gateway] tests then fail (no/old Lambda, or "No result in Lambda response" / "Security block or Lambda error").

**Root cause:** SSL/certs or network when the deploy script runs (e.g. corporate proxy, macOS certs).

**Where to look:** `examples/agentsec/3-agent-runtimes/amazon-bedrock-agentcore/lambda-deploy/scripts/deploy.sh`

**Fix (already in repo):** Deploy script has a retry with `--trusted-host pypi.org` and `--trusted-host files.pythonhosted.org`. If it still fails:
- Fix system SSL (e.g. Install Certificates.command for Python, or `pip install --upgrade certifi`).
- Ensure network/proxy allows PyPI.

---

## 3. GCP Vertex AI Agent Engine runtime

**Affected:** `gcp-vertex-ai-agent-engine` – full suite (agent-engine, cloud-run, gke, MCP).

**What can fail:**
- **Poetry:** `langchain-google-vertexai (>=2.0.0) which doesn't match any versions` – **Fixed** in main repo (relaxed to `>=2.0.0,<4`, lock regenerated).
- **Auth:** 401 Unauthenticated or 403 ACCESS_TOKEN_SCOPE_INSUFFICIENT – need ADC and scope.
- **Config:** Missing env vars (e.g. `OPENAI_1_GATEWAY_URL`) if `.env` not loaded – **Fixed** by loading `examples/agentsec/.env` (or `.env_venkat`) in `run-integration-tests.sh` before runtime tests.

**Fix (env):**
- Run `gcloud auth application-default login --scopes=https://www.googleapis.com/auth/cloud-platform`.
- Export `GOOGLE_APPLICATION_CREDENTIALS` to your ADC path if needed.
- Ensure `examples/agentsec/.env` exists and has all vars referenced in `agentsec.yaml` (or use `.env_venkat` and script will load it).

---

## 4. Microsoft Foundry (Azure) deploy

**Affected:** `microsoft-foundry` – Foundry Agent App deploy, Azure Functions deploy, Foundry Container deploy (api and gateway each).

**What fails:** Deployment fails with `PermissionError: [Errno 1] Operation not permitted: '.../.azure/az.sess'` – Azure CLI cannot write session file.

**Root cause:** Process cannot write to `~/.azure/` (sandbox, permissions, or read-only home).

**Fix:**
- Run tests from a shell where `az` can write to `~/.azure/` (e.g. `mkdir -p ~/.azure && chmod 700 ~/.azure`).
- Run `az login` if needed.
- In CI/sandbox, ensure the environment allows writes to Azure config directory.

---

## 5. Summary table (what to fix)

| # | Component | Failure | Fix type |
|---|-----------|---------|----------|
| 1 | strands-agent | Vertex [api]: MCP not executed + Traceback; Vertex [gateway]: cycle failed or Traceback | Code: Vertex agent path / test checks |
| 2 | langgraph-agent | Vertex [api] + [gateway]: MCP not executed or Traceback in output | Code: Vertex agent path / test checks |
| 3 | langchain-agent | Vertex [api] + [gateway]: same as above | Code: Vertex agent path / test checks |
| 4 | crewai / autogen / openai | Likely same Vertex pattern if they run Vertex tests | Same as 1–3 once confirmed |
| 5 | AWS Lambda | Deploy SSL error then Lambda tests fail | Env: SSL/certs + retry in deploy script |
| 6 | GCP Vertex runtime | Auth 401/403 or missing .env | Env: ADC + scopes + .env |
| 7 | Microsoft Foundry | az cannot write ~/.azure/az.sess | Env: run where ~/.azure is writable |

---

## 6. Log locations (for debugging)

- **Agent frameworks:** `examples/agentsec/2-agent-frameworks/<agent>/tests/integration/logs/`
- **AWS AgentCore:** `examples/agentsec/3-agent-runtimes/amazon-bedrock-agentcore/tests/integration/logs/` (e.g. `deploy-lambda.log`)
- **GCP Vertex:** `examples/agentsec/3-agent-runtimes/gcp-vertex-ai-agent-engine/tests/integration/logs/`
- **Azure Foundry:** `examples/agentsec/3-agent-runtimes/microsoft-foundry/tests/integration/logs/`

---

## 7. Recommended fix order

1. **Vertex agent frameworks (1–4):** Get full traceback from one agent (e.g. strands) Vertex api log; fix agent or SDK Vertex path; then re-run all agent frameworks.
2. **AWS Lambda (5):** Fix SSL/certs or confirm trusted-host retry; re-run Lambda deploy then Lambda tests.
3. **GCP (6):** Ensure ADC + scopes + .env; re-run GCP runtime tests.
4. **Azure (7):** Run Foundry tests from a shell with writable `~/.azure`.
