"""
Strands tools for managing a local prompt library.

Three tools:
  - get_prompts: Fetch prompts by category
  - add_prompt: Write a new prompt under a category
  - categorize_prompt: Determine the best category for a prompt
"""

import json
import logging
from datetime import date
from pathlib import Path
from typing import Optional

from strands.tools import tool

logger = logging.getLogger(__name__)

PROMPTS_FILE = Path(__file__).parent / "prompts.json"


def _load_prompts() -> dict:
    """Load the prompts database from disk."""
    if not PROMPTS_FILE.exists():
        return {}
    with open(PROMPTS_FILE, "r") as f:
        return json.load(f)


def _save_prompts(data: dict) -> None:
    """Write the prompts database back to disk."""
    with open(PROMPTS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _next_id(data: dict) -> int:
    """Return the next available prompt ID across all categories."""
    max_id = 0
    for prompts in data.values():
        for p in prompts:
            if p.get("id", 0) > max_id:
                max_id = p["id"]
    return max_id + 1


@tool
def get_prompts(category: str) -> str:
    """
    Fetch all prompts for a given category.

    Args:
        category: The category name to look up (e.g. 'coding', 'writing').

    Returns:
        A JSON string of prompts in that category, or a message if not found.
    """
    data = _load_prompts()
    key = category.lower().strip()

    if key not in data:
        available = ", ".join(sorted(data.keys())) if data else "none"
        return json.dumps({
            "error": f"Category '{category}' not found.",
            "available_categories": available,
        })

    return json.dumps({
        "category": key,
        "count": len(data[key]),
        "prompts": data[key],
    })


@tool
def add_prompt(text: str, category: str) -> str:
    """
    Add a new prompt under the specified category.

    If the category does not exist yet it will be created automatically.

    Args:
        text: The prompt text to store.
        category: The category to file this prompt under.

    Returns:
        Confirmation with the assigned ID and category.
    """
    data = _load_prompts()
    key = category.lower().strip()

    new_prompt = {
        "id": _next_id(data),
        "text": text.strip(),
        "created": date.today().isoformat(),
    }

    if key not in data:
        data[key] = []
        logger.info(f"Created new category: {key}")

    data[key].append(new_prompt)
    _save_prompts(data)

    return json.dumps({
        "status": "saved",
        "id": new_prompt["id"],
        "category": key,
        "text": new_prompt["text"],
    })


@tool
def categorize_prompt(text: str, user_category: Optional[str] = None) -> str:
    """
    Determine the best category for a prompt.

    This tool loads the existing categories and their sample prompts,
    then returns the information the agent needs to decide:
      - The list of existing categories with example prompts.
      - Whether user_category was provided and if it already exists.

    The agent (LLM) should use this information to pick the right
    category or create a new one.

    Args:
        text: The prompt text to categorize.
        user_category: Optional category suggested by the user.

    Returns:
        A JSON summary of existing categories and the user suggestion.
    """
    data = _load_prompts()

    category_summaries = {}
    for cat, prompts in data.items():
        category_summaries[cat] = {
            "count": len(prompts),
            "examples": [p["text"] for p in prompts[:3]],
        }

    result = {
        "prompt_to_categorize": text.strip(),
        "existing_categories": category_summaries,
        "user_suggested_category": user_category.lower().strip() if user_category else None,
        "user_category_exists": (
            user_category.lower().strip() in data if user_category else None
        ),
    }

    return json.dumps(result)
