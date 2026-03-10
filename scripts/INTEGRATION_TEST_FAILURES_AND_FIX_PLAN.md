# Integration Test Failures and Fix Plan

**Source:** Run with `./scripts/run-integration-tests.sh --new-resources`  
**Status:** Simple examples 22/22 passed. Agent frameworks: repeated failures on **Azure [api]**, **Vertex [api]**, and **Vertex [gateway]** across strands-agent, langgraph-agent, and langchain-agent.

---

## 1. Failure Summary

| Framework        | Provider | Mode    | Failed checks                          | Root cause (from logs) |
|-----------------|----------|---------|----------------------------------------|-------------------------|
| strands-agent   | azure    | api     | MCP tool NOT executed, Errors (Traceback) | Azure 401               |
| strands-agent   | vertex   | api     | LLM NOT intercepted, MCP NOT executed, No decisions, Errors | Vertex auth/scope       |
| strands-agent   | vertex   | gateway | LLM NOT intercepted, MCP NOT executed, Errors | Vertex gateway / early fail |
| langgraph-agent | azure    | api     | MCP tool NOT executed, Errors          | Azure 401               |
| langgraph-agent | vertex   | api     | MCP tool NOT executed, Errors          | Vertex RefreshError     |
| langgraph-agent | vertex   | gateway | MCP executed, Gateway OK, but Errors   | Vertex gateway 500      |
| langchain-agent | azure    | api     | MCP tool NOT executed, Errors          | Azure 401               |
| langchain-agent | vertex   | api     | MCP tool NOT executed, Errors          | Vertex RefreshError     |
| langchain-agent | vertex   | gateway | MCP executed, Gateway OK, but Errors   | Vertex gateway 500      |

**Passing:** All **openai** and **bedrock** combinations (api + gateway) pass. **Azure [gateway]** passes (gateway uses different auth/endpoint).

---

## 2. Root Causes (from log analysis)

### 2.1 Azure [api] — 401 AuthenticationError

- **Log:** `openai.AuthenticationError: Error code: 401 - Access denied due to invalid subscription key or wrong API endpoint.`
- **Request:** After AI Defense allows the request, the call goes to `https://aid-ai-runtime.openai.azure.com/...` and Azure returns 401.
- **Cause:** `AZURE_OPENAI_ENDPOINT` and/or `AZURE_OPENAI_API_KEY` in `.env` are invalid for this Azure resource (wrong key, expired, or wrong region/endpoint).
- **Fix:** Update `.env` with valid Azure OpenAI credentials for the resource you intend to use. No code change.

---

### 2.2 Vertex [api] — RefreshError (invalid OAuth scope)

- **Log:** `google.auth.exceptions.RefreshError: ('invalid_scope: Invalid OAuth scope or ID token audience provided.', ...)`
- **Cause:** Agent frameworks use **google-genai** (e.g. `ChatGoogleGenerativeAI` / `gemini-2.5-flash-lite`). ADC (Application Default Credentials) is used with a scope or audience that Vertex/Google rejects.
- **Fix (environment):**
  - Ensure GCP project has Vertex AI API enabled and the service account (or user) has correct roles.
  - Use `gcloud auth application-default login` with the correct project, or set `GOOGLE_APPLICATION_CREDENTIALS` to a service account key that has Vertex AI access and correct OAuth scopes.
  - If using a service account key, ensure the key is for a Vertex AI–enabled project and has not been created with overly restrictive scopes.
- **Optional (tests):** Skip Vertex [api] in CI when ADC/scopes are not configured (e.g. env flag or allowlist of providers).

---

### 2.3 Vertex [gateway] — 500 on second LLM request

- **Log:** First LLM call and MCP tool call succeed; second LLM call (with tool call + tool response in the request body) returns `500 Internal Server Error` from the AI Defense Vertex gateway.
- **Cause:** Known AI Defense gateway limitation. README states: *"Vertex AI gateway 400 Invalid JSON payload: request bodies larger than ~2700 bytes are corrupted during forwarding. Use llm_integration_mode: api for Vertex AI / google-genai until the gateway team resolves this."* The 500 on the larger multi-turn request is consistent with this (gateway cannot handle larger/multi-turn Vertex payloads).
- **Fix options:**
  1. **Documentation:** Keep README/troubleshooting as-is; recommend API mode for Vertex/google-genai when using tool calls / multi-turn.
  2. **Test suite:** Treat Vertex [gateway] as best-effort: either **skip** Vertex gateway in agent-framework integration tests, or add a **known-failure** / skip when the log contains "500 Internal Server Error" for the Vertex gateway URL so CI does not fail on a known backend limitation.
  3. **Backend:** Fix on AI Defense gateway side (out of scope for this repo).

---

## 3. Fix Plan (actionable)

### Phase 1 — Environment / credentials (no code change)

1. **Azure [api]**  
   - Verify the Azure OpenAI resource is active and the key/endpoint in the other repo’s `.env` are still valid.  
   - Update `examples/agentsec/.env`: `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY` (and deployment/version if needed).  
   - Re-run integration tests; Azure [api] should pass once credentials are correct.

2. **Vertex [api]** — **Implemented**  
   - Integration tests source only `examples/agentsec/.env`; ADC must see the service account there.  
   - **Done:** `.env` and `.env.example` now document `GOOGLE_APPLICATION_CREDENTIALS` and `VERTEXAI_1_SA_KEY_FILE`.  
   - **Done:** All agent-framework `test-all-providers.sh` scripts and `run-all-integration-tests.sh` set `GOOGLE_APPLICATION_CREDENTIALS=$VERTEXAI_1_SA_KEY_FILE` when the former is unset and the latter is set and the file exists. So you can set **either** variable in `.env`; setting `VERTEXAI_1_SA_KEY_FILE` to your SA key path is enough for both gateway and framework ADC.  
   - **Your step:** In `examples/agentsec/.env`, set `VERTEXAI_1_SA_KEY_FILE=/path/to/your-service-account.json` (or `GOOGLE_APPLICATION_CREDENTIALS=...`). Ensure `GOOGLE_CLOUD_PROJECT` / `VERTEXAI_1_GCP_PROJECT` match the SA’s project. Re-run; Vertex [api] should pass.

### Phase 2 — Test suite (optional resilience)

3. **Vertex [gateway] known limitation**  
   - **Option A:** In agent-framework integration scripts (`test-all-providers.sh`), add a **skip** for the `vertex` + `gateway` combination (with a comment pointing to README/troubleshooting).  
   - **Option B:** Add a **known-failure** check: if the log contains `500 Internal Server Error` for the Vertex gateway host and the run otherwise shows “Gateway mode communication successful” and “MCP tool call executed”, mark as “known limitation” and do not fail the run.  
   - Prefer Option A for simplicity and to avoid masking real regressions.

### Phase 3 — Documentation

4. **README / troubleshooting**  
   - Ensure troubleshooting table entry for Vertex AI gateway (400/500, large or multi-turn payloads) is visible and recommends API mode for Vertex/google-genai until the gateway is fixed.  
   - Optionally add a short “Integration test environment” section: required env vars, Azure/Vertex credentials, and that Vertex gateway tests may be skipped due to known gateway limitation.

---

## 4. Verification

- After Phase 1: re-run  
  `./scripts/run-integration-tests.sh --new-resources`  
  and confirm Azure [api] and Vertex [api] pass for strands, langgraph, and langchain when credentials are correct.
- After Phase 2: same command; Vertex [gateway] should no longer cause failures (skipped or treated as known limitation).
- No change to passing suites (simple examples, openai, bedrock, Azure gateway) expected.

---

## 5. Log locations (for re-checking)

- strands-agent: `examples/agentsec/2-agent-frameworks/strands-agent/tests/integration/logs/`
- langgraph-agent: `examples/agentsec/2-agent-frameworks/langgraph-agent/tests/integration/logs/`
- langchain-agent: `examples/agentsec/2-agent-frameworks/langchain-agent/tests/integration/logs/`

Example failed log files used for this analysis: `azure-api.log`, `vertex-api.log`, `vertex-gateway.log` (langchain-agent).
