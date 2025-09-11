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

"""Python OAuth Client Provider for MCP Remote."""

import base64
import hashlib
import secrets
import time
import uuid
import webbrowser
from urllib.parse import urlencode

from mcp_foxxy_bridge.utils.logging import get_logger

from .types import (
    OAuthClientInformation,
    OAuthClientMetadata,
    OAuthProviderOptions,
    OAuthTokens,
)
from .utils import (
    cleanup_auth_files,
    get_server_url_hash,
    load_client_info,
    load_code_verifier,
    load_tokens,
    save_client_info,
    save_code_verifier,
    save_tokens,
)

logger = get_logger(__name__, facility="OAUTH")


class OAuthClientProvider:
    """OAuth client provider for handling authentication flow."""

    def __init__(self, options: OAuthProviderOptions) -> None:
        self.options = options
        self.server_url_hash = get_server_url_hash(options.server_url)
        self.server_name = options.server_name  # Store server name for proper directory organization
        self.callback_path = options.callback_path or "/oauth/callback"
        self.client_name = options.client_name or "MCP CLI Client"
        self.client_uri = options.client_uri or "https://github.com/modelcontextprotocol/mcp-cli"
        self.software_id = options.software_id or "2e6dc280-f3c3-4e01-99a7-8181dbd1d23d"
        self.software_version = options.software_version or "1.0.0"
        self.static_oauth_client_metadata = options.static_oauth_client_metadata
        self.static_oauth_client_info = options.static_oauth_client_info
        self.authorize_resource = options.authorize_resource
        self._state = str(uuid.uuid4())
        self._code_verifier: str | None = None
        self._code_challenge: str | None = None

    @property
    def redirect_url(self) -> str:
        """Get the OAuth redirect URL."""
        return f"http://{self.options.host}:{self.options.callback_port}{self.callback_path}"

    @property
    def state(self) -> str:
        """Get the OAuth state parameter."""
        return self._state

    def generate_pkce_pair(self) -> tuple[str, str]:
        """Generate PKCE code verifier and challenge."""
        if self._code_verifier is None:
            code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("utf-8").rstrip("=")
            self._code_verifier = code_verifier

        if self._code_challenge is None:
            # At this point, _code_verifier is guaranteed to be not None
            if self._code_verifier is None:  # For mypy
                raise RuntimeError("PKCE code verifier not set")
            challenge_bytes = hashlib.sha256(self._code_verifier.encode("utf-8")).digest()
            code_challenge = base64.urlsafe_b64encode(challenge_bytes).decode("utf-8").rstrip("=")
            self._code_challenge = code_challenge

        # Both should be set by now
        if self._code_verifier is None:
            raise RuntimeError("PKCE code verifier not generated")
        if self._code_challenge is None:
            raise RuntimeError("PKCE code challenge not generated")
        return self._code_verifier, self._code_challenge

    def client_metadata(self) -> OAuthClientMetadata:
        """Get OAuth client metadata."""
        if self.static_oauth_client_metadata:
            return OAuthClientMetadata(**self.static_oauth_client_metadata)

        return OAuthClientMetadata(
            redirect_uris=[self.redirect_url],
            client_name=self.client_name,
            client_uri=self.client_uri,
            token_endpoint_auth_method="client_secret_basic",  # noqa: S106
            grant_types=["authorization_code"],
            response_types=["code"],
            scope=None,  # Let OAuth server determine appropriate scopes
            software_id=self.software_id,
            software_version=self.software_version,
        )

    def client_information(self) -> OAuthClientInformation | None:
        """Get saved OAuth client information."""
        if self.static_oauth_client_info:
            return OAuthClientInformation(**self.static_oauth_client_info)

        client_data = load_client_info(self.server_url_hash, self.server_name)
        if client_data:
            return OAuthClientInformation(**client_data)

        return None

    def save_client_information(self, client_info: OAuthClientInformation) -> None:
        """Save OAuth client information."""
        if not self.static_oauth_client_info:
            client_data = {
                "client_id": client_info.client_id,
                "client_secret": client_info.client_secret,
                "client_id_issued_at": client_info.client_id_issued_at,
                "client_secret_expires_at": client_info.client_secret_expires_at,
            }
            save_client_info(self.server_url_hash, client_data, self.server_name)

    def tokens(self) -> OAuthTokens | None:
        """Get saved OAuth tokens."""
        token_data = load_tokens(self.server_url_hash, self.server_name)
        if token_data:
            # Check if token is still valid (not expired)
            if "expires_in" in token_data and token_data["expires_in"] and "issued_at" in token_data:
                issued_at = token_data["issued_at"]
                current_time = int(time.time())
                if (current_time - issued_at) >= token_data["expires_in"]:
                    # Token is expired, return None
                    return None

            # Remove 'issued_at' and 'oauth_issuer' fields before creating OAuthTokens object
            oauth_token_data = {k: v for k, v in token_data.items() if k not in ["issued_at", "oauth_issuer"]}
            return OAuthTokens(**oauth_token_data)
        return None

    def tokens_including_expired(self) -> OAuthTokens | None:
        """Get saved OAuth tokens even if expired (for refresh token access)."""
        token_data = load_tokens(self.server_url_hash, self.server_name)
        if token_data:
            # Remove 'issued_at' field before creating OAuthTokens object
            oauth_token_data = {k: v for k, v in token_data.items() if k not in ["issued_at", "oauth_issuer"]}
            return OAuthTokens(**oauth_token_data)
        return None

    def stored_oauth_issuer(self) -> str | None:
        """Get stored OAuth issuer from token data."""
        token_data = load_tokens(self.server_url_hash, self.server_name)
        if token_data:
            return token_data.get("oauth_issuer")
        return None

    def save_tokens(self, tokens: OAuthTokens) -> None:
        """Save OAuth tokens with OAuth issuer info for future refresh operations."""
        token_data = {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "token_type": tokens.token_type,
            "expires_in": tokens.expires_in,
            "scope": tokens.scope,
        }

        # Store OAuth issuer info if available for future refresh operations
        if hasattr(self.options, "oauth_issuer") and self.options.oauth_issuer:
            token_data["oauth_issuer"] = self.options.oauth_issuer

        save_tokens(self.server_url_hash, token_data, self.server_name)

    def save_code_verifier(self, code_verifier: str) -> None:
        """Save PKCE code verifier."""
        save_code_verifier(self.server_url_hash, code_verifier, self.server_name)

    def code_verifier(self) -> str | None:
        """Get saved PKCE code verifier."""
        return load_code_verifier(self.server_url_hash, self.server_name)

    def build_authorization_url(self, authorization_endpoint: str, client_id: str) -> str:
        """Build the OAuth authorization URL."""
        code_verifier, code_challenge = self.generate_pkce_pair()
        self.save_code_verifier(code_verifier)

        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": self.redirect_url,
            "state": self.state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }

        if self.authorize_resource:
            params["resource"] = self.authorize_resource

        return f"{authorization_endpoint}?{urlencode(params)}"

    def redirect_to_authorization(self, authorization_url: str) -> None:
        """Open the authorization URL in the default browser."""
        logger.info("[%s] Opening authorization URL in browser", self.server_name or "UNKNOWN")
        webbrowser.open(authorization_url)

    def invalidate_credentials(self) -> None:
        """Remove all saved credentials and tokens."""
        cleanup_auth_files(self.server_url_hash, self.server_name)
        self._state = str(uuid.uuid4())
        self._code_verifier = None
        self._code_challenge = None
