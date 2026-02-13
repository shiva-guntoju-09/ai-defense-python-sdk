#!/usr/bin/env python3
"""
Mistral AI client with agentsec in Gateway mode.

This example runs the Mistral SDK with Cisco AI Defense Gateway mode:
calls are routed through the gateway (inspection and proxying happen there).

Usage:
    python mistral_gateway_example.py

Set in ../.env:
    AGENTSEC_LLM_INTEGRATION_MODE=gateway
    AGENTSEC_GATEWAY_MODE_LLM=on
    AGENTSEC_MISTRAL_GATEWAY_URL=https://gateway.../your-tenant/connections/your-mistral-conn
    AGENTSEC_MISTRAL_GATEWAY_API_KEY=your-mistral-gateway-api-key
    MISTRAL_API_KEY=your-mistral-api-key  # Still required for client instantiation
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

# Enable protection BEFORE importing Mistral (reads gateway config from env)
from aidefense.runtime import agentsec
agentsec.protect()


def main() -> None:
    """Run a Mistral chat call via Cisco AI Defense Gateway."""
    if os.environ.get("AGENTSEC_LLM_INTEGRATION_MODE") != "gateway":
        print("This example is for Gateway mode. Set in .env:")
        print("  AGENTSEC_LLM_INTEGRATION_MODE=gateway")
        print("  AGENTSEC_GATEWAY_MODE_LLM=on")
        print("  AGENTSEC_MISTRAL_GATEWAY_URL=https://gateway.../...")
        print("  AGENTSEC_MISTRAL_GATEWAY_API_KEY=your-key")
        return
    gateway_url = os.environ.get("AGENTSEC_MISTRAL_GATEWAY_URL")
    gateway_key = os.environ.get("AGENTSEC_MISTRAL_GATEWAY_API_KEY")
    if not gateway_url or not gateway_key:
        print("Mistral gateway not configured. Set in .env:")
        print("  AGENTSEC_MISTRAL_GATEWAY_URL")
        print("  AGENTSEC_MISTRAL_GATEWAY_API_KEY")
        return

    patched = agentsec.get_patched_clients()
    print(f"Patched clients: {patched}")

    from mistralai import Mistral

    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise ValueError("MISTRAL_API_KEY not set. Please check ../.env")

    client = Mistral(api_key=api_key)
    print("Mistral client ready (Gateway mode – calls routed through Cisco AI Defense Gateway)")
    print(f"Client patched: {'mistral' in patched}")
    print()

    print("Making API call (routed via gateway)...")
    print()

    response = client.chat.complete(
        model="mistral-large-latest",
        messages=[{"role": "user", "content": "Say hello in exactly 3 words."}],
    )

    content = response.choices[0].message.content if response.choices else ""
    print(f"Response: {content or '(empty)'}")
    print()
    print("Call was routed through Cisco AI Defense Gateway.")


if __name__ == "__main__":
    main()
