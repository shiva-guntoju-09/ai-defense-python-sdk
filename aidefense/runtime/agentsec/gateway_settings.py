"""Gateway settings dataclass for agentsec gateway configuration."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class GatewaySettings:
    """Resolved settings for a single gateway connection.

    This is the final, fully-resolved configuration used by patchers
    to make gateway calls. All inheritance and defaults have been applied
    before creating this object.

    Attributes:
        url: The gateway URL to proxy requests through.
        api_key: API key for Bearer token auth (used when auth_mode="api_key").
        auth_mode: Authentication mode - "api_key", "aws_sigv4", or "google_adc".
        fail_open: If True, allow the original request on gateway failure.
        timeout: Timeout in seconds for gateway calls.
        retry_total: Total number of retries on failure.
        retry_backoff: Backoff factor between retries.
        retry_status_codes: HTTP status codes that trigger a retry.
    """

    url: str
    api_key: Optional[str] = None
    auth_mode: str = "api_key"  # "api_key" | "aws_sigv4" | "google_adc"
    fail_open: bool = True
    timeout: int = 60
    retry_total: int = 3
    retry_backoff: float = 0.5
    retry_status_codes: List[int] = field(
        default_factory=lambda: [429, 500, 502, 503, 504]
    )
