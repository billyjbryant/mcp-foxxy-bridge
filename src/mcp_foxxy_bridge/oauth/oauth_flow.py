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

"""Complete OAuth flow implementation for MCP Remote Python."""

import asyncio
import json
import threading
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from mcp_foxxy_bridge.utils.logging import get_logger

from .config import OAUTH_USER_AGENT
from .coordination import cleanup_lockfile, coordinate_auth
from .events import EventEmitter
from .oauth_client_provider import OAuthClientProvider
from .types import OAuthClientInformation, OAuthProviderOptions, OAuthTokens
from .utils import setup_signal_handlers

logger = get_logger(__name__, facility="OAUTH")


class OAuthFlow:
    """Complete OAuth authentication flow manager."""

    def __init__(self, options: OAuthProviderOptions) -> None:
        self.options = options
        self.provider = OAuthClientProvider(options)
        self.events = EventEmitter()
        # Bridge server handles OAuth callbacks, no separate callback server needed
        self._auth_result: dict[str, Any] | None = None
        self._auth_completed = threading.Event()

        # Set up event handlers
        self.events.on("auth_success", self._handle_auth_success)
        self.events.on("auth_error", self._handle_auth_error)

        # Set up cleanup on exit
        setup_signal_handlers(self._cleanup)

    def _handle_auth_success(self, data: dict[str, Any]) -> None:
        """Handle successful authorization callback."""
        self._auth_result = {"success": True, "data": data}
        self._auth_completed.set()

    def _handle_auth_error(self, data: dict[str, Any]) -> None:
        """Handle authorization error callback."""
        self._auth_result = {"success": False, "error": data}
        self._auth_completed.set()

    def _cleanup(self) -> None:
        """Clean up resources."""
        # No callback server to stop - bridge server handles OAuth callbacks
        cleanup_lockfile(self.provider.server_url_hash)

    def discover_endpoints(self) -> dict[str, str]:
        """Discover OAuth endpoints from the server."""
        # Extract base URL from server URL
        parsed_url = urlparse(self.options.server_url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

        # Try OpenID Connect discovery first on the MCP server
        discovery_urls = [
            f"{base_url}/.well-known/openid_configuration",
            f"{base_url}/.well-known/oauth-authorization-server",
        ]

        for discovery_url in discovery_urls:
            try:
                # Secure HTTP request with configurable SSL verification
                verify_ssl = getattr(self.options, "verify_ssl", True)
                response = httpx.get(
                    discovery_url, timeout=10, verify=verify_ssl, headers={"User-Agent": OAUTH_USER_AGENT}
                )
                if response.status_code == 200:
                    config = response.json()
                    logger.info(
                        "Discovered OAuth endpoints via well-known URL for server '%s'",
                        self.options.server_name or "UNKNOWN",
                    )
                    return {
                        "authorization_endpoint": config.get("authorization_endpoint"),
                        "token_endpoint": config.get("token_endpoint"),
                        "registration_endpoint": config.get("registration_endpoint"),
                        "userinfo_endpoint": config.get("userinfo_endpoint"),
                    }
            except (httpx.HTTPError, json.JSONDecodeError):
                continue

        # Fallback to common paths (original behavior)
        logger.debug("Using fallback OAuth endpoints for server '%s'", self.options.server_name or "UNKNOWN")
        return {
            "authorization_endpoint": f"{base_url}/oauth/authorize",
            "token_endpoint": f"{base_url}/oauth/token",
            "registration_endpoint": f"{base_url}/oauth/register",
            "userinfo_endpoint": f"{base_url}/oauth/userinfo",
        }

    def register_client(self, registration_endpoint: str) -> OAuthClientInformation:
        """Register OAuth client with the server."""
        existing_client = self.provider.client_information()
        if existing_client:
            return existing_client

        metadata = self.provider.client_metadata()

        try:
            verify_ssl = getattr(self.options, "verify_ssl", True)
            response = httpx.post(
                registration_endpoint,
                json={
                    "redirect_uris": metadata.redirect_uris,
                    "client_name": metadata.client_name,
                    "client_uri": metadata.client_uri,
                    "token_endpoint_auth_method": metadata.token_endpoint_auth_method,
                    "grant_types": metadata.grant_types,
                    "response_types": metadata.response_types,
                    "scope": metadata.scope,
                    "software_id": metadata.software_id,
                    "software_version": metadata.software_version,
                },
                headers={"Content-Type": "application/json", "User-Agent": OAUTH_USER_AGENT},
                timeout=10,
                verify=verify_ssl,
            )

            if response.status_code == 201:
                client_data = response.json()
                client_info = OAuthClientInformation(
                    client_id=client_data["client_id"],
                    client_secret=client_data.get("client_secret"),
                    client_id_issued_at=client_data.get("client_id_issued_at"),
                    client_secret_expires_at=client_data.get("client_secret_expires_at"),
                )

                self.provider.save_client_information(client_info)
                return client_info

            msg = f"Client registration failed: {response.status_code} - {response.text}"
            raise RuntimeError(msg)

        except httpx.HTTPError as e:
            msg = f"Failed to register OAuth client: {e}"
            raise RuntimeError(msg) from e

    def exchange_code_for_tokens(
        self, token_endpoint: str, auth_code: str, client_info: OAuthClientInformation
    ) -> OAuthTokens:
        """Exchange authorization code for access tokens."""
        code_verifier = self.provider.code_verifier()
        if not code_verifier:
            raise RuntimeError("Code verifier not found")

        # Debug logging for token exchange
        logger.debug(f"Token exchange - Authorization code length: {len(auth_code)}")
        logger.debug(f"Token exchange - Code verifier length: {len(code_verifier)}")
        logger.debug(f"Token exchange - Redirect URI: {self.provider.redirect_url}")
        logger.debug(f"Token exchange - Client ID: {client_info.client_id}")
        logger.debug(f"Token exchange - Token endpoint: {token_endpoint}")

        data = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": self.provider.redirect_url,
            "client_id": client_info.client_id,
            "code_verifier": code_verifier,
        }

        # CRITICAL FIX: Some OAuth servers require client_secret in POST body, not Basic auth
        # Try POST body authentication first for broader compatibility
        auth = None
        if client_info.client_secret:
            logger.debug("Using client secret in POST body for token exchange")
            data["client_secret"] = client_info.client_secret
        else:
            logger.debug("Using public client authentication (PKCE only)")

        # Enhanced debug logging for the actual request
        logger.debug(f"Token exchange request data: {data}")
        logger.debug(f"Token exchange auth method: {'post_body' if client_info.client_secret else 'public'}")

        try:
            verify_ssl = getattr(self.options, "verify_ssl", True)
            response = httpx.post(
                token_endpoint,
                data=data,
                auth=auth,
                headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": OAUTH_USER_AGENT},
                timeout=10,
                verify=verify_ssl,
            )

            # Enhanced debug logging for response
            logger.debug(f"Token exchange response status: {response.status_code}")
            logger.debug(f"Token exchange response headers: {dict(response.headers)}")

            if response.status_code == 200:
                token_data = response.json()
                tokens = OAuthTokens(
                    access_token=token_data["access_token"],
                    refresh_token=token_data.get("refresh_token"),
                    token_type=token_data.get("token_type", "Bearer"),
                    expires_in=token_data.get("expires_in"),
                    scope=token_data.get("scope"),
                )

                self.provider.save_tokens(tokens)
                logger.info("Token exchange successful")
                return tokens

            # Enhanced error logging
            logger.error(f"Token exchange failed with status {response.status_code}")
            logger.error(f"Response body: {response.text}")
            msg = f"Token exchange failed: {response.status_code} - {response.text}"
            raise RuntimeError(msg)

        except httpx.HTTPError as e:
            logger.exception("HTTP error during token exchange: %s", e)
            msg = f"Failed to exchange code for tokens: {e}"
            raise RuntimeError(msg) from e

    async def authenticate(self, skip_browser: bool = False) -> OAuthTokens:
        """Perform complete OAuth authentication flow."""
        # Check for existing valid tokens
        existing_tokens = self.provider.tokens()
        if existing_tokens and not skip_browser:
            logger.info("Using existing tokens for server '%s'", self.options.server_name or "UNKNOWN")
            return existing_tokens

        logger.info("Starting OAuth authentication flow for server '%s'", self.options.server_name or "UNKNOWN")

        # Discover OAuth endpoints
        endpoints = self.discover_endpoints()
        if not endpoints.get("authorization_endpoint") or not endpoints.get("token_endpoint"):
            raise RuntimeError("Could not discover OAuth endpoints")

        # Check if we should coordinate with other processes
        # Note: callback_port is now the bridge server port since OAuth is integrated
        should_start_auth, _ = coordinate_auth(self.provider.server_url_hash, self.options.callback_port, self.events)

        if not should_start_auth:
            # Another process handled authentication
            tokens = self.provider.tokens()
            if tokens:
                return tokens
            raise RuntimeError("Authentication failed in coordinating process")

        # Register OAuth client if needed
        if endpoints.get("registration_endpoint"):
            client_info = self.register_client(endpoints["registration_endpoint"])
        else:
            retrieved_client_info: OAuthClientInformation | None = self.provider.client_information()
            if not retrieved_client_info:
                raise RuntimeError("No OAuth client information available and no registration endpoint")
            client_info = retrieved_client_info

        # No need to start callback server - bridge server handles OAuth callbacks
        try:
            # Build authorization URL and redirect user
            auth_url = self.provider.build_authorization_url(endpoints["authorization_endpoint"], client_info.client_id)

            if not skip_browser:
                self.provider.redirect_to_authorization(auth_url)
            else:
                logger.info(
                    "Visit this URL to authorize server '%s': %s", self.options.server_name or "UNKNOWN", auth_url
                )

            # Wait for tokens to be saved by bridge server's OAuth callback
            logger.info("Waiting for authorization callback for server '%s'", self.options.server_name or "UNKNOWN")

            timeout = 300  # 5 minutes
            start_time = time.time()
            last_log_time = start_time

            while time.time() - start_time < timeout:
                # Check if tokens were saved by the bridge server's callback handler
                tokens = self.provider.tokens()
                if tokens:
                    elapsed = time.time() - start_time
                    logger.success("Authentication successful after %.1f seconds!", elapsed)  # type: ignore[attr-defined]
                    return tokens

                current_time = time.time()
                elapsed = current_time - start_time
                remaining = timeout - elapsed
                if current_time - last_log_time >= 10:
                    logger.info(
                        "OAuth callback pending for server '%s' (%.1fs elapsed, %.1fs remaining)",
                        self.options.server_name or "UNKNOWN",
                        elapsed,
                        remaining,
                    )
                    last_log_time = current_time

                await asyncio.sleep(1.0)

            # Provide helpful error message for redirect issues
            elapsed = time.time() - start_time
            error_msg = f"OAuth authentication timed out after {elapsed:.1f} seconds"
            logger.error("[%s] OAuth timeout: %s", self.options.server_name or "UNKNOWN", error_msg)
            raise RuntimeError(error_msg)

        finally:
            self._cleanup()

    def refresh_tokens(self, refresh_token: str) -> OAuthTokens:
        """Refresh access tokens using refresh token."""
        # For token refresh, try to use the OAuth issuer first if available
        token_endpoint = None

        # Check if we have a configured OAuth issuer for refresh operations
        if hasattr(self.options, "oauth_issuer") and self.options.oauth_issuer:
            logger.debug("[%s] Using configured OAuth issuer for token refresh", self.options.server_name or "UNKNOWN")
            oauth_issuer = self.options.oauth_issuer

            # Try OAuth issuer endpoints for refresh
            refresh_discovery_urls = [
                f"{oauth_issuer}/.well-known/openid_configuration",
                f"{oauth_issuer}/.well-known/oauth-authorization-server",
            ]

            for discovery_url in refresh_discovery_urls:
                try:
                    verify_ssl = getattr(self.options, "verify_ssl", True)
                    response = httpx.get(
                        discovery_url, timeout=10, verify=verify_ssl, headers={"User-Agent": OAUTH_USER_AGENT}
                    )
                    if response.status_code == 200:
                        config = response.json()
                        token_endpoint = config.get("token_endpoint")
                        if token_endpoint:
                            server_name = self.options.server_name or "UNKNOWN"
                            logger.debug("[%s] Found token endpoint via OAuth issuer discovery", server_name)
                            break
                except (httpx.HTTPError, json.JSONDecodeError):
                    continue

            # If discovery failed, try common OAuth issuer paths
            if not token_endpoint:
                token_endpoint = f"{oauth_issuer}/oauth/token"
                logger.debug("[%s] Using fallback OAuth issuer token endpoint", self.options.server_name or "UNKNOWN")

        # If no OAuth issuer or it failed, fall back to server endpoints
        if not token_endpoint:
            server_name = self.options.server_name or "UNKNOWN"
            logger.debug("[%s] Falling back to server endpoints for token refresh", server_name)
            endpoints = self.discover_endpoints()
            token_endpoint = endpoints.get("token_endpoint")

        if not token_endpoint:
            raise RuntimeError("Token endpoint not available")

        client_info = self.provider.client_information()
        if not client_info:
            raise RuntimeError("Client information not available")

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_info.client_id,
        }

        auth = None
        if client_info.client_secret:
            auth = (client_info.client_id, client_info.client_secret)

        try:
            verify_ssl = getattr(self.options, "verify_ssl", True)
            response = httpx.post(
                token_endpoint,
                data=data,
                auth=auth,
                headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": OAUTH_USER_AGENT},
                timeout=10,
                verify=verify_ssl,
            )

            if response.status_code == 200:
                token_data = response.json()
                tokens = OAuthTokens(
                    access_token=token_data["access_token"],
                    refresh_token=token_data.get("refresh_token", refresh_token),
                    token_type=token_data.get("token_type", "Bearer"),
                    expires_in=token_data.get("expires_in"),
                    scope=token_data.get("scope"),
                )

                self.provider.save_tokens(tokens)
                return tokens

            msg = f"Token refresh failed: {response.status_code} - {response.text}"
            raise RuntimeError(msg)

        except httpx.HTTPError as e:
            msg = f"Failed to refresh tokens: {e}"
            raise RuntimeError(msg) from e

    def invalidate_credentials(self) -> None:
        """Invalidate and remove all stored credentials."""
        self.provider.invalidate_credentials()
        self._cleanup()
