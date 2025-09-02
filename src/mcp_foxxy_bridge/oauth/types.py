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

"""OAuth types and interfaces for MCP Remote Python implementation."""

from dataclasses import dataclass
from typing import Any

from .events import EventEmitter


@dataclass
class OAuthProviderOptions:
    """Configuration options for OAuth provider."""

    server_url: str
    callback_port: int
    host: str
    callback_path: str | None = "/oauth/callback"
    config_dir: str | None = None
    client_name: str | None = "MCP CLI Client"
    client_uri: str | None = "https://github.com/modelcontextprotocol/mcp-cli"
    software_id: str | None = "2e6dc280-f3c3-4e01-99a7-8181dbd1d23d"
    software_version: str | None = "1.0.0"
    static_oauth_client_metadata: dict[str, Any] | None = None
    static_oauth_client_info: dict[str, Any] | None = None
    authorize_resource: str | None = None
    server_name: str | None = None  # Added server name for proper storage organization
    oauth_issuer: str | None = None  # OAuth issuer URL for discovery fallback
    verify_ssl: bool = True  # SSL certificate verification (default: secure)


@dataclass
class OAuthCallbackServerOptions:
    """Configuration options for OAuth callback server."""

    port: int
    path: str
    events: EventEmitter


@dataclass
class OAuthTokens:
    """OAuth token storage."""

    access_token: str
    refresh_token: str | None = None
    token_type: str = "Bearer"  # noqa: S105
    expires_in: int | None = None
    scope: str | None = None


@dataclass
class OAuthClientInformation:
    """OAuth client information."""

    client_id: str
    client_secret: str | None = None
    client_id_issued_at: int | None = None
    client_secret_expires_at: int | None = None


@dataclass
class OAuthClientMetadata:
    """OAuth client metadata."""

    redirect_uris: list[str]
    client_name: str | None = None
    client_uri: str | None = None
    token_endpoint_auth_method: str = "client_secret_basic"  # noqa: S105
    grant_types: list[str] | None = None
    response_types: list[str] | None = None
    scope: str | None = None
    software_id: str | None = None
    software_version: str | None = None

    def __post_init__(self) -> None:
        """Post-init setup for OAuthClientMetadata."""
        if self.grant_types is None:
            self.grant_types = ["authorization_code"]
        if self.response_types is None:
            self.response_types = ["code"]


StaticOAuthClientMetadata = OAuthClientMetadata | None
StaticOAuthClientInformationFull = OAuthClientInformation | None
