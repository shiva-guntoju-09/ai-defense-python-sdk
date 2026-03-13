#!/usr/bin/env python3
"""
LangChain Streaming Agent with agentsec Security + Multi-Provider Support
==========================================================================

Demonstrates **streaming** LLM responses with agentsec protection.

Key difference from ``agent.py``:
- Uses ``llm.stream()`` instead of ``llm.invoke()`` so tokens print as they
  arrive, giving a much better interactive experience.
- agentsec inspection is **automatic** — the SDK patcher wraps the underlying
  provider's streaming response, accumulates chunks, and inspects
  incrementally + at stream end.  No extra code is needed.

Supported providers (via shared ``_shared/providers``):
- OpenAI
- Azure OpenAI
- Amazon Bedrock (ConverseStream)
- Google Vertex AI

Usage:
    python agent_streaming.py                    # Interactive mode
    python agent_streaming.py "Your question"    # Single question mode

    # Use different providers:
    CONFIG_FILE=config-azure.yaml python agent_streaming.py
    CONFIG_FILE=config-vertex.yaml python agent_streaming.py
    CONFIG_FILE=config-bedrock.yaml python agent_streaming.py
"""

import asyncio
import logging
import os
import sys
import time
from pathlib import Path
from typing import List, Dict, Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

MCP_TIMEOUT = int(os.getenv("MCP_TIMEOUT", "60"))

from dotenv import load_dotenv

shared_env = Path(__file__).parent.parent.parent / ".env"
if shared_env.exists():
    load_dotenv(shared_env)

# ── agentsec integration (before any framework imports) ─────────────────
from aidefense.runtime import agentsec

config_path = str(Path(__file__).parent.parent.parent / "agentsec.yaml")
_protect_kwargs: Dict[str, str] = {}
if os.getenv("AGENTSEC_LLM_INTEGRATION_MODE"):
    _protect_kwargs["llm_integration_mode"] = os.getenv("AGENTSEC_LLM_INTEGRATION_MODE")
if os.getenv("AGENTSEC_MCP_INTEGRATION_MODE"):
    _protect_kwargs["mcp_integration_mode"] = os.getenv("AGENTSEC_MCP_INTEGRATION_MODE")
agentsec.protect(config=config_path, **_protect_kwargs)

from aidefense.runtime.agentsec.exceptions import SecurityPolicyError

print(f"[agentsec] Patched: {agentsec.get_patched_clients()}")

# ── Shared provider infrastructure ──────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _shared import load_config, create_provider, validate_url, URLValidationError

# ── LangChain (import AFTER agentsec.protect()) ────────────────────────
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession
from langchain_core.tools import tool
from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    AIMessageChunk,
    ToolMessage,
    SystemMessage,
)

_mcp_session = None


# ── Tool definitions ────────────────────────────────────────────────────

@tool
def fetch_url(url: str) -> str:
    """Fetch the contents of a URL.

    Args:
        url: The URL to fetch (e.g., 'https://example.com')

    Returns:
        The text content of the URL
    """
    logger.info(f"fetch_url called: url='{url}'")

    try:
        validate_url(url)
    except URLValidationError as e:
        logger.warning(f"URL validation failed: {e}")
        return f"Error: Invalid URL - {e}"

    global _mcp_session
    if _mcp_session is None:
        logger.warning("MCP not connected")
        return "Error: MCP not connected"

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    async def _call_mcp():
        start = time.time()
        result = await _mcp_session.call_tool("fetch", {"url": url})
        content = next(
            (c.text for c in (result.content or []) if hasattr(c, "text")),
            "No content",
        )
        elapsed = time.time() - start
        logger.info(f"Got response ({len(content)} chars) in {elapsed:.1f}s")
        return content

    try:
        return loop.run_until_complete(_call_mcp())
    except Exception as e:
        logger.exception(f"Tool error: {type(e).__name__}: {e}")
        return f"Error: {e}"


# ── Streaming agent loop ────────────────────────────────────────────────

def run_streaming_agent_loop(
    llm_with_tools,
    tools_dict: Dict[str, Any],
    messages: List,
    max_iterations: int = 10,
) -> str:
    """Run the agentic loop with **streaming** LLM responses.

    On the final answer (no tool calls) tokens are printed as they arrive.
    Tool-calling turns use ``invoke()`` because the model must finish
    deciding which tools to call before we can execute them.
    """
    for iteration in range(max_iterations):
        logger.debug(f"Agent iteration {iteration + 1}/{max_iterations}")

        # ── First, try a non-streaming invoke to check for tool calls ───
        response = llm_with_tools.invoke(messages)

        if response.tool_calls:
            messages.append(response)
            for tc in response.tool_calls:
                tool_name = tc["name"]
                tool_args = tc["args"]
                tool_id = tc["id"]
                logger.debug(f"Tool call: {tool_name}({tool_args})")
                if tool_name in tools_dict:
                    try:
                        result = tools_dict[tool_name].invoke(tool_args)
                    except Exception as e:
                        result = f"Error executing tool: {e}"
                else:
                    result = f"Unknown tool: {tool_name}"
                messages.append(ToolMessage(content=str(result), tool_call_id=tool_id))
            continue

        # ── No tool calls → stream the final answer ────────────────────
        # We discard the non-streaming response and re-run with .stream()
        # so the user sees tokens appearing in real-time.
        print("\nAgent: ", end="", flush=True)
        collected = []
        for chunk in llm_with_tools.stream(messages):
            token = chunk.content if hasattr(chunk, "content") else ""
            if token:
                print(token, end="", flush=True)
                collected.append(token)
        print(flush=True)
        return "".join(collected)

    return (
        "I've reached the maximum number of iterations. "
        + (messages[-1].content if messages else "Unable to complete the request.")
    )


# ── Main application ────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a helpful assistant with access to the fetch_url tool.

CRITICAL INSTRUCTIONS:
1. When the user asks to fetch a URL or asks about a webpage, ALWAYS use the fetch_url tool.
2. NEVER guess what a page contains - always use the tool to get actual content.
3. After fetching, summarize the results clearly for the user.

Tool usage: fetch_url(url='https://example.com')"""


async def run_agent(initial_message: str = None):
    """Run the LangChain streaming agent."""
    global _mcp_session

    try:
        config = load_config()
        provider = create_provider(config)
        print(f"[provider] Using: {config.get('provider', 'unknown')} / {provider.model_id}")
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        print("Create a config.yaml or set CONFIG_FILE environment variable")
        return
    except Exception as e:
        print(f"[ERROR] Failed to initialize provider: {e}")
        import traceback
        traceback.print_exc()
        return

    mcp_url = os.getenv("MCP_SERVER_URL")

    # ── Connect to MCP ──────────────────────────────────────────────────
    mcp_context = None
    session_context = None

    if mcp_url:
        logger.info(f"Connecting to MCP server: {mcp_url}")
        try:
            mcp_context = streamablehttp_client(mcp_url, timeout=MCP_TIMEOUT)
            read, write, _ = await mcp_context.__aenter__()
            session_context = ClientSession(read, write)
            _mcp_session = await session_context.__aenter__()
            await _mcp_session.initialize()
            tools_list = await _mcp_session.list_tools()
            logger.info(f"MCP connected. Tools: {[t.name for t in tools_list.tools]}")
        except Exception as e:
            logger.warning(f"MCP connection failed: {e}")
            _mcp_session = None

    # ── Create LLM + bind tools ─────────────────────────────────────────
    llm = provider.get_langchain_llm()
    tools = [fetch_url] if mcp_url else []
    tools_dict = {t.name: t for t in tools}
    llm_with_tools = llm.bind_tools(tools) if tools else llm

    print("\n" + "=" * 60, flush=True)
    print("  LangChain Streaming Agent + agentsec", flush=True)
    print("  (Tokens stream in real-time)", flush=True)
    print("=" * 60, flush=True)

    system_message = SystemMessage(content=SYSTEM_PROMPT)

    # ── Single-message mode ─────────────────────────────────────────────
    if initial_message:
        print(f"\nYou: {initial_message}", flush=True)
        try:
            start = time.time()
            messages = [system_message, HumanMessage(content=initial_message)]
            response = run_streaming_agent_loop(llm_with_tools, tools_dict, messages)
            elapsed = time.time() - start
            logger.debug(f"Agent completed in {elapsed:.1f}s")
        except SecurityPolicyError as e:
            print(f"\n[BLOCKED] {e.decision.action}: {e.decision.reasons}", flush=True)
        except Exception as e:
            print(f"\n[ERROR] {type(e).__name__}: {e}", flush=True)
            import traceback
            traceback.print_exc()
        await cleanup_mcp(session_context, mcp_context)
        return

    # ── Interactive mode ────────────────────────────────────────────────
    print("\nType your message (or 'quit' to exit)", flush=True)
    print("Try: 'Tell me a short story about a robot'\n", flush=True)

    MAX_HISTORY_MESSAGES = 20
    conversation_messages = [system_message]

    while True:
        try:
            user_input = input("You: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "q"):
                print("Goodbye!", flush=True)
                break

            try:
                conversation_messages.append(HumanMessage(content=user_input))
                response_text = run_streaming_agent_loop(
                    llm_with_tools, tools_dict, conversation_messages.copy()
                )
                conversation_messages.append(AIMessage(content=response_text))
                if len(conversation_messages) > MAX_HISTORY_MESSAGES + 1:
                    conversation_messages = [system_message] + conversation_messages[
                        -(MAX_HISTORY_MESSAGES):
                    ]
            except SecurityPolicyError as e:
                print(f"\n[BLOCKED] {e.decision.action}: {e.decision.reasons}", flush=True)
            print(flush=True)

        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!", flush=True)
            break

    await cleanup_mcp(session_context, mcp_context)


async def cleanup_mcp(session_context, mcp_context):
    """Clean up MCP connections gracefully."""
    try:
        if session_context:
            await session_context.__aexit__(None, None, None)
    except Exception as e:
        logger.debug(f"MCP session cleanup: {type(e).__name__}")
    try:
        if mcp_context:
            await mcp_context.__aexit__(None, None, None)
    except Exception as e:
        logger.debug(f"MCP context cleanup: {type(e).__name__}")


def main():
    """Entry point."""
    import warnings

    warnings.filterwarnings("ignore", category=RuntimeWarning)

    import nest_asyncio

    nest_asyncio.apply()

    def exception_handler(loop, context):
        if "exception" in context:
            exc = context["exception"]
            if isinstance(exc, (RuntimeError, asyncio.CancelledError)):
                return
        loop.default_exception_handler(context)

    initial_message = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None

    loop = asyncio.new_event_loop()
    loop.set_exception_handler(exception_handler)
    try:
        loop.run_until_complete(run_agent(initial_message))
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception as e:
            logger.debug(f"Error during async generator shutdown: {e}")
        loop.close()


if __name__ == "__main__":
    main()
