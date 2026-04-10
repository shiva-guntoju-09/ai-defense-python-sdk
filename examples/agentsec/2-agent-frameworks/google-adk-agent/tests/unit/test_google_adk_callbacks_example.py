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
Tests for the Google ADK Callback-based Agent Example (agent_callbacks.py).

This module validates:
- File structure and syntax
- LLMInspector / MCPInspector usage (not monkey-patching)
- ADK callback wiring (before_model, after_model, before_tool, after_tool)
- Decision handling and enforce/monitor mode logic
- Inspector cleanup
"""

import ast
import os

import pytest


EXAMPLE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Path to the google-adk-agent example directory."""


@pytest.fixture(scope="module")
def cb_example_file():
    """Path to the callback example agent_callbacks.py file."""
    return os.path.join(EXAMPLE_DIR, "agent_callbacks.py")


@pytest.fixture(scope="module")
def cb_example_code(cb_example_file):
    """Read the callback example file source code."""
    with open(cb_example_file) as f:
        return f.read()


@pytest.fixture(scope="module")
def cb_example_ast(cb_example_code):
    """Parse the callback example file into an AST."""
    return ast.parse(cb_example_code)


# ---------------------------------------------------------------------------
# File structure
# ---------------------------------------------------------------------------

class TestCallbackFileStructure:
    """Verify agent_callbacks.py exists and is well-formed."""

    def test_file_exists(self):
        assert os.path.exists(os.path.join(EXAMPLE_DIR, "agent_callbacks.py")), \
            "agent_callbacks.py should exist"

    def test_syntax_valid(self, cb_example_code):
        try:
            ast.parse(cb_example_code)
        except SyntaxError as e:
            pytest.fail(f"Syntax error in agent_callbacks.py: {e}")

    def test_has_docstring(self, cb_example_ast):
        docstring = ast.get_docstring(cb_example_ast)
        assert docstring, "Module should have a docstring"

    def test_main_guard(self, cb_example_code):
        assert '__name__ == "__main__"' in cb_example_code or \
               "__name__ == '__main__'" in cb_example_code, \
            "Should have main guard"


# ---------------------------------------------------------------------------
# Inspector usage (not monkey-patching)
# ---------------------------------------------------------------------------

class TestInspectorUsage:
    """Verify that LLMInspector and MCPInspector are used instead of agentsec.protect()."""

    def test_imports_llm_inspector(self, cb_example_code):
        assert "LLMInspector" in cb_example_code, \
            "Should import LLMInspector"

    def test_imports_mcp_inspector(self, cb_example_code):
        assert "MCPInspector" in cb_example_code, \
            "Should import MCPInspector"

    def test_imports_decision(self, cb_example_code):
        assert "Decision" in cb_example_code, \
            "Should import Decision"

    def test_creates_llm_inspector(self, cb_example_code):
        assert "LLMInspector()" in cb_example_code, \
            "Should instantiate LLMInspector"

    def test_creates_mcp_inspector(self, cb_example_code):
        assert "MCPInspector()" in cb_example_code, \
            "Should instantiate MCPInspector"

    def test_no_agentsec_protect(self, cb_example_code):
        assert "agentsec.protect(" not in cb_example_code, \
            "Callback example should NOT use agentsec.protect() (that's the monkey-patching approach)"

    def test_uses_ainspect_conversation(self, cb_example_code):
        assert "ainspect_conversation" in cb_example_code, \
            "Should use LLMInspector.ainspect_conversation() for async inspection"

    def test_uses_ainspect_request(self, cb_example_code):
        assert "ainspect_request" in cb_example_code, \
            "Should use MCPInspector.ainspect_request()"

    def test_uses_ainspect_response(self, cb_example_code):
        assert "ainspect_response" in cb_example_code, \
            "Should use MCPInspector.ainspect_response()"


# ---------------------------------------------------------------------------
# ADK callback wiring
# ---------------------------------------------------------------------------

class TestADKCallbackWiring:
    """Verify that ADK callbacks are defined and wired to LlmAgent."""

    def test_before_model_callback_defined(self, cb_example_code):
        assert "async def before_model_callback(" in cb_example_code, \
            "Should define before_model_callback"

    def test_after_model_callback_defined(self, cb_example_code):
        assert "async def after_model_callback(" in cb_example_code, \
            "Should define after_model_callback"

    def test_before_tool_callback_defined(self, cb_example_code):
        assert "async def before_tool_callback(" in cb_example_code, \
            "Should define before_tool_callback"

    def test_after_tool_callback_defined(self, cb_example_code):
        assert "async def after_tool_callback(" in cb_example_code, \
            "Should define after_tool_callback"

    def test_callbacks_wired_to_agent(self, cb_example_code):
        assert "before_model_callback=before_model_callback" in cb_example_code, \
            "before_model_callback should be passed to LlmAgent"
        assert "after_model_callback=after_model_callback" in cb_example_code, \
            "after_model_callback should be passed to LlmAgent"
        assert "before_tool_callback=before_tool_callback" in cb_example_code, \
            "before_tool_callback should be passed to LlmAgent"
        assert "after_tool_callback=after_tool_callback" in cb_example_code, \
            "after_tool_callback should be passed to LlmAgent"

    def test_callback_context_import(self, cb_example_code):
        assert "CallbackContext" in cb_example_code, \
            "Should import CallbackContext for callback signatures"

    def test_llm_request_import(self, cb_example_code):
        assert "LlmRequest" in cb_example_code, \
            "Should import LlmRequest for before_model_callback"

    def test_llm_response_import(self, cb_example_code):
        assert "LlmResponse" in cb_example_code, \
            "Should import LlmResponse for after_model_callback"

    def test_tool_context_import(self, cb_example_code):
        assert "ToolContext" in cb_example_code, \
            "Should import ToolContext for tool callbacks"

    def test_base_tool_import(self, cb_example_code):
        assert "BaseTool" in cb_example_code, \
            "Should import BaseTool for tool callback signatures"


# ---------------------------------------------------------------------------
# Decision handling
# ---------------------------------------------------------------------------

class TestDecisionHandling:
    """Verify correct usage of Decision objects."""

    def test_checks_allows(self, cb_example_code):
        assert "decision.allows()" in cb_example_code, \
            "Should check decision.allows() for allow/block"

    def test_enforce_mode_check_llm(self, cb_example_code):
        assert 'LLM_MODE == "enforce"' in cb_example_code, \
            "Should check LLM_MODE for enforce behavior"

    def test_enforce_mode_check_mcp(self, cb_example_code):
        assert 'MCP_MODE == "enforce"' in cb_example_code, \
            "Should check MCP_MODE for enforce behavior"

    def test_blocked_response_on_enforce(self, cb_example_code):
        assert "blocked by Cisco AI Defense policy" in cb_example_code, \
            "Should return a blocked message on enforce"

    def test_mode_env_vars_read(self, cb_example_code):
        assert "AGENTSEC_API_MODE_LLM" in cb_example_code
        assert "AGENTSEC_API_MODE_MCP" in cb_example_code


# ---------------------------------------------------------------------------
# Inspector cleanup
# ---------------------------------------------------------------------------

class TestInspectorCleanup:
    """Verify inspectors are properly closed."""

    def test_llm_inspector_closed(self, cb_example_code):
        assert "llm_inspector.close()" in cb_example_code, \
            "Should close LLMInspector on exit"

    def test_mcp_inspector_closed(self, cb_example_code):
        assert "mcp_inspector.close()" in cb_example_code, \
            "Should close MCPInspector on exit"


# ---------------------------------------------------------------------------
# ADK agent setup
# ---------------------------------------------------------------------------

class TestADKAgentSetup:
    """Verify ADK agent is properly configured."""

    def test_llm_agent_used(self, cb_example_code):
        assert "LlmAgent(" in cb_example_code, "Should instantiate LlmAgent"

    def test_runner_used(self, cb_example_code):
        assert "Runner(" in cb_example_code, "Should instantiate Runner"

    def test_session_service_used(self, cb_example_code):
        assert "InMemorySessionService" in cb_example_code

    def test_run_async_used(self, cb_example_code):
        assert "run_async" in cb_example_code

    def test_gemini_model_configured(self, cb_example_code):
        assert "gemini" in cb_example_code.lower()


# ---------------------------------------------------------------------------
# MCP integration
# ---------------------------------------------------------------------------

class TestCallbackMCPIntegration:
    """Verify MCP tool integration."""

    def test_mcp_toolset_imported(self, cb_example_code):
        assert "McpToolset" in cb_example_code

    def test_mcp_url_from_env(self, cb_example_code):
        assert "MCP_SERVER_URL" in cb_example_code

    def test_mcp_toolset_cleanup(self, cb_example_code):
        assert "mcp_toolset.close()" in cb_example_code
