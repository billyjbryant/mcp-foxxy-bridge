"""Complete OAuth flow implementation for MCP Remote Python."""

import json
import logging
import threading
import time
from typing import Any
from urllib.parse import urlparse

import requests

from .coordination import cleanup_lockfile, coordinate_auth
from .events import EventEmitter
from .oauth_client_provider import OAuthClientProvider
from .types import OAuthClientInformation, OAuthProviderOptions, OAuthTokens
from .utils import setup_signal_handlers

logger = logging.getLogger(__name__)


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
                # Secure HTTP request with proper SSL verification
                response = requests.get(discovery_url, timeout=10, verify=True)  # type: ignore[attr-defined, no-untyped-call]
                if response.status_code == 200:
                    config = response.json()
                    logger.info("Discovered OAuth endpoints via well-known URL")
                    return {
                        "authorization_endpoint": config.get("authorization_endpoint"),
                        "token_endpoint": config.get("token_endpoint"),
                        "registration_endpoint": config.get("registration_endpoint"),
                        "userinfo_endpoint": config.get("userinfo_endpoint"),
                    }
            except (requests.RequestException, json.JSONDecodeError):  # type: ignore[attr-defined]
                continue

        # Fallback to common paths (original behavior)
        logger.debug("Using fallback OAuth endpoints")
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
            response = requests.post(  # type: ignore[attr-defined, no-untyped-call]  # type: ignore[no-untyped-call]
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
                headers={"Content-Type": "application/json"},
                timeout=10,
                verify=True,  # Ensure SSL verification
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

        except requests.RequestException as e:  # type: ignore[attr-defined]
            msg = f"Failed to register OAuth client: {e}"
            raise RuntimeError(msg) from e

    def exchange_code_for_tokens(
        self, token_endpoint: str, auth_code: str, client_info: OAuthClientInformation
    ) -> OAuthTokens:
        """Exchange authorization code for access tokens."""
        code_verifier = self.provider.code_verifier()
        if not code_verifier:
            raise RuntimeError("Code verifier not found")

        data = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": self.provider.redirect_url,
            "client_id": client_info.client_id,
            "code_verifier": code_verifier,
        }

        # Add client authentication
        auth = None
        if client_info.client_secret:
            auth = (client_info.client_id, client_info.client_secret)

        try:
            response = requests.post(  # type: ignore[attr-defined, no-untyped-call]  # type: ignore[no-untyped-call]
                token_endpoint,
                data=data,
                auth=auth,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10,
                verify=True,  # Ensure SSL verification
            )

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
                return tokens

            msg = f"Token exchange failed: {response.status_code} - {response.text}"
            raise RuntimeError(msg)

        except requests.RequestException as e:  # type: ignore[attr-defined]
            msg = f"Failed to exchange code for tokens: {e}"
            raise RuntimeError(msg) from e

    def authenticate(self, skip_browser: bool = False) -> OAuthTokens:
        """Perform complete OAuth authentication flow."""
        # Check for existing valid tokens
        existing_tokens = self.provider.tokens()
        if existing_tokens and not skip_browser:
            logger.info("Using existing tokens")
            return existing_tokens

        logger.info("Starting OAuth authentication flow...")

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
                logger.info(f"Visit this URL to authorize: {auth_url}")

            # Wait for tokens to be saved by bridge server's OAuth callback
            logger.info("Waiting for authorization callback...")
            logger.info("If you're redirected to an invalid URL instead of the bridge server,")
            logger.info("this may be due to a bug in the OAuth provider's redirect handling.")

            timeout = 300  # 5 minutes
            start_time = time.time()

            while time.time() - start_time < timeout:
                # Check if tokens were saved by the bridge server's callback handler
                tokens = self.provider.tokens()
                if tokens:
                    logger.info("Authentication successful!")
                    return tokens

                # Brief pause before checking again
                time.sleep(1.0)

            # Provide helpful error message for redirect issues
            error_msg = (
                "Authentication timed out. If you were redirected to an invalid URL "
                "instead of the bridge server callback, this indicates a bug in the "
                "OAuth provider's redirect URI handling. The provider should redirect "
                f"to: {self.provider.redirect_url}"
            )
            raise RuntimeError(error_msg)

        finally:
            self._cleanup()

    def refresh_tokens(self, refresh_token: str) -> OAuthTokens:
        """Refresh access tokens using refresh token."""
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
            response = requests.post(  # type: ignore[attr-defined, no-untyped-call]  # type: ignore[no-untyped-call]
                token_endpoint,
                data=data,
                auth=auth,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10,
                verify=True,  # Ensure SSL verification
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

        except requests.RequestException as e:  # type: ignore[attr-defined]
            msg = f"Failed to refresh tokens: {e}"
            raise RuntimeError(msg) from e

    def invalidate_credentials(self) -> None:
        """Invalidate and remove all stored credentials."""
        self.provider.invalidate_credentials()
        self._cleanup()
