"""Tests for new _state.py features (resolve functions, new getters)."""

import pytest

from aidefense.runtime.agentsec import _state
from aidefense.runtime.agentsec.gateway_settings import GatewaySettings


@pytest.fixture(autouse=True)
def reset_state():
    _state.reset()
    yield
    _state.reset()


class TestSetStateWithGatewayMode:
    """Tests for set_state() with the new gateway_mode dict."""

    def test_provider_defaults_stored(self):
        _state.set_state(
            initialized=True,
            llm_integration_mode="gateway",
            gateway_mode={
                "llm_gateways": {
                    "openai-default": {
                        "gateway_url": "https://gw/openai",
                        "gateway_api_key": "k1",
                        "provider": "openai",
                        "default": True,
                    },
                },
            },
        )
        p = _state.get_default_gateway_for_provider("openai")
        assert p is not None
        assert p["gateway_url"] == "https://gw/openai"

    def test_default_true_without_provider_not_indexed(self):
        """Entry with default: true but no provider field is not indexed."""
        _state.set_state(
            initialized=True,
            llm_integration_mode="gateway",
            gateway_mode={
                "llm_gateways": {
                    "catch-all": {
                        "gateway_url": "https://gw/catch-all",
                        "default": True,
                        # no provider field
                    },
                },
            },
        )
        # Should not be returned for any provider
        assert _state.get_default_gateway_for_provider("openai") is None
        assert _state.get_default_gateway_for_provider("bedrock") is None
        # But still accessible as a named gateway
        assert _state.get_llm_gateway("catch-all") is not None

    def test_provider_without_default_not_auto_selected(self):
        """Entry with provider but no default flag is not auto-selected."""
        _state.set_state(
            initialized=True,
            llm_integration_mode="gateway",
            gateway_mode={
                "llm_gateways": {
                    "bedrock-analytics": {
                        "gateway_url": "https://gw/analytics",
                        "provider": "bedrock",
                        # no default: true
                    },
                },
            },
        )
        assert _state.get_default_gateway_for_provider("bedrock") is None

    def test_default_false_not_auto_selected(self):
        """Entry with default: false is not auto-selected."""
        _state.set_state(
            initialized=True,
            llm_integration_mode="gateway",
            gateway_mode={
                "llm_gateways": {
                    "openai-special": {
                        "gateway_url": "https://gw/special",
                        "provider": "openai",
                        "default": False,
                    },
                },
            },
        )
        assert _state.get_default_gateway_for_provider("openai") is None

    def test_multiple_defaults_last_wins(self):
        """When multiple entries claim default for same provider, last wins."""
        _state.set_state(
            initialized=True,
            llm_integration_mode="gateway",
            gateway_mode={
                "llm_gateways": {
                    "openai-first": {
                        "gateway_url": "https://gw/first",
                        "provider": "openai",
                        "default": True,
                    },
                    "openai-second": {
                        "gateway_url": "https://gw/second",
                        "provider": "openai",
                        "default": True,
                    },
                },
            },
        )
        p = _state.get_default_gateway_for_provider("openai")
        assert p is not None
        assert p["gateway_url"] == "https://gw/second"

    def test_llm_gateways_stored(self):
        _state.set_state(
            initialized=True,
            llm_integration_mode="gateway",
            gateway_mode={
                "llm_gateways": {
                    "math": {"gateway_url": "https://gw/math"},
                },
            },
        )
        gw = _state.get_llm_gateway("math")
        assert gw is not None
        assert gw["gateway_url"] == "https://gw/math"
        assert _state.get_llm_gateway("nonexistent") is None

    def test_mcp_gateways_stored(self):
        _state.set_state(
            initialized=True,
            mcp_integration_mode="gateway",
            gateway_mode={
                "mcp_gateways": {
                    "https://mcp.example.com": {"gateway_url": "https://gw/mcp"},
                    "https://mcp2.example.com": {"gateway_url": "https://gw/mcp2"},
                },
            },
        )
        per_url = _state.get_mcp_gateway_for_url("https://mcp.example.com")
        assert per_url is not None
        assert per_url["gateway_url"] == "https://gw/mcp"

        per_url2 = _state.get_mcp_gateway_for_url("https://mcp2.example.com")
        assert per_url2 is not None
        assert per_url2["gateway_url"] == "https://gw/mcp2"

        assert _state.get_mcp_gateway_for_url("https://other.com") is None

    def test_llm_defaults_override(self):
        _state.set_state(
            initialized=True,
            gateway_mode={
                "llm_defaults": {
                    "fail_open": False,
                    "timeout": 99,
                    "retry": {"total": 7, "backoff_factor": 2.0},
                },
            },
        )
        assert _state._gw_llm_fail_open is False
        assert _state._gw_llm_timeout == 99
        assert _state._gw_llm_retry_total == 7
        assert _state._gw_llm_retry_backoff == 2.0

    def test_mcp_defaults_override(self):
        _state.set_state(
            initialized=True,
            gateway_mode={
                "mcp_defaults": {
                    "timeout": 30,
                },
            },
        )
        assert _state._gw_mcp_timeout == 30
        # Other defaults should still be at hardcoded values
        assert _state._gw_mcp_fail_open is True


class TestSetStateWithApiMode:
    """Tests for set_state() with the new api_mode dict."""

    def test_api_llm_config_unpacked(self):
        _state.set_state(
            initialized=True,
            api_mode={
                "llm": {
                    "mode": "enforce",
                    "endpoint": "https://api.example.com",
                    "api_key": "secret",
                    "rules": ["jailbreak"],
                    "entity_types": ["EMAIL"],
                },
            },
        )
        assert _state.get_api_mode_llm() == "enforce"
        assert _state.get_api_mode_llm_endpoint() == "https://api.example.com"
        assert _state.get_api_mode_llm_api_key() == "secret"
        assert _state.get_llm_rules() == ["jailbreak"]
        assert _state.get_llm_entity_types() == ["EMAIL"]

    def test_api_mcp_config_unpacked(self):
        _state.set_state(
            initialized=True,
            api_mode={
                "mcp": {
                    "mode": "monitor",
                    "endpoint": "https://api.mcp.example.com",
                    "api_key": "mcp-secret",
                },
            },
        )
        assert _state.get_api_mode_mcp() == "monitor"
        assert _state.get_api_mode_mcp_endpoint() == "https://api.mcp.example.com"
        assert _state.get_api_mode_mcp_api_key() == "mcp-secret"

    def test_api_llm_defaults_unpacked(self):
        _state.set_state(
            initialized=True,
            api_mode={
                "llm_defaults": {
                    "fail_open": True,
                    "timeout": 10,
                    "retry": {"total": 5},
                },
            },
        )
        assert _state.get_api_llm_fail_open() is True
        assert _state.get_api_llm_timeout() == 10
        assert _state.get_api_llm_retry_total() == 5

    def test_api_mcp_defaults_unpacked(self):
        _state.set_state(
            initialized=True,
            api_mode={
                "mcp_defaults": {
                    "fail_open": False,
                    "timeout": 15,
                },
            },
        )
        assert _state.get_api_mcp_fail_open() is False
        assert _state.get_api_mcp_timeout() == 15

    def test_invalid_api_mode_raises(self):
        from aidefense.runtime.agentsec.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError, match="api_mode.llm.mode"):
            _state.set_state(
                initialized=True,
                api_mode={"llm": {"mode": "invalid"}},
            )


class TestResolveGatewaySettings:
    """Tests for resolve_llm_gateway_settings and resolve_mcp_gateway_settings."""

    def test_resolve_llm_with_defaults(self):
        _state.set_state(
            initialized=True,
            gateway_mode={
                "llm_defaults": {
                    "fail_open": False,
                    "timeout": 5,
                },
            },
        )
        settings = _state.resolve_llm_gateway_settings(
            {"gateway_url": "https://gw.example.com", "gateway_api_key": "key"},
        )
        assert isinstance(settings, GatewaySettings)
        assert settings.url == "https://gw.example.com"
        assert settings.fail_open is False  # from defaults
        assert settings.timeout == 5  # from defaults

    def test_resolve_llm_per_gateway_overrides(self):
        _state.set_state(
            initialized=True,
            gateway_mode={
                "llm_defaults": {"fail_open": True, "timeout": 1},
            },
        )
        settings = _state.resolve_llm_gateway_settings(
            {"gateway_url": "https://gw.example.com", "fail_open": False, "timeout": 99},
        )
        assert settings.fail_open is False
        assert settings.timeout == 99

    def test_resolve_llm_auth_mode_from_provider(self):
        _state.set_state(
            initialized=True,
            gateway_mode={
                "llm_gateways": {
                    "bedrock-default": {
                        "gateway_url": "https://x",
                        "auth_mode": "aws_sigv4",
                        "provider": "bedrock",
                        "default": True,
                    },
                },
            },
        )
        settings = _state.resolve_llm_gateway_settings(
            {"gateway_url": "https://gw-named.example.com"},
            provider="bedrock",
        )
        assert settings.auth_mode == "aws_sigv4"

    def test_resolve_mcp_with_defaults(self):
        _state.set_state(
            initialized=True,
            gateway_mode={
                "mcp_defaults": {"fail_open": False, "timeout": 20},
            },
        )
        settings = _state.resolve_mcp_gateway_settings(
            {"gateway_url": "https://mcp-gw.example.com"},
        )
        assert settings.fail_open is False
        assert settings.timeout == 20


class TestReset:
    """Tests for reset() clearing all new state."""

    def test_reset_clears_gateway_mode(self):
        _state.set_state(
            initialized=True,
            llm_integration_mode="gateway",
            gateway_mode={
                "llm_gateways": {
                    "openai-default": {"gateway_url": "https://gw", "provider": "openai", "default": True},
                    "math": {"gateway_url": "https://math"},
                },
                "mcp_gateways": {"https://mcp.example.com": {"gateway_url": "https://gw/mcp"}},
                "llm_defaults": {"timeout": 99},
            },
        )
        _state.reset()

        assert _state.is_initialized() is False
        assert _state.get_default_gateway_for_provider("openai") is None
        assert _state.get_llm_gateway("math") is None
        assert _state.get_mcp_gateway_for_url("https://mcp.example.com") is None
        assert _state._gw_llm_timeout == 60  # back to default

    def test_reset_clears_api_mode(self):
        _state.set_state(
            initialized=True,
            api_mode={
                "llm_defaults": {"fail_open": True, "timeout": 99},
                "llm": {"mode": "enforce"},
            },
        )
        _state.reset()
        assert _state.get_api_llm_fail_open() is False  # back to default
        assert _state.get_api_llm_timeout() == 5  # back to default
        assert _state.get_api_mode_llm() is None
