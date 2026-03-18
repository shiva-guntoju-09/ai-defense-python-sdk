#!/usr/bin/env python3
"""
Prompt Category Agent -- Strands agent that manages a local prompt library.

Capabilities (via tools):
  - Fetch prompts by category
  - Add new prompts with auto-categorization
  - AI-driven category matching against existing categories

Usage:
    python agent.py                                   # Interactive mode
    python agent.py "Show me all coding prompts"      # Single question
    python agent.py "Add: Write a haiku about rain"   # Add a prompt

Environment variables (loaded from ../../.env):
    AZURE_OPENAI_API_KEY          Azure OpenAI API key
    AZURE_OPENAI_ENDPOINT         Azure OpenAI endpoint URL
    AZURE_OPENAI_DEPLOYMENT_NAME  Deployment name (default: gpt-4o)
    AZURE_OPENAI_API_VERSION      API version (default: 2024-08-01-preview)

    Optional (agentsec):
    ENABLE_AGENTSEC               Set to "true" to enable AI Defense protection
    AI_DEFENSE_API_MODE_LLM_API_KEY
    AI_DEFENSE_API_MODE_LLM_ENDPOINT
"""

import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 1. Load environment
# ---------------------------------------------------------------------------
from dotenv import load_dotenv

env_file = Path(__file__).parent.parent.parent / ".env"
if env_file.exists():
    load_dotenv(env_file)
    logger.info(f"Loaded environment from {env_file}")

# ---------------------------------------------------------------------------
# 2. Optional agentsec protection (before any LLM imports)
# ---------------------------------------------------------------------------
if os.getenv("ENABLE_AGENTSEC", "").lower() == "true":
    from aidefense.runtime import agentsec

    agentsec.protect(
        llm_integration_mode="api",
        api_mode={
            "llm": {
                "mode": os.getenv("AGENTSEC_LLM_MODE", "monitor"),
                "endpoint": os.getenv("AI_DEFENSE_API_MODE_LLM_ENDPOINT"),
                "api_key": os.getenv("AI_DEFENSE_API_MODE_LLM_API_KEY"),
            }
        },
    )
    logger.info(f"agentsec enabled: {agentsec.get_patched_clients()}")

# ---------------------------------------------------------------------------
# 3. Import Strands and tools (after agentsec.protect if enabled)
# ---------------------------------------------------------------------------
from strands import Agent
from strands.models.openai import OpenAIModel

from tools import add_prompt, categorize_prompt, get_prompts

# ---------------------------------------------------------------------------
# 4. Build the agent
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a Prompt Library Manager. You help users organize and store prompts
in a local library that is grouped by category.

You have three tools:

1. **get_prompts(category)** -- Retrieve all prompts in a category.
2. **categorize_prompt(text, user_category?)** -- Given a prompt text (and an
   optional user-suggested category), return the existing categories with
   examples so you can decide the best fit.
3. **add_prompt(text, category)** -- Save a prompt under a category.

WORKFLOW when the user wants to add a prompt:
  a. Call categorize_prompt with the prompt text (and user_category if given).
  b. Review the existing categories returned.
     - If the prompt clearly fits an existing category, use that category.
     - If the user provided a category and it makes sense, use it.
     - Otherwise suggest a new descriptive category name.
  c. Call add_prompt with the chosen category.
  d. Confirm to the user: the prompt text, assigned category, and ID.

WORKFLOW when the user wants to view prompts:
  a. Call get_prompts with the requested category.
  b. Present the prompts in a readable format.

Always be concise. When listing prompts, number them.
"""


def create_agent() -> Agent:
    """Build a Strands Agent wired to Azure OpenAI and the prompt tools."""
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")

    if not api_key or not endpoint:
        raise ValueError(
            "AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT must be set in ../../.env"
        )

    model = OpenAIModel(
        client_args={
            "api_key": api_key,
            "base_url": f"{endpoint.rstrip('/')}/openai/deployments/{deployment}",
            "default_query": {"api-version": api_version},
            "default_headers": {"api-key": api_key},
        },
        model_id=deployment,
    )

    return Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=[get_prompts, add_prompt, categorize_prompt],
    )


# ---------------------------------------------------------------------------
# 5. Run
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry point: single-question or interactive mode."""
    try:
        agent = create_agent()
    except ValueError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    print()
    print("=" * 50)
    print("  Prompt Category Agent (Strands)")
    print("=" * 50)

    initial_message = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None

    if initial_message:
        print(f"\nYou: {initial_message}")
        try:
            response = agent(initial_message)
            print(f"\nAgent: {response}")
        except Exception as e:
            print(f"\n[ERROR] {type(e).__name__}: {e}")
        return

    print("\nType your message (or 'quit' to exit)")
    print("Examples:")
    print('  "Show me all coding prompts"')
    print('  "Add this prompt: Write a Flask REST API"')
    print('  "Add: Compose a haiku about rain -- category: poetry"')
    print()

    while True:
        try:
            user_input = input("You: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "q"):
                print("Goodbye!")
                break

            response = agent(user_input)
            print(f"\nAgent: {response}\n")

        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"\n[ERROR] {type(e).__name__}: {e}\n")


if __name__ == "__main__":
    main()
