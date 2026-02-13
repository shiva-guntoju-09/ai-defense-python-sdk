"""Tests for the shared resolve_gateway_settings() in patchers/_base.py."""

import pytest

from aidefense.runtime.agentsec import _state
from aidefense.runtime.agentsec._context import gateway
from aidefense.runtime.agentsec.patchers._base import resolve_gateway_settings


@pytest.fixture(autouse=True)
def reset_state():
    """Reset state before and after each test."""
    _state.reset()
    yield
    _state.reset()


class TestResolveGatewaySettings:
    """Tests for the shared LLM gateway resolver."""

    def test_returns_none_when_api_mode(self):
        """When integration mode is 'api', resolver returns None."""
        _state.set_state(
            initialized=True,
            llm_integration_mode="api",
        )
        assert resolve_gateway_settings("openai") is None

    def test_returns_none_when_no_provider_config(self):
        """When gateway mode but no provider configured, returns None."""
        _state.set_state(
            initialized=True,
            llm_integration_mode="gateway",
        )
        assert resolve_gateway_settings("openai") is None

    def test_returns_none_when_gateways_exist_but_no_default(self):
        """Named gateways exist for provider, but none marked default."""
        _state.set_state(
            initialized=True,
            llm_integration_mode="gateway",
            gateway_mode={
                "llm_gateways": {
                    "openai-special": {
                        "gateway_url": "https://special.example.com",
                        "gateway_api_key": "key",
                        "provider": "openai",
                        # no default: true
                    },
                },
            },
        )
        # Without an active named gateway, nothing is auto-selected
        assert resolve_gateway_settings("openai") is None

        # But with a named gateway context, it resolves
        with gateway("openai-special"):
            settings = resolve_gateway_settings("openai")
            assert settings is not None
            assert settings.url == "https://special.example.com"

    def test_returns_provider_default(self):
        """When provider is configured, returns its settings."""
        _state.set_state(
            initialized=True,
            llm_integration_mode="gateway",
            gateway_mode={
                "llm_gateways": {
                    "openai-default": {
                        "gateway_url": "https://gw.example.com/openai",
                        "gateway_api_key": "key-123",
                        "provider": "openai",
                        "default": True,
                    },
                },
            },
        )
        settings = resolve_gateway_settings("openai")
        assert settings is not None
        assert settings.url == "https://gw.example.com/openai"
        assert settings.api_key == "key-123"
        assert settings.auth_mode == "api_key"

    def test_named_gateway_overrides_provider(self):
        """When a named gateway is active and matches, it wins over provider."""
        _state.set_state(
            initialized=True,
            llm_integration_mode="gateway",
            gateway_mode={
                "llm_gateways": {
                    "openai-default": {
                        "gateway_url": "https://provider.example.com",
                        "gateway_api_key": "provider-key",
                        "provider": "openai",
                        "default": True,
                    },
                    "math-gw": {
                        "gateway_url": "https://math.example.com",
                        "gateway_api_key": "math-key",
                        "provider": "openai",
                    },
                },
            },
        )

        # Without gateway context, returns provider default
        settings = resolve_gateway_settings("openai")
        assert settings.url == "https://provider.example.com"

        # With gateway context, returns named gateway
        with gateway("math-gw"):
            settings = resolve_gateway_settings("openai")
            assert settings.url == "https://math.example.com"
            assert settings.api_key == "math-key"

    def test_named_gateway_provider_mismatch_falls_through(self):
        """Named gateway scoped to 'openai' is not used for 'bedrock' calls."""
        _state.set_state(
            initialized=True,
            llm_integration_mode="gateway",
            gateway_mode={
                "llm_gateways": {
                    "bedrock-default": {
                        "gateway_url": "https://bedrock-default.example.com",
                        "gateway_api_key": "bedrock-key",
                        "provider": "bedrock",
                        "default": True,
                    },
                    "openai-gw": {
                        "gateway_url": "https://openai.example.com",
                        "gateway_api_key": "openai-key",
                        "provider": "openai",
                    },
                },
            },
        )

        with gateway("openai-gw"):
            # For bedrock calls, the openai-scoped gateway doesn't apply
            settings = resolve_gateway_settings("bedrock")
            assert settings.url == "https://bedrock-default.example.com"

    def test_named_gateway_no_provider_field(self):
        """Named gateway without provider field applies to any provider."""
        _state.set_state(
            initialized=True,
            llm_integration_mode="gateway",
            gateway_mode={
                "llm_gateways": {
                    "catch-all-gw": {
                        "gateway_url": "https://catch-all.example.com",
                        "gateway_api_key": "catch-all-key",
                    },
                },
            },
        )
        with gateway("catch-all-gw"):
            settings = resolve_gateway_settings("openai")
            assert settings.url == "https://catch-all.example.com"
            settings = resolve_gateway_settings("bedrock")
            assert settings.url == "https://catch-all.example.com"

    def test_auth_mode_inherited_from_provider(self):
        """Named gateway inherits auth_mode from its provider config."""
        _state.set_state(
            initialized=True,
            llm_integration_mode="gateway",
            gateway_mode={
                "llm_gateways": {
                    "bedrock-default": {
                        "gateway_url": "https://bedrock.example.com",
                        "auth_mode": "aws_sigv4",
                        "provider": "bedrock",
                        "default": True,
                    },
                    "bedrock-analytics": {
                        "gateway_url": "https://analytics.example.com",
                        "provider": "bedrock",
                        # No auth_mode -- should inherit aws_sigv4
                    },
                },
            },
        )
        with gateway("bedrock-analytics"):
            settings = resolve_gateway_settings("bedrock")
            assert settings.auth_mode == "aws_sigv4"

    def test_settings_inherit_defaults(self):
        """Provider config with no timeout/retry inherits llm_defaults."""
        _state.set_state(
            initialized=True,
            llm_integration_mode="gateway",
            gateway_mode={
                "llm_defaults": {
                    "fail_open": False,
                    "timeout": 5,
                    "retry": {
                        "total": 10,
                    },
                },
                "llm_gateways": {
                    "openai-default": {
                        "gateway_url": "https://gw.example.com",
                        "gateway_api_key": "key",
                        "provider": "openai",
                        "default": True,
                    },
                },
            },
        )
        settings = resolve_gateway_settings("openai")
        assert settings.fail_open is False
        assert settings.timeout == 5
        assert settings.retry_total == 10

    def test_per_gateway_override_beats_defaults(self):
        """Per-gateway settings override llm_defaults."""
        _state.set_state(
            initialized=True,
            llm_integration_mode="gateway",
            gateway_mode={
                "llm_defaults": {
                    "fail_open": True,
                    "timeout": 1,
                },
                "llm_gateways": {
                    "openai-default": {
                        "gateway_url": "https://gw.example.com",
                        "gateway_api_key": "key",
                        "provider": "openai",
                        "default": True,
                        "fail_open": False,
                        "timeout": 99,
                    },
                },
            },
        )
        settings = resolve_gateway_settings("openai")
        assert settings.fail_open is False
        assert settings.timeout == 99

    def test_skip_inspection_returns_none(self):
        """When skip_inspection is active, resolver returns None."""
        from aidefense.runtime.agentsec._context import skip_inspection

        _state.set_state(
            initialized=True,
            llm_integration_mode="gateway",
            gateway_mode={
                "llm_gateways": {
                    "openai-default": {
                        "gateway_url": "https://gw.example.com",
                        "gateway_api_key": "key",
                        "provider": "openai",
                        "default": True,
                    },
                },
            },
        )
        with skip_inspection(llm=True):
            assert resolve_gateway_settings("openai") is None
