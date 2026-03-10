# Agent Runtime Integration Test — Failure Reasons and Fixes

After running:
```bash
./scripts/run-integration-tests.sh --runtimes --deploy --new-resources
```
tests can still fail for the reasons below. **Deployments** (Lambda, Direct, Container, Agent Engine) may succeed; **invocations** or **assertions** then fail.

---

## 1. Amazon Bedrock AgentCore

### 1.1 Direct Deploy [api] — "No AI Defense API response found"
- **Cause:** The test script greps the **invoke log** for strings like `AI Defense response`, `'action': 'Allow'`, `Integration: api`, or `llm_integration=api`. The Direct agent’s **stdout/log** doesn’t contain one of these patterns (e.g. logging format differs or output is truncated).
- **Fix:** Either (a) ensure the Direct agent (or invoke script) logs one of those strings when running in API mode, or (b) relax the test to accept alternative indicators of API-mode inspection (e.g. “Request inspection” + “Response inspection” without requiring the exact phrase “AI Defense response”).

### 1.2 Lambda **deployment** fails — SSL/cert errors when installing dependencies
- **Cause:** During `lambda-deploy/scripts/deploy.sh`, `pip install -r requirements.txt` fails with `SSLCertVerificationError` (e.g. `OSStatus -26276` on macOS, or corporate proxy/custom certs). Pip cannot reach PyPI, so the Lambda package is never built.
- **Fix:** (1) The deploy script **retries** pip with `--trusted-host pypi.org --trusted-host files.pythonhosted.org` when the first attempt fails. (2) If it still fails, fix system certs (e.g. run **Install Certificates.command** from your Python 3.x application folder, or `pip install --upgrade certifi`). (3) Ensure outbound HTTPS to PyPI is allowed.

### 1.3 Container Deploy [api] / [gateway] — "Container invocation failed", "An error occurred when starting the runtime"
- **Cause:** The Bedrock AgentCore **container runtime** fails to start. Common causes: (1) **Missing config in image** — the container did not include `agentsec.yaml` or `.env`, so `agent_factory` could not load gateway/API config or credentials at startup. (2) Missing env (Bedrock region, AI Defense config). (3) Import/runtime error (e.g. missing dependency like `tenacity`). (4) Timeout before the app listens on the expected port.
- **Fix:** (1) Ensure the container image is built with **agentsec.yaml** and **.env** in `/app/` (see `container-deploy/scripts/deploy.sh` and `container-deploy/Dockerfile` — deploy copies these into the build context and the Dockerfile COPYs them). (2) Check **CloudWatch** for the container runtime's log group (e.g. `/aws/bedrock-agentcore/runtimes/<agent-name>-<suffix>-DEFAULT`) using the `aws logs tail ...` command from the test output. (3) Ensure `tenacity` is in container requirements if using strands-agents.

### 1.4 Lambda Deploy [api] / [gateway] — "No result in Lambda response", "Security block or Lambda error found"
- **Cause:** (1) Lambda **deploy** failed (see §1.2), so the new-named function was never created/updated; invoke then fails or returns an error body. (2) Lambda returns a body that doesn’t include the key the test expects (e.g. `result`). (3) CloudWatch shows a traceback or security block.
- **Fix:** If deploy failed, fix Lambda deploy first (SSL/certs per §1.2). Then inspect the Lambda's CloudWatch log group and any saved response (e.g. `/tmp/lambda_response.json`). Ensure the Lambda returns a JSON object with the field the test checks (e.g. `result`). For gateway mode, ensure the function has gateway URL and key in its environment.json` and the Lambda’s CloudWatch log group after the test. Ensure the Lambda returns a JSON object with the field the test checks (e.g. `result`). If the Lambda uses gateway mode, ensure it has gateway URL and key in its environment (see Azure section for same idea).

---

## 2. GCP Vertex AI Agent Engine

### 2.1 Agent Engine [api] / [gateway] — 403 ACCESS_TOKEN_SCOPE_INSUFFICIENT
- **Error:** `403 Request had insufficient authentication scopes. [reason: "ACCESS_TOKEN_SCOPE_INSUFFICIENT" service: "generativelanguage.googleapis.com" method: "google.ai.generativelanguage.v1beta.GenerativeService.GenerateContent"]`
- **Cause:** The **Vertex AI Reasoning Engine** (the deployed agent) runs with a **runtime identity** (service account) that does **not** have the **Generative Language API** scope. When the agent calls Gemini (`GenerateContent`), GCP returns 403. This is **not** your local credentials; it’s the SA used by the Reasoning Engine in the cloud.
- **Fix:** In GCP, grant the **Reasoning Engine’s service account** (or the default compute SA for the agent engine) the scope for **Generative Language API** (e.g. role “Vertex AI User” or add `https://www.googleapis.com/auth/generative-language`). In IAM: Project → IAM → find the SA used by the Reasoning Engine → add appropriate role (e.g. “Vertex AI User”) or custom role with that scope.

### 2.2 Cloud Run [api] / [gateway] — Docker and gcloud
- **Errors:**
  - `Cannot connect to the Docker daemon at unix:///Users/shivaguntoju/.docker/run/docker.sock. Is the docker daemon running?`
  - `PermissionError: ... /Users/shivaguntoju/.config/gcloud/credentials.db ... Operation not permitted`
  - `Project 'gcp-aiteamgcp-nprd-22046' lacks an 'environment' tag`
- **Cause:** (1) **Docker** is not running or the socket path is wrong. (2) **gcloud** cannot write to `~/.config/gcloud` (e.g. permission or read-only filesystem). (3) GCP project requires an **environment** tag for some operations.
- **Fix:** (1) Start Docker Desktop (or your Docker daemon) and ensure the default socket is available. (2) Run the test from a terminal where gcloud can write to `~/.config/gcloud` (e.g. not a restricted sandbox). (3) Add project tag: `gcloud resource-manager tags bindings create ...` as in the error link.

### 2.3 GKE — "Cluster API not reachable", "Master Authorized Networks"
- **Cause:** Your IP is not in the GKE cluster’s **Master Authorized Networks**.
- **Fix:** Add your IP to the cluster’s authorized networks, or run from a network that is already allowed (e.g. VPN). See: `./gke-deploy/scripts/deploy.sh setup`.

---

## 3. Microsoft Foundry (Azure)

### 3.1 Azure Functions — HTTP 500 "Gateway mode is active but no gateway configuration found for provider 'azure_openai'"
- **Cause:** The Function App is set to **gateway** integration mode (via `AGENTSEC_LLM_INTEGRATION_MODE=gateway` when the test runs “gateway mode”). The agentsec SDK then looks for an `azure_openai` gateway in config, but the **Function App’s application settings** do **not** include the gateway URL (`AZURE_OPENAI_1_GATEWAY_URL`) or the config is not loaded. So the function has “gateway on” but no gateway URL.
- **Fix:** When deploying the Azure Function for **gateway** mode, add the gateway URL (and key if needed) to the function app settings, e.g.:
  - `AZURE_OPENAI_1_GATEWAY_URL=<your-azure-openai-gateway-url>`
  - `AZURE_OPENAI_API_KEY=<key-used-by-gateway>` (if required by gateway auth)
  Update the deploy script to pass these from `.env` into `az functionapp config appsettings set` so the function has them at runtime.

### 3.2 Foundry Agent App / Foundry Container — "Deployment failed"
- **Cause:** Usually **Docker** (build/push), **Azure CLI** (e.g. `az login` or writing `~/.azure`), or **ACR/ML** resource creation. Check the referenced log files.
- **Fix:** Ensure Docker is running; run from a shell where `az` can write to `~/.azure`; ensure ACR and ML workspace exist and the SA has permission.

---

## Summary Table

| Runtime              | Failure                                      | Main cause                                      | Fix |
|----------------------|----------------------------------------------|-------------------------------------------------|-----|
| AWS Direct [api]     | No AI Defense API response found             | Log doesn’t contain expected grep pattern       | Align logging or relax test |
| AWS Container       | Invocation failed; "error when starting the runtime" | Runtime fails to start in AgentCore    | Check CloudWatch log group for container runtime; fix env/imports |
| AWS Lambda deploy   | pip SSL/cert error; no package built        | PyPI unreachable (cert/proxy)          | Deploy script retries with --trusted-host; or fix certs / Install Certificates.command |
| AWS Lambda          | No result; security block or error          | Deploy failed (see above) or response shape or CloudWatch error | Fix deploy first; then Lambda response shape and env (gateway URL if gateway mode) |
| GCP Agent Engine     | 403 ACCESS_TOKEN_SCOPE_INSUFFICIENT          | Reasoning Engine SA missing Generative Language scope | Grant SA scope/role in GCP IAM |
| GCP Cloud Run        | Docker / gcloud permission / project tag     | Docker not running; gcloud write; project tag   | Start Docker; fix gcloud env; add project tag |
| GCP GKE              | Cluster API not reachable                    | IP not in Master Authorized Networks           | Add IP to GKE authorized networks |
| Azure Functions      | 500 no gateway config for azure_openai      | Gateway mode but no gateway URL in app settings | Add AZURE_OPENAI_1_GATEWAY_URL (and key) to function app settings |
| Azure Agent App / Container | Deployment failed                    | Docker / az / ACR / permissions                 | Check logs; Docker; az; permissions |

---

## Quick checks

1. **Docker:** `docker info` (daemon running and socket correct).
2. **GCP Agent Engine 403:** IAM for the Reasoning Engine’s service account → add Vertex AI / Generative Language scope.
3. **Azure Function 500:** Function App → Configuration → Application settings: ensure `AZURE_OPENAI_1_GATEWAY_URL` (and keys) are set when using gateway mode; or force API mode for the function so it doesn’t need a gateway.
