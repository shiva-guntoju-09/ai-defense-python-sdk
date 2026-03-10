# Agent Framework Integration Logs — Failure Details and Next Steps

Summary of failure details pulled from **strands**, **langgraph**, **langchain**, and **autogen** integration logs under `examples/agentsec/2-agent-frameworks/<agent>/tests/integration/logs/`.

---

## 1. GCP dependency fix (done)

- **Location:** `examples/agentsec/3-agent-runtimes/gcp-vertex-ai-agent-engine/pyproject.toml`
- **Change:** `langchain-google-vertexai = ">=2.0.0,<4"`, `langchain-core = ">=0.3.0,<2.0.0"`; `poetry lock` run in that directory.
- **Result:** `poetry install` succeeds (e.g. langchain-google-vertexai 3.2.2, langchain-core 1.2.13). GCP runtime suite can proceed to auth/config steps.

---

## 2. Log availability

- **langchain-agent:** Full set of logs present (vertex-api, vertex-gateway, bedrock-api, bedrock-gateway, openai, azure).
- **autogen-agent:** Vertex logs only (vertex-api.log, vertex-gateway.log).
- **strands-agent / langgraph-agent:** `tests/integration/logs/` is in `.gitignore`, so committed repo has no log files. To get failure details, either re-run the integration tests for those agents or temporarily stop ignoring `logs/` and re-run.

---

## 3. LangChain Agent

### 3.1 Vertex [api] — FAIL

- **Log:** `langchain-agent/tests/integration/logs/vertex-api.log`
- **Error:**  
  `google.auth.exceptions.RefreshError: ('invalid_scope: Invalid OAuth scope or ID token audience provided.', {'error': 'invalid_scope', 'error_description': 'Invalid OAuth scope or ID token audience provided.'})`
- **Cause:** In API (direct) mode the agent uses **google-genai** (ChatGoogleGenerativeAI) with ADC. Token refresh fails because the credentials (service account or user) do not have the correct OAuth scope for the Generative Language API.
- **Next steps:**
  1. For **service account:** Ensure the SA has a scope that includes Generative Language API (e.g. `https://www.googleapis.com/auth/generative-language` or `https://www.googleapis.com/auth/cloud-platform`). When using `gcloud auth application-default login`, use `--scopes=https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/generative-language`.
  2. Alternatively run Vertex [gateway] for this provider (already passes).

### 3.2 Vertex [gateway] — PASS

- **Log:** `langchain-agent/tests/integration/logs/vertex-gateway.log`
- Gateway path works; MCP tool `fetch` is called; agent returns a correct summary of example.com.

### 3.3 Bedrock [api] / [gateway]

- **bedrock-gateway.log:** PASS (MCP executed, agent responds).
- **bedrock-api.log:** From log snippet, API inspection and Bedrock call proceed; any test failure here is likely environment (e.g. expired AWS token) rather than agentsec.

---

## 4. AutoGen Agent

### 4.1 Vertex [api] — PASS

- **Log:** `autogen-agent/tests/integration/logs/vertex-api.log`
- Uses **VertexAI** (GenerativeModel) in API mode; request/response inspection passes; MCP tool `fetch_url` is executed; agent returns "Example.com is a domain designated for use in documentation examples... TASK_COMPLETE".

### 4.2 Vertex [gateway] — FAIL (MCP not executed)

- **Log:** `autogen-agent/tests/integration/logs/vertex-gateway.log`
- **Behavior:** In gateway mode the first LLM request sent to the AI Defense Gateway contains **only** `contents` (user message). There are **no** `tools` or `tool_config` in the request body, so the model never suggests a tool call. The model replies that it cannot access external websites; the agent never calls `fetch_url`. The run eventually hits "Maximum number of consecutive auto-replies" without MCP being used.
- **Cause:** When agentsec routes Vertex through the gateway, the gateway request is built without tool definitions for this agent flow, so the model has no way to suggest `fetch_url`.
- **Next steps:**
  1. In the Vertex **gateway** path, ensure the first (and subsequent) request(s) to the gateway include **tool definitions** (and optionally tool_config) so the model can suggest MCP tools (e.g. fetch_url).
  2. Align with the Vertex [api] flow (or with LangChain Vertex gateway), where tools are included and the model does suggest tool use.

---

## 5. Strands / LangGraph

- **Strands:** No log files in repo (logs ignored). Failure list reports Vertex [api]: "MCP not executed + Traceback"; Vertex [gateway]: "cycle failed" or Traceback.
- **LangGraph:** No log files in repo. Failure list reports Vertex [api]/[gateway]: "MCP not executed or Traceback in output."
- **Next steps:** Re-run integration tests for strands-agent and langgraph-agent (Vertex provider only is enough), then inspect:
  - `strands-agent/tests/integration/logs/vertex-api.log`, `vertex-gateway.log`
  - `langgraph-agent/tests/integration/logs/vertex-api.log`, `vertex-gateway.log`
  For "cycle failed" (strands), check the agent loop and error handling. For "Traceback in output", determine if the test is failing on a real exception vs. benign stack trace in logs and consider relaxing the "Errors in output" check for known cases.

---

## 6. Summary table

| Agent          | Provider | Mode  | Result | Root cause / next step |
|----------------|----------|-------|--------|-------------------------|
| langchain      | Vertex   | api   | FAIL   | OAuth invalid_scope for google-genai; fix ADC scopes or use gateway. |
| langchain      | Vertex   | gateway | PASS | — |
| langchain      | Bedrock  | gateway | PASS | — |
| autogen        | Vertex   | api   | PASS   | — |
| autogen        | Vertex   | gateway | FAIL | No tools in gateway request; add tool definitions to gateway path. |
| strands        | Vertex   | api/gateway | ?  | No logs in repo; re-run and inspect vertex-*.log. |
| langgraph      | Vertex   | api/gateway | ?  | No logs in repo; re-run and inspect vertex-*.log. |

---

## 7. Recommended fix order

1. **Autogen Vertex [gateway]:** Ensure Vertex gateway request builder includes tools (and tool_config if needed) so the model can suggest fetch_url.
2. **LangChain Vertex [api]:** Fix Google OAuth scope for API mode (ADC scopes or SA permissions for Generative Language API).
3. **Strands / LangGraph:** Re-run Vertex integration, capture logs, then fix "cycle failed" or "Traceback in output" per the new log details.
