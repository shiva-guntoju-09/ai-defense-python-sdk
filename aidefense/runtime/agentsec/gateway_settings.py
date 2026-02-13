# Copyright 2025 Cisco Systems, Inc. and its affiliates
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

"""Gateway settings dataclass for agentsec multi-gateway support."""

from dataclasses import dataclass, field
from typing import List, Optional


# Valid auth_mode values
VALID_AUTH_MODES = {"api_key", "aws_sigv4", "google_adc"}


@dataclass
class GatewaySettings:
    """
    Resolved gateway configuration for a single LLM or MCP gateway.

    This is the final, merged configuration used at runtime by patchers.
    It combines per-gateway overrides with category defaults (llm_defaults
    or mcp_defaults) and hardcoded fallbacks.

    Attributes:
        url: Gateway URL to proxy requests through.
        api_key: API key for gateway authentication (used when auth_mode="api_key").
        auth_mode: Authentication method for the gateway.
            - "api_key": Authorization: Bearer {api_key} header (default)
            - "aws_sigv4": AWS SigV4 signed request via boto3 IAM credentials
            - "google_adc": OAuth2 token from Google Application Default Credentials
        fail_open: If True, allow requests to pass through on gateway errors.
        timeout: Timeout for gateway requests in seconds.
        retry_total: Total number of retry attempts.
        retry_backoff: Exponential backoff factor between retries in seconds.
        retry_status_codes: HTTP status codes that trigger a retry.
    """

    url: str
    api_key: Optional[str] = None
    auth_mode: str = "api_key"
    fail_open: bool = True
    timeout: int = 1
    retry_total: int = 3
    retry_backoff: float = 0.5
    retry_status_codes: List[int] = field(
        default_factory=lambda: [429, 500, 502, 503, 504]
    )

    def __post_init__(self) -> None:
        """Validate auth_mode after initialization."""
        if self.auth_mode not in VALID_AUTH_MODES:
            raise ValueError(
                f"Invalid auth_mode '{self.auth_mode}'. "
                f"Must be one of: {', '.join(sorted(VALID_AUTH_MODES))}"
            )
