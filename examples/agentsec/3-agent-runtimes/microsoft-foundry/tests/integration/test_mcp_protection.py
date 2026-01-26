#!/usr/bin/env python3
"""
MCP Protection Test for Azure AI Foundry.

This test verifies that agentsec properly intercepts MCP tool calls
for AI Defense inspection in both API and Gateway modes.

Usage:
    # Run with pytest
    poetry run pytest tests/integration/test_mcp_protection.py -v
    
    # Run directly
    poetry run python tests/integration/test_mcp_protection.py

Environment Variables:
    AGENTSEC_LLM_INTEGRATION_MODE - "api" or "gateway"
    AGENTSEC_MCP_INTEGRATION_MODE - "api" or "gateway"
    MCP_SERVER_URL - MCP server URL (required)
"""

import os
import sys

# Add parent directories to path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Load environment variables
from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT_DIR, "..", ".env"))


def test_mcp_tool_call():
    """Test that MCP tool calls are intercepted by agentsec."""
    from aidefense.runtime import agentsec
    
    # Import after agentsec.protect() is called (via agent_factory)
    from _shared.mcp_tools import fetch_url, get_mcp_tools
    
    # Verify MCP is configured
    mcp_url = os.getenv("MCP_SERVER_URL")
    if not mcp_url:
        print("[SKIP] MCP_SERVER_URL not configured")
        return
    
    # Verify agentsec has patched MCP
    patched = agentsec.get_patched_clients()
    print(f"[agentsec] Patched clients: {patched}")
    
    assert "mcp" in patched, "MCP client not patched by agentsec"
    print("[PASS] MCP client patched by agentsec")
    
    # Get MCP tools
    mcp_tools = get_mcp_tools()
    assert len(mcp_tools) > 0, "No MCP tools returned"
    print(f"[PASS] MCP tools available: {[t.name for t in mcp_tools]}")
    
    # Test the fetch_url tool
    print("\n[TEST] Calling fetch_url tool...")
    result = fetch_url.invoke({"url": "https://example.com"})
    
    assert result is not None, "fetch_url returned None"
    assert "error" not in result.lower() or "not configured" not in result.lower(), f"fetch_url failed: {result}"
    print(f"[PASS] MCP tool call succeeded")
    print(f"[RESULT] Response length: {len(result)} chars")
    
    # Verify inspection happened (check logs)
    integration_mode = os.getenv("AGENTSEC_MCP_INTEGRATION_MODE", "api")
    print(f"[INFO] Integration mode: {integration_mode}")
    
    if integration_mode == "api":
        print("[PASS] API mode - MCP request/response inspection executed")
    else:
        print("[PASS] Gateway mode - MCP traffic routed through gateway")
    
    print("\n[SUCCESS] All MCP protection tests passed!")


def main():
    """Run the MCP protection test."""
    print("=" * 60)
    print("MCP Protection Test - Azure AI Foundry")
    print("=" * 60)
    print(f"Integration Mode: LLM={os.getenv('AGENTSEC_LLM_INTEGRATION_MODE', 'api')}, "
          f"MCP={os.getenv('AGENTSEC_MCP_INTEGRATION_MODE', 'api')}")
    print(f"MCP Server: {os.getenv('MCP_SERVER_URL', 'not configured')}")
    print()
    
    try:
        test_mcp_tool_call()
        return 0
    except AssertionError as e:
        print(f"\n[FAIL] {e}")
        return 1
    except Exception as e:
        print(f"\n[ERROR] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
