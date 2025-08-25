"""MCP OAuth Python - Python implementation of OAuth flow for MCP Remote.

This package provides a complete OAuth 2.0 / OpenID Connect implementation
for authenticating with MCP (Model Context Protocol) servers.
"""

from .config import (
    OAUTH_CLIENT_NAME,
    OAUTH_CLIENT_URI,
    OAUTH_SOFTWARE_ID,
    OAUTH_SOFTWARE_VERSION,
    OAUTH_USER_AGENT,
    get_oauth_client_config,
)
from .coordination import (
    cleanup_lockfile,
    coordinate_auth,
    create_lazy_auth_coordinator,
)
from .events import EventEmitter
from .oauth_client_provider import OAuthClientProvider
from .oauth_flow import OAuthFlow
from .types import (
    OAuthCallbackServerOptions,
    OAuthClientInformation,
    OAuthClientMetadata,
    OAuthProviderOptions,
    OAuthTokens,
    StaticOAuthClientInformationFull,
    StaticOAuthClientMetadata,
)
from .utils import cleanup_auth_files, find_available_port, get_server_url_hash

__version__ = "1.0.0"
__author__ = "Assistant"
__email__ = "assistant@anthropic.com"

__all__ = [
    # OAuth config constants
    "OAUTH_CLIENT_NAME",
    "OAUTH_CLIENT_URI",
    "OAUTH_SOFTWARE_ID",
    "OAUTH_SOFTWARE_VERSION",
    "OAUTH_USER_AGENT",
    "EventEmitter",
    "OAuthCallbackServerOptions",
    "OAuthClientInformation",
    "OAuthClientMetadata",
    # Main classes
    "OAuthClientProvider",
    "OAuthFlow",
    # Types
    "OAuthProviderOptions",
    "OAuthTokens",
    "StaticOAuthClientInformationFull",
    "StaticOAuthClientMetadata",
    "cleanup_auth_files",
    "cleanup_lockfile",
    # Functions
    "coordinate_auth",
    "create_lazy_auth_coordinator",
    "find_available_port",
    "get_config_dir",
    "get_oauth_client_config",
    "get_server_url_hash",
]
