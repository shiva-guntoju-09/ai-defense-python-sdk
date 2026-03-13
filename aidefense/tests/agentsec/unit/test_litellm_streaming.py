"""Tests for LiteLLM streaming inspection wrappers.

Covers _LiteLLMStreamingInspectionWrapper, _AsyncLiteLLMStreamingInspectionWrapper,
and the stream=True detection in _wrap_completion / _wrap_acompletion.
"""

import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, AsyncMock

from aidefense.runtime.agentsec.decision import Decision
from aidefense.runtime.agentsec.exceptions import SecurityPolicyError
from aidefense.runtime.agentsec import _state
from aidefense.runtime.agentsec._context import clear_inspection_context
from aidefense.runtime.agentsec.patchers import reset_registry


@pytest.fixture(autouse=True)
def reset_env():
    """Reset agentsec state and patch registry before each test."""
    _state.reset()
    reset_registry()
    clear_inspection_context()
    import aidefense.runtime.agentsec.patchers.litellm as litellm_module
    litellm_module._inspector = None
    yield
    _state.reset()
    reset_registry()
    clear_inspection_context()
    litellm_module._inspector = None


def _make_litellm_stream_chunks(text_chunks):
    """Build a list of OpenAI-compatible streaming chunks."""
    chunks = []
    for text in text_chunks:
        chunk = SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content=text))]
        )
        chunks.append(chunk)
    return chunks


async def _async_iter(items):
    """Helper to create an async iterator from a list."""
    for item in items:
        yield item


# ===========================================================================
# _LiteLLMStreamingInspectionWrapper (sync)
# ===========================================================================


class TestLiteLLMStreamingInspectionWrapper:
    """Tests for the sync LiteLLM streaming wrapper."""

    @patch("aidefense.runtime.agentsec.patchers.litellm._should_inspect", return_value=True)
    @patch("aidefense.runtime.agentsec.patchers.litellm._get_inspector")
    def test_yields_all_chunks_and_accumulates(self, mock_get_inspector, mock_should):
        from aidefense.runtime.agentsec.patchers.litellm import _LiteLLMStreamingInspectionWrapper

        mock_inspector = MagicMock()
        mock_inspector.inspect_conversation.return_value = Decision.allow()
        mock_get_inspector.return_value = mock_inspector

        chunks = _make_litellm_stream_chunks(["Hello", " ", "world"])
        wrapper = _LiteLLMStreamingInspectionWrapper(
            iter(chunks), [{"role": "user", "content": "hi"}], {}
        )

        collected = list(wrapper)
        assert len(collected) == 3
        assert wrapper._buffer == "Hello world"

    @patch("aidefense.runtime.agentsec.patchers.litellm._should_inspect", return_value=True)
    @patch("aidefense.runtime.agentsec.patchers.litellm._get_inspector")
    def test_final_inspection_called(self, mock_get_inspector, mock_should):
        from aidefense.runtime.agentsec.patchers.litellm import _LiteLLMStreamingInspectionWrapper

        mock_inspector = MagicMock()
        mock_inspector.inspect_conversation.return_value = Decision.allow()
        mock_get_inspector.return_value = mock_inspector

        chunks = _make_litellm_stream_chunks(["text"])
        wrapper = _LiteLLMStreamingInspectionWrapper(
            iter(chunks), [{"role": "user", "content": "hi"}], {}
        )
        list(wrapper)

        assert mock_inspector.inspect_conversation.called
        assert wrapper._final_inspection_done

    @patch("aidefense.runtime.agentsec.patchers.litellm._should_inspect", return_value=True)
    @patch("aidefense.runtime.agentsec.patchers.litellm._get_inspector")
    def test_incremental_inspection(self, mock_get_inspector, mock_should):
        from aidefense.runtime.agentsec.patchers.litellm import _LiteLLMStreamingInspectionWrapper

        mock_inspector = MagicMock()
        mock_inspector.inspect_conversation.return_value = Decision.allow()
        mock_get_inspector.return_value = mock_inspector

        chunks = _make_litellm_stream_chunks([f"w{i}" for i in range(25)])
        wrapper = _LiteLLMStreamingInspectionWrapper(
            iter(chunks), [{"role": "user", "content": "hi"}], {}
        )
        wrapper._inspect_interval = 10
        list(wrapper)

        # 2 incremental + 1 final
        assert mock_inspector.inspect_conversation.call_count == 3

    @patch("aidefense.runtime.agentsec.patchers.litellm._should_inspect", return_value=True)
    @patch("aidefense.runtime.agentsec.patchers.litellm._get_inspector")
    def test_block_raises_in_enforce_mode(self, mock_get_inspector, mock_should):
        from aidefense.runtime.agentsec.patchers.litellm import _LiteLLMStreamingInspectionWrapper

        mock_inspector = MagicMock()
        mock_inspector.inspect_conversation.return_value = Decision.block(reasons=["unsafe"])
        mock_get_inspector.return_value = mock_inspector

        _state._state = {"initialized": True, "llm_mode": "enforce"}

        chunks = _make_litellm_stream_chunks(["bad content"])
        wrapper = _LiteLLMStreamingInspectionWrapper(
            iter(chunks), [{"role": "user", "content": "hi"}], {}
        )

        with pytest.raises(SecurityPolicyError):
            list(wrapper)

    @patch("aidefense.runtime.agentsec.patchers.litellm._should_inspect", return_value=True)
    @patch("aidefense.runtime.agentsec.patchers.litellm._get_inspector")
    def test_buffer_capped(self, mock_get_inspector, mock_should):
        from aidefense.runtime.agentsec.patchers.litellm import (
            _LiteLLMStreamingInspectionWrapper,
            MAX_STREAMING_BUFFER_SIZE,
        )

        mock_inspector = MagicMock()
        mock_inspector.inspect_conversation.return_value = Decision.allow()
        mock_get_inspector.return_value = mock_inspector

        huge_text = "x" * (MAX_STREAMING_BUFFER_SIZE + 500)
        chunks = _make_litellm_stream_chunks([huge_text])
        wrapper = _LiteLLMStreamingInspectionWrapper(
            iter(chunks), [{"role": "user", "content": "hi"}], {}
        )
        list(wrapper)

        assert len(wrapper._buffer) <= MAX_STREAMING_BUFFER_SIZE


# ===========================================================================
# _AsyncLiteLLMStreamingInspectionWrapper
# ===========================================================================


class TestAsyncLiteLLMStreamingInspectionWrapper:
    """Tests for the async LiteLLM streaming wrapper."""

    @pytest.mark.asyncio
    @patch("aidefense.runtime.agentsec.patchers.litellm._should_inspect", return_value=True)
    @patch("aidefense.runtime.agentsec.patchers.litellm._get_inspector")
    async def test_yields_all_chunks(self, mock_get_inspector, mock_should):
        from aidefense.runtime.agentsec.patchers.litellm import _AsyncLiteLLMStreamingInspectionWrapper

        mock_inspector = MagicMock()
        mock_inspector.ainspect_conversation = AsyncMock(return_value=Decision.allow())
        mock_get_inspector.return_value = mock_inspector

        raw_chunks = _make_litellm_stream_chunks(["Hello", " world"])
        wrapper = _AsyncLiteLLMStreamingInspectionWrapper(
            _async_iter(raw_chunks),
            [{"role": "user", "content": "hi"}],
            {},
        )

        collected = []
        async for chunk in wrapper:
            collected.append(chunk)

        assert len(collected) == 2
        assert wrapper._buffer == "Hello world"


# ===========================================================================
# _wrap_completion detects stream=True
# ===========================================================================


class TestWrapCompletionStreaming:
    """Verify _wrap_completion returns a streaming wrapper when stream=True."""

    @patch("aidefense.runtime.agentsec.patchers.litellm._should_inspect", return_value=True)
    @patch("aidefense.runtime.agentsec.patchers.litellm._get_inspector")
    @patch("aidefense.runtime.agentsec.patchers.litellm.resolve_gateway_settings", return_value=None)
    def test_stream_true_returns_wrapper(self, mock_gw, mock_get_inspector, mock_should):
        from aidefense.runtime.agentsec.patchers.litellm import (
            _wrap_completion,
            _LiteLLMStreamingInspectionWrapper,
        )

        mock_inspector = MagicMock()
        mock_inspector.inspect_conversation.return_value = Decision.allow()
        mock_get_inspector.return_value = mock_inspector

        raw_chunks = _make_litellm_stream_chunks(["token1", "token2"])
        wrapped_fn = MagicMock(return_value=iter(raw_chunks))

        result = _wrap_completion(
            wrapped_fn,
            None,
            (),
            {
                "model": "gpt-4",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
        )

        assert isinstance(result, _LiteLLMStreamingInspectionWrapper)

    @patch("aidefense.runtime.agentsec.patchers.litellm._should_inspect", return_value=True)
    @patch("aidefense.runtime.agentsec.patchers.litellm._get_inspector")
    @patch("aidefense.runtime.agentsec.patchers.litellm.resolve_gateway_settings", return_value=None)
    def test_stream_false_returns_response_directly(self, mock_gw, mock_get_inspector, mock_should):
        from aidefense.runtime.agentsec.patchers.litellm import _wrap_completion

        mock_inspector = MagicMock()
        mock_inspector.inspect_conversation.return_value = Decision.allow()
        mock_get_inspector.return_value = mock_inspector

        mock_response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Hello!"))]
        )
        wrapped_fn = MagicMock(return_value=mock_response)

        result = _wrap_completion(
            wrapped_fn,
            None,
            (),
            {
                "model": "gpt-4",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": False,
            },
        )

        assert result is mock_response
