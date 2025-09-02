#
# Copyright (C) 2024 Billy Bryant
# Portions copyright (C) 2024 Sergey Parfenyuk (original MIT-licensed author)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# MIT License attribution: Portions of this file were originally licensed
# under the MIT License by Sergey Parfenyuk (2024).
#

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
