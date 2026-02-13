#!/usr/bin/env python3
"""
Cohere client with agentsec protection.

This example demonstrates how to use agentsec with the Cohere Python SDK (v2).
Call agentsec.protect() BEFORE importing the Cohere client.

Usage:
    python cohere_example.py

Environment variables are loaded from ../.env:
    COHERE_API_KEY: Your Cohere API key
    AI_DEFENSE_API_MODE_LLM_API_KEY: Your Cisco AI Defense API key
    AI_DEFENSE_API_MODE_LLM_ENDPOINT: API endpoint URL
"""

import os
import sys
from pathlib import Path

# Allow running from 1-simple without installing the package (add repo root to path)
_here = Path(__file__).resolve().parent
_repo_root = _here.parent.parent.parent
if _repo_root.exists() and (_repo_root / "aidefense").is_dir() and str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

# Load environment variables from shared .env file (optional: requires python-dotenv)
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        print(f"Loaded environment from {env_file}")
except ImportError:
    pass  # Run without dotenv: set env vars manually or use a venv with python-dotenv

# IMPORTANT: Enable protection BEFORE importing Cohere
from aidefense.runtime import agentsec
agentsec.protect(api_mode_llm="monitor")  # Use monitor mode for this example


def main() -> None:
    """Demonstrate Cohere v2 client usage with agentsec protection."""
    patched = agentsec.get_patched_clients()
    print(f"Patched clients: {patched}")

    # Import Cohere AFTER calling protect()
    from cohere import Client, UserChatMessageV2

    api_key = os.environ.get("COHERE_API_KEY")
    if not api_key:
        raise ValueError("COHERE_API_KEY not set. Please check ../.env")

    client = Client(api_key=api_key)
    print("Cohere client ready with agentsec protection")
    print(f"Client patched: {'cohere' in patched}")
    print()

    print("Making API call (will be inspected by Cisco AI Defense)...")
    print()

    response = client.v2.chat(
        model="command-r-plus-08-2024",
        messages=[UserChatMessageV2(content="Say hello in exactly 3 words.")],
    )

    # Extract text from V2ChatResponse (message.content can be list of content items)
    content = response.message.content
    if isinstance(content, list):
        text = " ".join(getattr(item, "text", "") or "" for item in content)
    else:
        text = content or ""
    print(f"Response: {text.strip() or '(empty)'}")
    print()
    print("The call was automatically inspected by Cisco AI Defense!")


if __name__ == "__main__":
    main()
