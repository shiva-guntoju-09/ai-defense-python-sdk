"""Unit tests for the Mistral client patcher."""

import pytest
from unittest.mock import MagicMock, patch

from aidefense.runtime.agentsec.patchers.mistral import (
    patch_mistral,
    _normalize_messages,
    _extract_assistant_content,
    _wrap_complete,
)
from aidefense.runtime.agentsec.exceptions import SecurityPolicyError
from aidefense.runtime.agentsec.decision import Decision
from aidefense.runtime.agentsec import _state
from aidefense.runtime.agentsec._context import clear_inspection_context
from aidefense.runtime.agentsec.patchers import reset_registry


@pytest.fixture(autouse=True)
def reset_state():
    """Reset agentsec state and patch registry before each test."""
    _state.reset()
    reset_registry()
    clear_inspection_context()
    import aidefense.runtime.agentsec.patchers.mistral as mistral_module
    mistral_module._inspector = None
    yield
    _state.reset()
    reset_registry()
    clear_inspection_context()
    mistral_module._inspector = None


class TestMistralNormalization:
    """Test message normalization for Mistral/OpenAI-style formats."""

    def test_normalize_dict_messages(self):
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        result = _normalize_messages(messages)
        assert len(result) == 2
        assert result[0]["role"] == "user" and result[0]["content"] == "Hello"
        assert result[1]["role"] == "assistant" and result[1]["content"] == "Hi there"

    def test_normalize_skips_tool_role(self):
        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "tool", "content": "tool result"},
        ]
        result = _normalize_messages(messages)
        assert len(result) == 1
        assert result[0]["role"] == "user"

    def test_normalize_empty_or_none(self):
        assert _normalize_messages([]) == []
        assert _normalize_messages(None) == []
        assert _normalize_messages("not a list") == []


class TestMistralExtractAssistantContent:
    """Test extraction of assistant text from ChatCompletionResponse."""

    def test_extract_from_choices_message_content(self):
        msg = MagicMock()
        msg.content = "Assistant reply"
        choice = MagicMock()
        choice.message = msg
        response = MagicMock()
        response.choices = [choice]
        assert _extract_assistant_content(response) == "Assistant reply"

    def test_extract_empty_when_no_choices(self):
        response = MagicMock()
        response.choices = []
        assert _extract_assistant_content(response) == ""

    def test_extract_empty_when_no_message(self):
        response = object()
        assert _extract_assistant_content(response) == ""


class TestMistralPatcherInspection:
    """Test that complete wrapper calls inspector and enforces decision."""

    @patch("aidefense.runtime.agentsec.patchers.mistral._get_inspector")
    def test_sync_complete_calls_inspector(self, mock_get_inspector):
        mock_inspector = MagicMock()
        mock_inspector.inspect_conversation.return_value = Decision.allow(reasons=[])
        mock_get_inspector.return_value = mock_inspector

        _state.set_state(
            initialized=True,
            llm_rules=None,
            api_mode_fail_open_llm=True,
            api_mode_llm="monitor",
        )
        clear_inspection_context()

        mock_wrapped = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Hi"))]
        mock_wrapped.return_value = mock_response

        result = _wrap_complete(
            mock_wrapped,
            MagicMock(),
            (),
            {"model": "mistral-large-latest", "messages": [{"role": "user", "content": "Hello"}]},
        )

        assert mock_inspector.inspect_conversation.call_count >= 1
        assert result == mock_response

    @patch("aidefense.runtime.agentsec.patchers.mistral._get_inspector")
    def test_enforce_mode_raises_on_block(self, mock_get_inspector):
        mock_inspector = MagicMock()
        mock_inspector.inspect_conversation.return_value = Decision.block(reasons=["jailbreak"])
        mock_get_inspector.return_value = mock_inspector

        _state.set_state(
            initialized=True,
            llm_rules=None,
            api_mode_fail_open_llm=True,
            api_mode_llm="enforce",
        )
        clear_inspection_context()

        mock_wrapped = MagicMock()

        with pytest.raises(SecurityPolicyError):
            _wrap_complete(
                mock_wrapped,
                MagicMock(),
                (),
                {"model": "mistral-large-latest", "messages": [{"role": "user", "content": "Hello"}]},
            )


class TestMistralGatewayMode:
    """Test gateway mode behavior (parity with OpenAI/Cohere)."""

    def test_should_use_gateway_returns_false_when_off(self):
        from aidefense.runtime.agentsec.patchers.mistral import _should_use_gateway
        _state.set_state(initialized=True, llm_integration_mode="api")
        assert _should_use_gateway() is False

    def test_should_use_gateway_returns_false_when_not_configured(self):
        from aidefense.runtime.agentsec.patchers.mistral import _should_use_gateway
        _state.set_state(initialized=True, llm_integration_mode="gateway")
        with patch("aidefense.runtime.agentsec.patchers.mistral._state.get_provider_gateway_url", return_value=None):
            assert _should_use_gateway() is False

    def test_should_use_gateway_returns_true_when_configured(self):
        """_should_use_gateway returns True when gateway mode and URL+key are set."""
        from aidefense.runtime.agentsec.patchers.mistral import _should_use_gateway
        _state.set_state(initialized=True, llm_integration_mode="gateway")
        with patch("aidefense.runtime.agentsec.patchers.mistral._state.get_provider_gateway_url", return_value="https://gateway.example.com/mistral"):
            with patch("aidefense.runtime.agentsec.patchers.mistral._state.get_provider_gateway_api_key", return_value="mistral-key"):
                assert _should_use_gateway() is True

    @patch("aidefense.runtime.agentsec.patchers.mistral._state")
    @patch("httpx.Client")
    def test_gateway_call_sync_sends_to_gateway_with_api_key(self, mock_httpx_client, mock_state):
        """Gateway sync call POSTs to gateway URL with api-key header."""
        from aidefense.runtime.agentsec.patchers.mistral import _handle_gateway_call_sync

        mock_state.get_provider_gateway_url.return_value = "https://gateway.example.com/mistral"
        mock_state.get_provider_gateway_api_key.return_value = "mistral-gateway-key"
        mock_state.get_gateway_mode_fail_open_llm.return_value = True

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "resp-1",
            "choices": [{"message": {"role": "assistant", "content": "Hi"}}],
            "usage": {},
        }
        mock_response.raise_for_status = MagicMock()
        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_response
        mock_httpx_client.return_value.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_httpx_client.return_value.__exit__ = MagicMock(return_value=False)

        kwargs = {"model": "mistral-large-latest", "messages": [{"role": "user", "content": "Hello"}]}
        result = _handle_gateway_call_sync(kwargs, [], {}, stream=False)

        mock_client_instance.post.assert_called_once()
        call_kwargs = mock_client_instance.post.call_args[1]
        assert call_kwargs["headers"]["Authorization"] == "Bearer mistral-gateway-key"
        assert "application/json" in call_kwargs["headers"]["Content-Type"]
        assert call_kwargs["json"]["model"] == "mistral-large-latest"
        assert len(call_kwargs["json"]["messages"]) == 1
        assert result is not None


class TestMistralPatchApply:
    """Test patch_mistral() behavior."""

    def test_returns_false_when_mistral_not_installed(self):
        with patch("aidefense.runtime.agentsec.patchers.mistral.safe_import", return_value=None):
            assert patch_mistral() is False

    def test_returns_true_when_already_patched(self):
        with patch("aidefense.runtime.agentsec.patchers.mistral.is_patched", return_value=True):
            assert patch_mistral() is True
