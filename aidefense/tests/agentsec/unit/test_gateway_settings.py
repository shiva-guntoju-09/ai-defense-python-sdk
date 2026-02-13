"""Tests for GatewaySettings dataclass."""

import pytest
from aidefense.runtime.agentsec.gateway_settings import GatewaySettings


class TestGatewaySettings:
    """Tests for GatewaySettings dataclass construction and defaults."""

    def test_minimal_construction(self):
        """Only url is required; everything else has defaults."""
        gs = GatewaySettings(url="https://gw.example.com")
        assert gs.url == "https://gw.example.com"
        assert gs.api_key is None
        assert gs.auth_mode == "api_key"
        assert gs.fail_open is True
        assert gs.timeout == 60
        assert gs.retry_total == 3
        assert gs.retry_backoff == 0.5
        assert gs.retry_status_codes == [429, 500, 502, 503, 504]

    def test_full_construction(self):
        """All fields can be set explicitly."""
        gs = GatewaySettings(
            url="https://gw.example.com",
            api_key="secret",
            auth_mode="aws_sigv4",
            fail_open=False,
            timeout=10,
            retry_total=5,
            retry_backoff=2.0,
            retry_status_codes=[500],
        )
        assert gs.url == "https://gw.example.com"
        assert gs.api_key == "secret"
        assert gs.auth_mode == "aws_sigv4"
        assert gs.fail_open is False
        assert gs.timeout == 10
        assert gs.retry_total == 5
        assert gs.retry_backoff == 2.0
        assert gs.retry_status_codes == [500]

    def test_retry_status_codes_mutable_default(self):
        """Each instance gets its own copy of retry_status_codes."""
        gs1 = GatewaySettings(url="a")
        gs2 = GatewaySettings(url="b")
        gs1.retry_status_codes.append(999)
        assert 999 not in gs2.retry_status_codes

    def test_google_adc_auth_mode(self):
        gs = GatewaySettings(url="https://gw.example.com", auth_mode="google_adc")
        assert gs.auth_mode == "google_adc"
