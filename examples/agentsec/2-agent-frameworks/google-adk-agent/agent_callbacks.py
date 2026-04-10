#!/usr/bin/env python3
# Copyright 2026 Cisco Systems, Inc. and its affiliates
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0
"""
Google ADK agent with Cisco AI Defense callback-based inspection.

This example demonstrates the **callback approach** — wiring ``LLMInspector``
and ``MCPInspector`` from the agentsec SDK directly into Google ADK's
per-agent callback hooks (``before_model_callback``, ``after_model_callback``,
``before_tool_callback``, ``after_tool_callback``).

Compared to ``agent.py`` (monkey-patching via ``agentsec.protect()``), the
callback approach gives you:
  - Per-agent granularity (different agents can have different policies).
  - Explicit control over what happens on violations (custom responses).
  - Access to the full ``Decision`` object (severity, classifications, rules).

agentsec inspectors used:
  - LLMInspector  — inspects LLM prompts and responses via AI Defense Chat API
  - MCPInspector  — inspects MCP tool calls via AI Defense MCP API

ADK callback signatures:
  - before_model_callback(callback_context, llm_request) -> Optional[LlmResponse]
  - after_model_callback(callback_context, llm_response) -> Optional[LlmResponse]
  - before_tool_callback(tool, args, tool_context) -> Optional[dict]
  - after_tool_callback(tool, args, tool_context, tool_response) -> Optional[dict]

Usage:
    python agent_callbacks.py

Environment variables (loaded from ../../.env):
    AGENTSEC_API_MODE_LLM:     LLM inspection mode  (monitor | enforce | off)
    AGENTSEC_API_MODE_MCP:     MCP inspection mode   (monitor | enforce | off)
    AI_DEFENSE_API_MODE_LLM_API_KEY:   Cisco AI Defense API key (LLM)
    AI_DEFENSE_API_MODE_LLM_ENDPOINT:  AI Defense LLM endpoint
    AI_DEFENSE_API_MODE_MCP_API_KEY:   Cisco AI Defense API key (MCP)
    AI_DEFENSE_API_MODE_MCP_ENDPOINT:  AI Defense MCP endpoint
    GOOGLE_API_KEY or GOOGLE_CLOUD_PROJECT: Gemini authentication
    MCP_SERVER_URL:             Remote MCP server URL (StreamableHTTP)
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

env_file = Path(__file__).resolve().parent.parent.parent / ".env"
if env_file.exists():
    load_dotenv(env_file)
    print(f"Loaded environment from {env_file}", flush=True)

if os.environ.get("GOOGLE_CLOUD_PROJECT") and not os.environ.get("GOOGLE_API_KEY"):
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "1")

# ── Import agentsec inspectors (no monkey-patching needed for callback mode) ──
from aidefense.runtime.agentsec.inspectors import LLMInspector, MCPInspector
from aidefense.runtime.agentsec.decision import Decision

# ── Import ADK types ──
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.adk.tools.tool_context import ToolContext
from google.genai import types

logging.basicConfig(
    level=logging.DEBUG,
    format="[%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

APP_NAME = "adk_agentsec_callbacks_demo"

LLM_MODE = os.environ.get("AGENTSEC_API_MODE_LLM", "monitor")
MCP_MODE = os.environ.get("AGENTSEC_API_MODE_MCP", "monitor")

llm_inspector = LLMInspector()
mcp_inspector = MCPInspector()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_last_user_text(contents: list[types.Content]) -> Optional[str]:
    """Extract text from the most recent user message."""
    for content in reversed(contents):
        if content.role != "user" or not content.parts:
            continue
        text_parts = [
            part.text for part in content.parts
            if hasattr(part, "text") and part.text
        ]
        if text_parts:
            return "\n".join(text_parts)
    return None


def _extract_model_text(llm_response: LlmResponse) -> Optional[str]:
    """Extract the model's text from an LlmResponse."""
    if not llm_response.content or not llm_response.content.parts:
        return None
    text_parts = [
        part.text for part in llm_response.content.parts
        if hasattr(part, "text") and part.text
    ]
    return "\n".join(text_parts) if text_parts else None


def _blocked_llm_response(reason: str) -> LlmResponse:
    """Build a canned LlmResponse that ADK returns to the user on block."""
    return LlmResponse(
        content=types.Content(
            role="model",
            parts=[types.Part(text=reason)],
        ),
    )


def _log_decision(phase: str, decision: Decision) -> None:
    """Log a decision with key details."""
    logger.info(
        "AI Defense %s: action=%s severity=%s classifications=%s event_id=%s",
        phase,
        decision.action,
        decision.severity,
        decision.classifications,
        decision.event_id,
    )
    if decision.reasons:
        logger.debug("  reasons: %s", decision.reasons)


# ---------------------------------------------------------------------------
# LLM Callbacks (wired to LLMInspector)
# ---------------------------------------------------------------------------

async def before_model_callback(
    *,
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> Optional[LlmResponse]:
    """Inspect the user prompt before it reaches the LLM."""
    if LLM_MODE == "off":
        return None

    prompt_text = _extract_last_user_text(llm_request.contents)
    if not prompt_text:
        return None

    messages = [{"role": "user", "content": prompt_text}]
    metadata = {"src_app": APP_NAME}

    decision = await llm_inspector.ainspect_conversation(messages, metadata)
    _log_decision("before_model", decision)

    if not decision.allows():
        logger.warning("AI Defense blocked prompt: %s", decision.reasons)
        if LLM_MODE == "enforce":
            return _blocked_llm_response(
                "Request blocked by Cisco AI Defense policy."
            )
    return None


async def after_model_callback(
    *,
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> Optional[LlmResponse]:
    """Inspect the LLM response before it is returned to the user."""
    if LLM_MODE == "off":
        return None

    response_text = _extract_model_text(llm_response)
    if not response_text:
        return None

    messages = [
        {"role": "user", "content": "(prior turn)"},
        {"role": "assistant", "content": response_text},
    ]
    metadata = {"src_app": APP_NAME}

    decision = await llm_inspector.ainspect_conversation(messages, metadata)
    _log_decision("after_model", decision)

    if not decision.allows():
        logger.warning("AI Defense blocked response: %s", decision.reasons)
        if LLM_MODE == "enforce":
            return _blocked_llm_response(
                "Response blocked by Cisco AI Defense policy."
            )
    return None


# ---------------------------------------------------------------------------
# Tool Callbacks (wired to MCPInspector)
# ---------------------------------------------------------------------------

async def before_tool_callback(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
) -> Optional[dict]:
    """Inspect a tool call request before the tool executes."""
    if MCP_MODE == "off":
        return None

    metadata = {"src_app": APP_NAME}

    decision = await mcp_inspector.ainspect_request(
        tool_name=tool.name,
        arguments=args,
        metadata=metadata,
        method="tools/call",
    )
    _log_decision("before_tool", decision)

    if not decision.allows():
        logger.warning("AI Defense blocked tool request '%s': %s", tool.name, decision.reasons)
        if MCP_MODE == "enforce":
            return {"error": f"Tool call '{tool.name}' blocked by Cisco AI Defense policy."}
    return None


async def after_tool_callback(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
    tool_response: dict,
) -> Optional[dict]:
    """Inspect a tool call response after the tool executes."""
    if MCP_MODE == "off":
        return None

    metadata = {"src_app": APP_NAME}

    decision = await mcp_inspector.ainspect_response(
        tool_name=tool.name,
        arguments=args,
        result=tool_response,
        metadata=metadata,
        method="tools/call",
    )
    _log_decision("after_tool", decision)

    if not decision.allows():
        logger.warning("AI Defense blocked tool response '%s': %s", tool.name, decision.reasons)
        if MCP_MODE == "enforce":
            return {"error": f"Tool response from '{tool.name}' blocked by Cisco AI Defense policy."}
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _build_mcp_toolset() -> McpToolset | None:
    """Build an MCP toolset from MCP_SERVER_URL if configured."""
    mcp_url = os.environ.get("MCP_SERVER_URL")
    if not mcp_url:
        logger.debug("MCP_SERVER_URL not set — running without MCP tools")
        return None
    return McpToolset(
        connection_params=StreamableHTTPConnectionParams(url=mcp_url),
    )


async def main() -> None:
    """Run a single-turn ADK agent with callback-based AI Defense inspection."""
    print(f"Inspection mode — LLM: {LLM_MODE}, MCP: {MCP_MODE}", flush=True)

    if os.environ.get("GOOGLE_API_KEY"):
        print("Gemini backend: Developer API (GOOGLE_API_KEY)", flush=True)
    elif os.environ.get("GOOGLE_CLOUD_PROJECT"):
        print(
            f"Gemini backend: Vertex AI "
            f"(project={os.environ['GOOGLE_CLOUD_PROJECT']}, "
            f"location={os.environ.get('GOOGLE_CLOUD_LOCATION', 'us-central1')})",
            flush=True,
        )
    else:
        print(
            "WARNING: Neither GOOGLE_API_KEY nor GOOGLE_CLOUD_PROJECT is set.",
            flush=True,
        )

    tools: list = []
    mcp_toolset = _build_mcp_toolset()
    if mcp_toolset is not None:
        tools.append(mcp_toolset)

    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    logger.info("Using model: %s", model)

    agent = LlmAgent(
        model=model,
        name="secure_assistant",
        instruction=(
            "You are a helpful assistant protected by Cisco AI Defense. "
            "Answer questions concisely. If you have access to tools, use them "
            "when the user's request would benefit from external data."
        ),
        tools=tools,
        before_model_callback=before_model_callback,
        after_model_callback=after_model_callback,
        before_tool_callback=before_tool_callback,
        after_tool_callback=after_tool_callback,
    )

    session_service = InMemorySessionService()
    runner = Runner(
        app_name=APP_NAME,
        agent=agent,
        session_service=session_service,
    )

    session = await session_service.create_session(
        state={}, app_name=APP_NAME, user_id="demo_user"
    )

    query = "Summarize the benefits of zero-trust security in two sentences."
    print(f"\nUser: {query}", flush=True)

    content = types.Content(role="user", parts=[types.Part(text=query)])

    events = runner.run_async(
        session_id=session.id,
        user_id=session.user_id,
        new_message=content,
    )
    async for event in events:
        if event.content and event.content.parts:
            for part in event.content.parts:
                if hasattr(part, "text") and part.text:
                    print(f"Assistant: {part.text}", flush=True)

    if mcp_toolset is not None:
        await mcp_toolset.close()

    llm_inspector.close()
    mcp_inspector.close()

    print("\nDone — all calls were inspected via ADK callbacks.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
