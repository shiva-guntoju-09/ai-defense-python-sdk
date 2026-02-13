"""
LiteLLM autopatching.

This module provides automatic inspection for LiteLLM calls by patching
litellm.completion() and litellm.acompletion().

LiteLLM is an abstraction layer used by CrewAI (and others) that supports
multiple LLM providers. For some providers (notably Vertex AI), LiteLLM
makes direct HTTP calls bypassing the provider-specific SDK, so our
provider-specific patchers (vertexai, google_genai) cannot intercept them.

This patcher catches those calls at the LiteLLM level. It checks
whether a provider-specific patcher has already handled the call
(via the inspection context) and only inspects if needed.

Supports both API mode (inspection via AI Defense API) and Gateway mode
(routing through AI Defense Gateway).
"""

import logging
import threading
from typing import Any, Dict, List, Optional

import wrapt

from .. import _state
from .._context import get_inspection_context, set_inspection_context
from ..decision import Decision
from ..exceptions import SecurityPolicyError
from ..inspectors.api_llm import LLMInspector
from . import is_patched, mark_patched
from ._base import safe_import, resolve_gateway_settings

logger = logging.getLogger("aidefense.runtime.agentsec.patchers.litellm")

# Global inspector instance with thread-safe initialization
_inspector: Optional[LLMInspector] = None
_inspector_lock = threading.Lock()


def _get_inspector() -> LLMInspector:
    """Get or create the LLMInspector instance (thread-safe)."""
    global _inspector
    if _inspector is None:
        with _inspector_lock:
            if _inspector is None:
                if not _state.is_initialized():
                    logger.warning("agentsec.protect() not called, using default config")
                _inspector = LLMInspector(
                    fail_open=_state.get_api_llm_fail_open(),
                    default_rules=_state.get_llm_rules(),
                )
                from ..inspectors import register_inspector_for_cleanup
                register_inspector_for_cleanup(_inspector)
    return _inspector


def _should_inspect() -> bool:
    """Check if we should inspect (not already done, mode is not off, and not skipped)."""
    from .._context import is_llm_skip_active
    if is_llm_skip_active():
        return False
    mode = _state.get_llm_mode()
    if mode == "off":
        return False
    ctx = get_inspection_context()
    return not ctx.done


def _enforce_decision(decision: Decision) -> None:
    """Enforce a decision if in enforce mode."""
    mode = _state.get_llm_mode()
    if mode == "enforce" and decision.action == "block":
        raise SecurityPolicyError(decision)


def _detect_provider(model: str) -> str:
    """Detect the LLM provider from the LiteLLM model string.
    
    LiteLLM uses prefixed model names like:
    - vertex_ai/gemini-2.5-flash-lite
    - azure/gpt-4
    - bedrock/anthropic.claude-3-haiku
    - gpt-4 (OpenAI, no prefix)
    """
    if not model:
        return "unknown"
    model_lower = model.lower()
    if model_lower.startswith("vertex_ai/") or model_lower.startswith("vertex_ai_beta/"):
        return "vertexai"
    if model_lower.startswith("azure/"):
        return "azure_openai"
    if model_lower.startswith("bedrock/") or model_lower.startswith("anthropic."):
        return "bedrock"
    if model_lower.startswith("gemini/") or model_lower.startswith("google/"):
        return "google_genai"
    # Default: OpenAI (no prefix)
    return "openai"


def _extract_response_text(response: Any) -> str:
    """Extract text content from a LiteLLM ModelResponse.
    
    LiteLLM returns a ModelResponse object with OpenAI-compatible structure:
        response.choices[0].message.content
    """
    try:
        if hasattr(response, 'choices') and response.choices:
            choice = response.choices[0]
            if hasattr(choice, 'message') and hasattr(choice.message, 'content'):
                return choice.message.content or ""
        # Try dict access
        if isinstance(response, dict):
            choices = response.get('choices', [])
            if choices:
                return choices[0].get('message', {}).get('content', '')
    except (IndexError, AttributeError, TypeError) as e:
        logger.debug(f"Error extracting response text: {e}")
    return ""


def _wrap_completion(wrapped, instance, args, kwargs):
    """Wrapper for litellm.completion().
    
    Intercepts LiteLLM completion calls for AI Defense inspection.
    Checks if a provider-specific patcher already handled the call.
    """
    model = kwargs.get("model") or (args[0] if args else "unknown")
    messages = kwargs.get("messages") or (args[1] if len(args) > 1 else [])
    
    if not _should_inspect():
        logger.debug(f"[PATCHED CALL] litellm.completion - inspection skipped (mode=off or already done)")
        return wrapped(*args, **kwargs)
    
    provider = _detect_provider(model)
    
    # Normalize messages (LiteLLM uses OpenAI format already)
    normalized = []
    if isinstance(messages, list):
        for msg in messages:
            if isinstance(msg, dict):
                normalized.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", ""),
                })
    
    metadata = get_inspection_context().metadata
    metadata["provider"] = provider
    metadata["model"] = model
    metadata["source"] = "litellm"
    
    mode = _state.get_llm_mode()
    integration_mode = _state.get_llm_integration_mode()
    logger.debug(f"")
    logger.debug(f"╔══════════════════════════════════════════════════════════════")
    logger.debug(f"║ [PATCHED] LLM CALL: {model}")
    logger.debug(f"║ Operation: litellm.completion | Provider: {provider} | LLM Mode: {mode} | Integration: {integration_mode}")
    logger.debug(f"╚══════════════════════════════════════════════════════════════")
    
    # Gateway mode: attempt to redirect via api_base
    gw_settings = resolve_gateway_settings(provider)
    if gw_settings:
        logger.debug(f"[PATCHED CALL] litellm.completion - Gateway mode for {provider}")
        # Set LiteLLM's api_base to the gateway URL
        # LiteLLM respects api_base for custom endpoints
        kwargs["api_base"] = gw_settings.url
        kwargs["api_key"] = gw_settings.api_key
        logger.debug(f"[PATCHED CALL] litellm.completion - Redirecting to gateway: {gw_settings.url}")
        
        # For vertex_ai, we also need to override auth since the gateway handles it
        if provider == "vertexai":
            # LiteLLM vertex_ai uses Google ADC; switch to custom api_key auth
            # Remove vertex-specific params that would trigger ADC auth
            kwargs.pop("vertex_project", None)
            kwargs.pop("vertex_location", None)
            kwargs.pop("vertex_credentials", None)
            # LiteLLM needs the model without the prefix for custom endpoints
            # Keep as-is since gateway should handle the model routing
        
        try:
            response = wrapped(*args, **kwargs)
            set_inspection_context(
                decision=Decision.allow(reasons=["Gateway handled inspection"]),
                done=True,
            )
            return response
        except Exception as e:
            logger.error(f"[GATEWAY] litellm.completion error: {e}")
            if gw_settings.fail_open:
                logger.warning(f"[GATEWAY] fail_open=True, re-raising for caller to handle")
                set_inspection_context(
                    decision=Decision.allow(reasons=["Gateway error, fail_open=True"]),
                    done=True,
                )
                raise
            raise SecurityPolicyError(
                Decision.block(reasons=["Gateway error"]),
                f"LiteLLM gateway error: {e}",
            )
    
    # API mode: use LLMInspector for inspection
    # Pre-call inspection
    if normalized:
        logger.debug(f"[PATCHED CALL] litellm.completion - Request inspection ({len(normalized)} messages)")
        inspector = _get_inspector()
        decision = inspector.inspect_conversation(normalized, metadata)
        logger.debug(f"[PATCHED CALL] litellm.completion - Request decision: {decision.action}")
        set_inspection_context(decision=decision)
        _enforce_decision(decision)
    
    # Call the original
    logger.debug(f"[PATCHED CALL] litellm.completion - calling original method")
    response = wrapped(*args, **kwargs)
    
    # Post-call inspection
    assistant_content = _extract_response_text(response)
    if assistant_content and normalized:
        logger.debug(f"[PATCHED CALL] litellm.completion - Response inspection (response: {len(assistant_content)} chars)")
        messages_with_response = normalized + [
            {"role": "assistant", "content": assistant_content}
        ]
        inspector = _get_inspector()
        decision = inspector.inspect_conversation(messages_with_response, metadata)
        logger.debug(f"[PATCHED CALL] litellm.completion - Response decision: {decision.action}")
        set_inspection_context(decision=decision, done=True)
        _enforce_decision(decision)
    
    logger.debug(f"[PATCHED CALL] litellm.completion - complete")
    return response


async def _wrap_acompletion(wrapped, instance, args, kwargs):
    """Async wrapper for litellm.acompletion()."""
    model = kwargs.get("model") or (args[0] if args else "unknown")
    messages = kwargs.get("messages") or (args[1] if len(args) > 1 else [])
    
    if not _should_inspect():
        logger.debug(f"[PATCHED CALL] litellm.acompletion - inspection skipped")
        return await wrapped(*args, **kwargs)
    
    provider = _detect_provider(model)
    
    # Normalize messages
    normalized = []
    if isinstance(messages, list):
        for msg in messages:
            if isinstance(msg, dict):
                normalized.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", ""),
                })
    
    metadata = get_inspection_context().metadata
    metadata["provider"] = provider
    metadata["model"] = model
    metadata["source"] = "litellm"
    
    mode = _state.get_llm_mode()
    integration_mode = _state.get_llm_integration_mode()
    logger.debug(f"")
    logger.debug(f"╔══════════════════════════════════════════════════════════════")
    logger.debug(f"║ [PATCHED] LLM CALL (async): {model}")
    logger.debug(f"║ Operation: litellm.acompletion | Provider: {provider} | LLM Mode: {mode} | Integration: {integration_mode}")
    logger.debug(f"╚══════════════════════════════════════════════════════════════")
    
    # Gateway mode: attempt to redirect via api_base
    gw_settings = resolve_gateway_settings(provider)
    if gw_settings:
        logger.debug(f"[PATCHED CALL] litellm.acompletion - Gateway mode for {provider}")
        kwargs["api_base"] = gw_settings.url
        kwargs["api_key"] = gw_settings.api_key
        logger.debug(f"[PATCHED CALL] litellm.acompletion - Redirecting to gateway: {gw_settings.url}")
        
        if provider == "vertexai":
            kwargs.pop("vertex_project", None)
            kwargs.pop("vertex_location", None)
            kwargs.pop("vertex_credentials", None)
        
        try:
            response = await wrapped(*args, **kwargs)
            set_inspection_context(
                decision=Decision.allow(reasons=["Gateway handled inspection"]),
                done=True,
            )
            return response
        except Exception as e:
            logger.error(f"[GATEWAY] litellm.acompletion error: {e}")
            if gw_settings.fail_open:
                logger.warning(f"[GATEWAY] fail_open=True, re-raising for caller to handle")
                set_inspection_context(
                    decision=Decision.allow(reasons=["Gateway error, fail_open=True"]),
                    done=True,
                )
                raise
            raise SecurityPolicyError(
                Decision.block(reasons=["Gateway error"]),
                f"LiteLLM gateway error: {e}",
            )
    
    # API mode: Pre-call inspection
    if normalized:
        logger.debug(f"[PATCHED CALL] litellm.acompletion - Request inspection ({len(normalized)} messages)")
        inspector = _get_inspector()
        decision = await inspector.ainspect_conversation(normalized, metadata)
        logger.debug(f"[PATCHED CALL] litellm.acompletion - Request decision: {decision.action}")
        set_inspection_context(decision=decision)
        _enforce_decision(decision)
    
    # Call the original
    logger.debug(f"[PATCHED CALL] litellm.acompletion - calling original method")
    response = await wrapped(*args, **kwargs)
    
    # Post-call inspection
    assistant_content = _extract_response_text(response)
    if assistant_content and normalized:
        logger.debug(f"[PATCHED CALL] litellm.acompletion - Response inspection")
        messages_with_response = normalized + [
            {"role": "assistant", "content": assistant_content}
        ]
        inspector = _get_inspector()
        decision = await inspector.ainspect_conversation(messages_with_response, metadata)
        logger.debug(f"[PATCHED CALL] litellm.acompletion - Response decision: {decision.action}")
        set_inspection_context(decision=decision, done=True)
        _enforce_decision(decision)
    
    logger.debug(f"[PATCHED CALL] litellm.acompletion - complete")
    return response


def patch_litellm() -> bool:
    """
    Patch LiteLLM for automatic inspection.
    
    Patches litellm.completion() and litellm.acompletion() to intercept
    all LLM calls made through LiteLLM (used by CrewAI and others).
    
    Returns:
        True if patching was successful, False otherwise
    """
    if is_patched("litellm"):
        logger.debug("LiteLLM already patched, skipping")
        return True
    
    litellm = safe_import("litellm")
    if litellm is None:
        return False
    
    try:
        # Patch litellm.completion
        wrapt.wrap_function_wrapper(
            "litellm",
            "completion",
            _wrap_completion,
        )
        logger.debug("Patched litellm.completion")
        
        # Patch litellm.acompletion
        try:
            wrapt.wrap_function_wrapper(
                "litellm",
                "acompletion",
                _wrap_acompletion,
            )
            logger.debug("Patched litellm.acompletion")
        except Exception as e:
            logger.debug(f"Could not patch litellm.acompletion: {e}")
        
        mark_patched("litellm")
        logger.info("LiteLLM patched successfully (completion, acompletion)")
        return True
    except Exception as e:
        logger.warning(f"Failed to patch LiteLLM: {e}")
        return False
