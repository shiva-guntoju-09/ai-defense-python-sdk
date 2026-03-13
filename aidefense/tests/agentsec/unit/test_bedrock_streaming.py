"""Tests for Bedrock streaming inspection wrappers.

Covers _ConverseStreamInspectionWrapper and _InvokeModelStreamInspectionWrapper
added to support response-side streaming inspection in API mode.
"""

import json
import pytest
from unittest.mock import MagicMock, patch

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
    import aidefense.runtime.agentsec.patchers.bedrock as bedrock_module
    bedrock_module._inspector = None
    yield
    _state.reset()
    reset_registry()
    clear_inspection_context()
    bedrock_module._inspector = None


def _make_converse_stream_events(text_chunks):
    """Build a list of ConverseStream-format events from text chunks."""
    events = [{"messageStart": {"role": "assistant"}}]
    events.append({"contentBlockStart": {"contentBlockIndex": 0, "start": {"text": ""}}})
    for chunk in text_chunks:
        events.append({
            "contentBlockDelta": {
                "contentBlockIndex": 0,
                "delta": {"text": chunk},
            }
        })
    events.append({"contentBlockStop": {"contentBlockIndex": 0}})
    events.append({"messageStop": {"stopReason": "end_turn"}})
    events.append({"metadata": {"usage": {"inputTokens": 10, "outputTokens": 5}}})
    return events


def _make_invoke_model_stream_events(text_chunks):
    """Build InvokeModelWithResponseStream-format events from text chunks."""
    events = []
    for chunk in text_chunks:
        data = {"type": "content_block_delta", "delta": {"type": "text_delta", "text": chunk}}
        events.append({"chunk": {"bytes": json.dumps(data).encode()}})
    return events


# ===========================================================================
# _ConverseStreamInspectionWrapper
# ===========================================================================


class TestConverseStreamInspectionWrapper:
    """Tests for the ConverseStream inspection wrapper."""

    @patch("aidefense.runtime.agentsec.patchers.bedrock._should_inspect", return_value=True)
    @patch("aidefense.runtime.agentsec.patchers.bedrock._get_inspector")
    def test_yields_all_events_and_accumulates_text(self, mock_get_inspector, mock_should):
        from aidefense.runtime.agentsec.patchers.bedrock import _ConverseStreamInspectionWrapper

        mock_inspector = MagicMock()
        mock_inspector.inspect_conversation.return_value = Decision.allow()
        mock_get_inspector.return_value = mock_inspector

        chunks = ["Hello", " world", "!"]
        events = _make_converse_stream_events(chunks)
        wrapper = _ConverseStreamInspectionWrapper(iter(events), [{"role": "user", "content": "hi"}], {})

        collected = list(wrapper)
        assert len(collected) == len(events)
        assert wrapper._buffer == "Hello world!"

    @patch("aidefense.runtime.agentsec.patchers.bedrock._should_inspect", return_value=True)
    @patch("aidefense.runtime.agentsec.patchers.bedrock._get_inspector")
    def test_final_inspection_called_on_stream_end(self, mock_get_inspector, mock_should):
        from aidefense.runtime.agentsec.patchers.bedrock import _ConverseStreamInspectionWrapper

        mock_inspector = MagicMock()
        mock_inspector.inspect_conversation.return_value = Decision.allow()
        mock_get_inspector.return_value = mock_inspector

        events = _make_converse_stream_events(["text"])
        wrapper = _ConverseStreamInspectionWrapper(iter(events), [{"role": "user", "content": "hi"}], {})
        list(wrapper)

        assert mock_inspector.inspect_conversation.called
        assert wrapper._final_inspection_done

    @patch("aidefense.runtime.agentsec.patchers.bedrock._should_inspect", return_value=True)
    @patch("aidefense.runtime.agentsec.patchers.bedrock._get_inspector")
    def test_incremental_inspection_every_n_chunks(self, mock_get_inspector, mock_should):
        from aidefense.runtime.agentsec.patchers.bedrock import _ConverseStreamInspectionWrapper

        mock_inspector = MagicMock()
        mock_inspector.inspect_conversation.return_value = Decision.allow()
        mock_get_inspector.return_value = mock_inspector

        chunks = [f"word{i}" for i in range(25)]
        events = _make_converse_stream_events(chunks)
        wrapper = _ConverseStreamInspectionWrapper(iter(events), [{"role": "user", "content": "hi"}], {})
        wrapper._inspect_interval = 10
        list(wrapper)

        # 2 incremental (at 10, 20) + 1 final
        assert mock_inspector.inspect_conversation.call_count == 3

    @patch("aidefense.runtime.agentsec.patchers.bedrock._should_inspect", return_value=True)
    @patch("aidefense.runtime.agentsec.patchers.bedrock._get_inspector")
    def test_block_decision_raises_security_error_in_enforce_mode(self, mock_get_inspector, mock_should):
        from aidefense.runtime.agentsec.patchers.bedrock import _ConverseStreamInspectionWrapper

        mock_inspector = MagicMock()
        mock_inspector.inspect_conversation.return_value = Decision.block(reasons=["unsafe"])
        mock_get_inspector.return_value = mock_inspector

        _state._state = {"initialized": True, "llm_mode": "enforce"}

        events = _make_converse_stream_events(["bad content"])
        wrapper = _ConverseStreamInspectionWrapper(iter(events), [{"role": "user", "content": "hi"}], {})

        with pytest.raises(SecurityPolicyError):
            list(wrapper)

    @patch("aidefense.runtime.agentsec.patchers.bedrock._should_inspect", return_value=True)
    @patch("aidefense.runtime.agentsec.patchers.bedrock._get_inspector")
    def test_empty_stream_no_inspection(self, mock_get_inspector, mock_should):
        from aidefense.runtime.agentsec.patchers.bedrock import _ConverseStreamInspectionWrapper

        mock_inspector = MagicMock()
        mock_get_inspector.return_value = mock_inspector

        wrapper = _ConverseStreamInspectionWrapper(iter([]), [{"role": "user", "content": "hi"}], {})
        list(wrapper)

        mock_inspector.inspect_conversation.assert_not_called()

    @patch("aidefense.runtime.agentsec.patchers.bedrock._should_inspect", return_value=True)
    @patch("aidefense.runtime.agentsec.patchers.bedrock._get_inspector")
    def test_buffer_capped_at_max_size(self, mock_get_inspector, mock_should):
        from aidefense.runtime.agentsec.patchers.bedrock import (
            _ConverseStreamInspectionWrapper,
            MAX_STREAMING_BUFFER_SIZE,
        )

        mock_inspector = MagicMock()
        mock_inspector.inspect_conversation.return_value = Decision.allow()
        mock_get_inspector.return_value = mock_inspector

        huge_chunk = "x" * (MAX_STREAMING_BUFFER_SIZE + 100)
        events = _make_converse_stream_events([huge_chunk])
        wrapper = _ConverseStreamInspectionWrapper(iter(events), [{"role": "user", "content": "hi"}], {})
        list(wrapper)

        assert len(wrapper._buffer) <= MAX_STREAMING_BUFFER_SIZE


# ===========================================================================
# _InvokeModelStreamInspectionWrapper
# ===========================================================================


class TestInvokeModelStreamInspectionWrapper:
    """Tests for the InvokeModel streaming inspection wrapper."""

    @patch("aidefense.runtime.agentsec.patchers.bedrock._should_inspect", return_value=True)
    @patch("aidefense.runtime.agentsec.patchers.bedrock._get_inspector")
    def test_yields_all_events_and_accumulates_text(self, mock_get_inspector, mock_should):
        from aidefense.runtime.agentsec.patchers.bedrock import _InvokeModelStreamInspectionWrapper

        mock_inspector = MagicMock()
        mock_inspector.inspect_conversation.return_value = Decision.allow()
        mock_get_inspector.return_value = mock_inspector

        chunks = ["Hello", " world"]
        events = _make_invoke_model_stream_events(chunks)
        wrapper = _InvokeModelStreamInspectionWrapper(
            iter(events), [{"role": "user", "content": "hi"}], {}, "anthropic.claude-3"
        )

        collected = list(wrapper)
        assert len(collected) == len(events)
        assert wrapper._buffer == "Hello world"

    @patch("aidefense.runtime.agentsec.patchers.bedrock._should_inspect", return_value=True)
    @patch("aidefense.runtime.agentsec.patchers.bedrock._get_inspector")
    def test_final_inspection_on_stream_end(self, mock_get_inspector, mock_should):
        from aidefense.runtime.agentsec.patchers.bedrock import _InvokeModelStreamInspectionWrapper

        mock_inspector = MagicMock()
        mock_inspector.inspect_conversation.return_value = Decision.allow()
        mock_get_inspector.return_value = mock_inspector

        events = _make_invoke_model_stream_events(["chunk"])
        wrapper = _InvokeModelStreamInspectionWrapper(
            iter(events), [{"role": "user", "content": "hi"}], {}, "model-id"
        )
        list(wrapper)

        assert mock_inspector.inspect_conversation.called
        assert wrapper._final_inspection_done

    @patch("aidefense.runtime.agentsec.patchers.bedrock._should_inspect", return_value=True)
    @patch("aidefense.runtime.agentsec.patchers.bedrock._get_inspector")
    def test_titan_format_extraction(self, mock_get_inspector, mock_should):
        from aidefense.runtime.agentsec.patchers.bedrock import _InvokeModelStreamInspectionWrapper

        mock_inspector = MagicMock()
        mock_inspector.inspect_conversation.return_value = Decision.allow()
        mock_get_inspector.return_value = mock_inspector

        data = {"outputText": "Titan response"}
        events = [{"chunk": {"bytes": json.dumps(data).encode()}}]
        wrapper = _InvokeModelStreamInspectionWrapper(
            iter(events), [{"role": "user", "content": "hi"}], {}, "amazon.titan"
        )
        list(wrapper)

        assert wrapper._buffer == "Titan response"


# ===========================================================================
# Integration: _wrap_make_api_call wraps streaming
# ===========================================================================


class TestWrapMakeApiCallStreaming:
    """Verify that _wrap_make_api_call wraps streaming operations."""

    @patch("aidefense.runtime.agentsec.patchers.bedrock._should_inspect", return_value=True)
    @patch("aidefense.runtime.agentsec.patchers.bedrock._get_inspector")
    @patch("aidefense.runtime.agentsec.patchers.bedrock.resolve_gateway_settings", return_value=None)
    def test_converse_stream_wrapped(self, mock_gw, mock_get_inspector, mock_should):
        from aidefense.runtime.agentsec.patchers.bedrock import (
            _wrap_make_api_call,
            _ConverseStreamInspectionWrapper,
        )

        mock_inspector = MagicMock()
        mock_inspector.inspect_conversation.return_value = Decision.allow()
        mock_get_inspector.return_value = mock_inspector

        fake_stream = iter(_make_converse_stream_events(["hello"]))
        original_response = {"stream": fake_stream, "ResponseMetadata": {}}

        wrapped_fn = MagicMock(return_value=original_response)
        instance = MagicMock()
        instance._service_model.service_name = "bedrock-runtime"

        result = _wrap_make_api_call(
            wrapped_fn,
            instance,
            ("ConverseStream", {"modelId": "test-model", "messages": [{"role": "user", "content": [{"text": "hi"}]}]}),
            {},
        )

        assert isinstance(result["stream"], _ConverseStreamInspectionWrapper)

    @patch("aidefense.runtime.agentsec.patchers.bedrock._should_inspect", return_value=True)
    @patch("aidefense.runtime.agentsec.patchers.bedrock._get_inspector")
    @patch("aidefense.runtime.agentsec.patchers.bedrock.resolve_gateway_settings", return_value=None)
    def test_invoke_model_stream_wrapped(self, mock_gw, mock_get_inspector, mock_should):
        from aidefense.runtime.agentsec.patchers.bedrock import (
            _wrap_make_api_call,
            _InvokeModelStreamInspectionWrapper,
        )

        mock_inspector = MagicMock()
        mock_inspector.inspect_conversation.return_value = Decision.allow()
        mock_get_inspector.return_value = mock_inspector

        fake_stream = iter(_make_invoke_model_stream_events(["hello"]))
        original_response = {"body": fake_stream, "ResponseMetadata": {}}

        wrapped_fn = MagicMock(return_value=original_response)
        instance = MagicMock()
        instance._service_model.service_name = "bedrock-runtime"

        body = json.dumps({"messages": [{"role": "user", "content": "hi"}]}).encode()
        result = _wrap_make_api_call(
            wrapped_fn,
            instance,
            ("InvokeModelWithResponseStream", {"modelId": "test-model", "body": body}),
            {},
        )

        assert isinstance(result["body"], _InvokeModelStreamInspectionWrapper)
