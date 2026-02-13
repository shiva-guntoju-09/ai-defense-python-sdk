# Integration Test Results – 6 Agent Frameworks

## Results Table

| Framework | Provider | Mode | LLM Protected | MCP Protected | Error | Notes |
|-----------|----------|------|---------------|---------------|-------|-------|
| Strands | openai | api | YES | NO | — | Agent produced final answer |
| Strands | openai | gateway | YES | NO | — | Agent produced final answer |
| Strands | azure | api | — | — | Azure endpoint missing in config | Provider init failed |
| Strands | azure | gateway | — | — | Azure endpoint missing in config | Provider init failed |
| Strands | vertex | api | — | — | tools[0].tool_type proto invalid (Strands+Gemini) | Strands tool format incompatible |
| Strands | vertex | gateway | — | — | tools[0].tool_type proto invalid | Strands tool format incompatible |
| Strands | bedrock | api | YES | NO | — | Agent produced final answer with example.com content |
| Strands | bedrock | gateway | YES | NO | — | Agent produced final answer |
| LangGraph | openai | api | YES | NO | — | Agent produced answer |
| LangGraph | openai | gateway | YES | NO | — | Agent produced answer |
| LangGraph | azure | api | — | — | Azure endpoint missing in config | Provider init failed |
| LangGraph | azure | gateway | — | — | Azure endpoint missing in config | Provider init failed |
| LangGraph | vertex | api | YES | NO | Task destroyed but pending (async cleanup) | Partial success; agent output empty |
| LangGraph | vertex | gateway | YES | NO | google-genai gateway not configured | LLM call blocked |
| LangGraph | bedrock | api | YES | NO | — | Agent produced final answer |
| LangGraph | bedrock | gateway | YES | NO | — | Agent produced final answer |
| LangChain | openai | api | YES | NO | — | Agent produced answer |
| LangChain | openai | gateway | YES | NO | — | Agent produced answer |
| LangChain | azure | api | — | — | Azure endpoint missing in config | Provider init failed |
| LangChain | azure | gateway | — | — | Azure endpoint missing in config | Provider init failed |
| LangChain | vertex | api | YES | NO | Task destroyed but pending | Partial success; agent output empty |
| LangChain | vertex | gateway | YES | NO | Task destroyed but pending | Same as vertex-api |
| LangChain | bedrock | api | YES | NO | — | Agent produced final answer |
| LangChain | bedrock | gateway | YES | NO | — | Agent produced final answer |
| CrewAI | openai | api | YES | NO | — | Crew completed with final answer |
| CrewAI | openai | gateway | YES | NO | — | Crew completed with final answer |
| CrewAI | azure | api | — | — | Azure endpoint missing in config | Provider init failed |
| CrewAI | azure | gateway | — | — | Azure endpoint missing in config | Provider init failed |
| CrewAI | vertex | api | YES | NO | Security policy violation (SECURITY_VIOLATION) in some runs | Complex log; some runs completed |
| CrewAI | vertex | gateway | YES | NO | Invalid request headers (Vertex via LiteLLM gateway) | LLM call failed |
| CrewAI | bedrock | api | YES | NO | — | Crew completed with final answer |
| CrewAI | bedrock | gateway | YES | NO | — | Crew completed with final answer |
| AutoGen | openai | api | YES | NO | — | Agent answered but echoed question as Final Answer |
| AutoGen | openai | gateway | YES | NO | — | Agent answered; Final Answer display echoed question |
| AutoGen | azure | api | — | — | Azure endpoint missing in config | Provider init failed |
| AutoGen | azure | gateway | — | — | Azure endpoint missing in config | Provider init failed |
| AutoGen | vertex | api | YES | NO | ResponseValidationError: Unexpected tool call format (Vertex/Gemini) | Vertex rejected model response |
| AutoGen | vertex | gateway | — | — | (not checked) | — |
| AutoGen | bedrock | api | YES | NO | Response BLOCKED (SECURITY_VIOLATION – Code Detection) | AI Defense blocked response |
| AutoGen | bedrock | gateway | YES | NO | — | Agent produced answer (Final Answer display echoed question) |
| OpenAI Agent | openai | api | YES | NO | — | Agent produced partial answer |
| OpenAI Agent | openai | gateway | YES | NO | — | Agent produced partial answer |
| OpenAI Agent | azure | api | — | — | Azure endpoint missing in config | Provider init failed |
| OpenAI Agent | azure | gateway | — | — | Azure endpoint missing in config | Provider init failed |

---

## Summary

**LLM protection:** All 6 frameworks have LLM calls intercepted by AI Defense when the test runs successfully (provider initialized and LLM invoked). Evidence: `[PATCHED] LLM CALL` in logs.

**MCP protection:** No log showed `[PATCHED] MCP TOOL CALL`. The examples use native function/tool calling (OpenAI tools, framework-specific tools) instead of MCP `ClientSession.call_tool`, so MCP interception was not exercised.

**Recurring issues:**
1. **Azure:** All Azure tests fail with "Azure OpenAI requires 'endpoint' in config" because the endpoint is missing.
2. **Vertex:** Several Vertex tests fail: Strands with `tools[0].tool_type` proto error, LangGraph with "google-genai gateway not configured", LangChain with async cleanup issues, CrewAI with invalid headers or security policy, AutoGen with Vertex response validation.
3. **Bedrock:** Generally successful except AutoGen api mode, where AI Defense blocked the response (Code Detection).
4. **OpenAI:** Most stable; all OpenAI tests ran with LLM protected and agents producing answers.

**Overall:** OpenAI and Bedrock pass most tests. Vertex and Azure have provider/config/gateway compatibility issues across frameworks.
