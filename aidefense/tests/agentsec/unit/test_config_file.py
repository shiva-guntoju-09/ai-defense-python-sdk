"""Tests for config_file.py -- YAML config loading with ${ENV_VAR} substitution."""

import os
import tempfile

import pytest

from aidefense.runtime.agentsec.config_file import load_config_file
from aidefense.runtime.agentsec.exceptions import ConfigurationError


class TestLoadConfigFile:
    """Tests for load_config_file()."""

    def _write_yaml(self, content: str) -> str:
        """Write YAML content to a temp file and return its path."""
        fd, path = tempfile.mkstemp(suffix=".yaml")
        os.write(fd, content.encode())
        os.close(fd)
        return path

    def test_basic_yaml(self):
        path = self._write_yaml("llm_integration_mode: gateway\n")
        result = load_config_file(path)
        assert result == {"llm_integration_mode": "gateway"}
        os.unlink(path)

    def test_nested_yaml(self):
        content = """\
gateway_mode:
  llm_defaults:
    fail_open: true
    timeout: 3
  llm_gateways:
    openai-default:
      gateway_url: https://gw.example.com
      provider: openai
      default: true
"""
        path = self._write_yaml(content)
        result = load_config_file(path)
        assert result["gateway_mode"]["llm_defaults"]["fail_open"] is True
        assert result["gateway_mode"]["llm_defaults"]["timeout"] == 3
        assert result["gateway_mode"]["llm_gateways"]["openai-default"]["gateway_url"] == "https://gw.example.com"
        os.unlink(path)

    def test_env_var_substitution(self, monkeypatch):
        monkeypatch.setenv("TEST_GW_KEY", "my-secret-key")
        content = """\
gateway_mode:
  llm_gateways:
    openai-default:
      gateway_api_key: ${TEST_GW_KEY}
      provider: openai
      default: true
"""
        path = self._write_yaml(content)
        result = load_config_file(path)
        assert result["gateway_mode"]["llm_gateways"]["openai-default"]["gateway_api_key"] == "my-secret-key"
        os.unlink(path)

    def test_env_var_not_set_raises(self):
        content = """\
gateway_mode:
  llm_gateways:
    openai-default:
      gateway_api_key: ${NONEXISTENT_VAR_12345}
      provider: openai
      default: true
"""
        path = self._write_yaml(content)
        with pytest.raises(ConfigurationError, match="NONEXISTENT_VAR_12345"):
            load_config_file(path)
        os.unlink(path)

    def test_file_not_found(self):
        with pytest.raises(ConfigurationError, match="not found"):
            load_config_file("/nonexistent/agentsec.yaml")

    def test_empty_file(self):
        path = self._write_yaml("")
        result = load_config_file(path)
        assert result == {}
        os.unlink(path)

    def test_invalid_yaml(self):
        path = self._write_yaml(":\n  :\n  - ][")
        with pytest.raises(ConfigurationError, match="Invalid YAML"):
            load_config_file(path)
        os.unlink(path)

    def test_non_mapping_yaml(self):
        path = self._write_yaml("- item1\n- item2\n")
        with pytest.raises(ConfigurationError, match="must contain a YAML mapping"):
            load_config_file(path)
        os.unlink(path)

    def test_mixed_env_and_literal(self, monkeypatch):
        """String with ${VAR} embedded in other text."""
        monkeypatch.setenv("MY_HOST", "gw.example.com")
        content = """\
url: https://${MY_HOST}/v1
"""
        path = self._write_yaml(content)
        result = load_config_file(path)
        assert result["url"] == "https://gw.example.com/v1"
        os.unlink(path)

    def test_non_string_values_preserved(self):
        """Integers, booleans, lists pass through unchanged."""
        content = """\
timeout: 5
fail_open: true
status_codes: [429, 500]
"""
        path = self._write_yaml(content)
        result = load_config_file(path)
        assert result["timeout"] == 5
        assert result["fail_open"] is True
        assert result["status_codes"] == [429, 500]
        os.unlink(path)
