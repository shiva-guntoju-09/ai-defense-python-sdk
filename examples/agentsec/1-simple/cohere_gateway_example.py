#!/usr/bin/env python3
"""
Cohere client with agentsec in Gateway mode.

This example runs the Cohere SDK with Cisco AI Defense Gateway mode:
calls are routed through the gateway (inspection and proxying happen there).

Usage:
    python cohere_gateway_example.py

Set in ../.env:
    AGENTSEC_LLM_INTEGRATION_MODE=gateway
    AGENTSEC_GATEWAY_MODE_LLM=on
    AGENTSEC_COHERE_GATEWAY_URL=https://gateway.../your-tenant/connections/your-cohere-conn
    AGENTSEC_COHERE_GATEWAY_API_KEY=your-cohere-gateway-api-key
    COHERE_API_KEY=your-cohere-api-key  # Still required for client instantiation
"""

import os
import sys
from pathlib import Path

# Allow running from 1-simple without installing the package (add repo root to path)
_here = Path(__file__).resolve().parent
_repo_root = _here.parent.parent.parent
if _repo_root.exists() and (_repo_root / "aidefense").is_dir() and str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        print(f"Loaded environment from {env_file}")
except ImportError:
    pass  # Run without dotenv: set env vars manually or use a venv with python-dotenv

# Enable protection BEFORE importing Cohere (reads gateway config from env)
from aidefense.runtime import agentsec
agentsec.protect()


def main() -> None:
    """Run a Cohere chat call via Cisco AI Defense Gateway."""
    if os.environ.get("AGENTSEC_LLM_INTEGRATION_MODE") != "gateway":
        print("This example is for Gateway mode. Set in .env:")
        print("  AGENTSEC_LLM_INTEGRATION_MODE=gateway")
        print("  AGENTSEC_GATEWAY_MODE_LLM=on")
        print("  AGENTSEC_COHERE_GATEWAY_URL=https://gateway.../...")
        print("  AGENTSEC_COHERE_GATEWAY_API_KEY=your-key")
        return
    gateway_url = os.environ.get("AGENTSEC_COHERE_GATEWAY_URL")
    gateway_key = os.environ.get("AGENTSEC_COHERE_GATEWAY_API_KEY")
    if not gateway_url or not gateway_key:
        print("Cohere gateway not configured. Set in .env:")
        print("  AGENTSEC_COHERE_GATEWAY_URL")
        print("  AGENTSEC_COHERE_GATEWAY_API_KEY")
        return

    patched = agentsec.get_patched_clients()
    print(f"Patched clients: {patched}")

    from cohere import Client, UserChatMessageV2

    api_key = os.environ.get("COHERE_API_KEY")
    if not api_key:
        raise ValueError("COHERE_API_KEY not set. Please check ../.env")

    client = Client(api_key=api_key)
    print("Cohere client ready (Gateway mode – calls routed through Cisco AI Defense Gateway)")
    print(f"Client patched: {'cohere' in patched}")
    print()

    print("Making API call (routed via gateway)...")
    print()

    response = client.v2.chat(
        model="command-r-plus-08-2024",
        messages=[UserChatMessageV2(content="Say hello in exactly 3 words.")],
    )

    content = response.message.content
    if isinstance(content, list):
        text = " ".join(getattr(item, "text", "") or "" for item in content)
    else:
        text = content or ""
    print(f"Response: {text.strip() or '(empty)'}")
    print()
    print("Call was routed through Cisco AI Defense Gateway.")


if __name__ == "__main__":
    main()
