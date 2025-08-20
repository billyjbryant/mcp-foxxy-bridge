#
# MCP Foxxy Bridge - SSE Client Wrapper
#
# Copyright (C) 2024 Billy Bryant
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
"""SSE Client Wrapper with Authentication and Error Handling.

This module provides an enhanced SSE (Server-Sent Events) client wrapper
for connecting to MCP servers with comprehensive authentication support
and automatic error handling capabilities.

Key Features:
    - Support for multiple authentication methods (OAuth, Bearer, API Key, Basic)
    - Automatic OAuth flow initiation on 401 errors
    - Seamless integration with mcp-remote token storage
    - Comprehensive error handling and recovery
    - Detailed logging with server-specific context
    - SSL/TLS verification control

Authentication Methods:
    - OAuth 2.0 with PKCE (automatic token refresh)
    - Bearer token authentication
    - API key authentication (configurable headers)
    - Basic authentication (username/password)
    - Custom header authentication

Example:
    Basic SSE connection:

    >>> async with sse_client_with_logging(
    ...     url="https://api.example.com/v1/sse",
    ...     server_name="example-server"
    ... ) as (read_stream, write_stream):
    ...     # Use MCP client with streams

    OAuth-enabled connection:

    >>> async with sse_client_with_logging(
    ...     url="https://mcp.atlassian.com/v1/sse",
    ...     server_name="atlassian",
    ...     oauth_enabled=True
    ... ) as streams:
    ...     # Automatically handles OAuth flow if needed
"""

import asyncio
import base64
import contextlib
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any
from urllib.parse import urlparse

import httpx
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import JSONRPCMessage

# Import OAuth functionality
from mcp_foxxy_bridge.oauth import OAuthFlow, OAuthProviderOptions, OAuthTokens
from mcp_foxxy_bridge.oauth.utils import get_server_url_hash, load_tokens
from mcp_foxxy_bridge.utils.bridge_config import get_bridge_server_host, get_oauth_port

logger = logging.getLogger(__name__)


def _auto_detect_oauth_issuer(server_url: str) -> str | None:
    """Auto-detect OAuth issuer for well-known providers.

    Args:
        server_url: The MCP server URL

    Returns:
        The detected OAuth issuer URL, or None if not recognized
    """
    parsed_url = urlparse(server_url)
    domain = parsed_url.netloc.lower()

    # Well-known OAuth issuer mappings
    issuer_mappings = {
        "mcp.atlassian.com": "https://auth.atlassian.com",
        # Add more well-known providers here as needed
        # 'api.github.com': 'https://github.com',
        # 'api.google.com': 'https://accounts.google.com',
    }

    return issuer_mappings.get(domain)


async def _discover_oauth_issuer(server_url: str) -> str | None:
    """Attempt to dynamically discover OAuth issuer URL from server.

    Tries to discover OAuth configuration through standard mechanisms:
    1. Check for OpenID Connect discovery endpoints
    2. Check for OAuth authorization server metadata
    3. Look for common OAuth issuer patterns

    Args:
        server_url: The MCP server URL to discover OAuth issuer from

    Returns:
        The discovered OAuth issuer URL, or None if discovery fails
    """
    # Extract base URL from server URL
    parsed_url = urlparse(server_url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

    # Standard discovery endpoints to try
    discovery_endpoints = [
        f"{base_url}/.well-known/openid_configuration",
        f"{base_url}/.well-known/oauth-authorization-server",
        # Try parent domain for multi-service providers
        f"{parsed_url.scheme}://auth.{parsed_url.netloc.split('.', 1)[-1]}/.well-known/openid_configuration"
        if "." in parsed_url.netloc
        else None,
    ]

    # Filter out None values
    discovery_endpoints = [ep for ep in discovery_endpoints if ep is not None]

    async with httpx.AsyncClient(timeout=10.0) as client:
        for endpoint in discovery_endpoints:
            if not endpoint:  # Skip None endpoints
                continue
            try:
                logger.debug("Trying OAuth discovery endpoint")
                response = await client.get(endpoint)
                if response.status_code == 200:
                    config = response.json()
                    issuer = config.get("issuer")
                    if issuer and isinstance(issuer, str):
                        logger.info("Discovered OAuth issuer")
                        return str(issuer)  # Explicit cast to satisfy mypy
            except Exception as e:
                logger.debug("OAuth discovery failed: %s", type(e).__name__)
                continue

    logger.debug("OAuth issuer discovery failed")
    return None


def get_oauth_tokens(server_url: str, server_name: str | None = None) -> OAuthTokens | None:
    """Get OAuth tokens for a server URL.

    Args:
        server_url: The server URL to get tokens for
        server_name: Optional server name for proper storage lookup

    Returns:
        OAuth tokens if found, None otherwise
    """
    try:
        server_url_hash = get_server_url_hash(server_url)
        tokens_data = load_tokens(server_url_hash, server_name)
        if not tokens_data:
            return None

        # Check if token is still valid (not expired) before creating OAuthTokens object
        if "expires_in" in tokens_data and tokens_data["expires_in"] and "issued_at" in tokens_data:
            issued_at = tokens_data["issued_at"]
            current_time = int(time.time())
            if (current_time - issued_at) >= tokens_data["expires_in"]:
                logger.debug("OAuth tokens expired")
                return None

        # Remove 'issued_at' field before creating OAuthTokens object
        oauth_token_data = {k: v for k, v in tokens_data.items() if k != "issued_at"}
        return OAuthTokens(**oauth_token_data)
    except (TypeError, ValueError, KeyError) as e:
        logger.debug("Error reading OAuth tokens: %s", e)
        return None
    except Exception:
        logger.exception("Unexpected error reading OAuth tokens")
        return None


def create_oauth_headers(tokens: OAuthTokens) -> dict[str, str] | None:
    """Create OAuth headers from tokens.

    Args:
        tokens: OAuth tokens

    Returns:
        Headers dictionary or None if invalid tokens
    """
    if not tokens or not tokens.access_token:
        return None

    # Ensure token type is properly capitalized (OAuth 2.0 standard)
    token_type = (tokens.token_type or "Bearer").capitalize()
    return {"Authorization": f"{token_type} {tokens.access_token}"}


class SSEClientWrapper:
    """Enhanced SSE client wrapper with authentication and error handling.

    This class provides a high-level interface for establishing SSE connections
    to MCP servers with comprehensive authentication support, automatic OAuth
    flow handling, and robust error recovery.

    Attributes:
        server_url: The SSE endpoint URL
        server_name: Human-readable server name for logging
        oauth_enabled: Whether OAuth authentication is enabled
        authentication: Authentication configuration dictionary
        verify_ssl: Whether to verify SSL/TLS certificates

    Example:
        >>> client = SSEClientWrapper(
        ...     server_url="https://api.example.com/v1/sse",
        ...     server_name="example-server",
        ...     oauth_enabled=True
        ... )
        >>> async with client.connect() as (read_stream, write_stream):
        ...     # Use streams for MCP communication
    """

    def __init__(
        self,
        server_url: str,
        server_name: str,
        oauth_enabled: bool = False,
        oauth_config: dict[str, Any] | None = None,
        authentication: dict[str, Any] | None = None,
        verify_ssl: bool = True,
        max_oauth_wait_time: int = 300,
    ) -> None:
        """Initialize SSE client wrapper.

        Args:
            server_url: The SSE endpoint URL
            server_name: Human-readable server name for logging and identification
            oauth_enabled: Whether OAuth authentication is enabled for this server
            oauth_config: OAuth configuration dictionary (with issuer, etc.)
            authentication: Authentication configuration dictionary
            verify_ssl: Whether to verify SSL/TLS certificates
            max_oauth_wait_time: Maximum time to wait for OAuth completion in seconds
        """
        self.server_url = server_url.rstrip("/")
        self.server_name = server_name
        self.oauth_enabled = oauth_enabled
        self.oauth_config = oauth_config or {}
        self.authentication = authentication or {}
        self.verify_ssl = verify_ssl
        self.max_oauth_wait_time = max_oauth_wait_time

        # Security: NO logging of any server details, URLs, or authentication info
        logger.debug("SSEClientWrapper initialized")

    @contextlib.asynccontextmanager
    async def connect(
        self, headers: dict[str, Any] | None = None
    ) -> AsyncGenerator[
        tuple[
            MemoryObjectReceiveStream[JSONRPCMessage],
            MemoryObjectSendStream[JSONRPCMessage],
        ],
        None,
    ]:
        """Establish SSE connection with authentication and error handling.

        Creates an SSE connection to the configured server with automatic
        authentication, OAuth flow handling, and comprehensive error recovery.

        Args:
            headers: Optional additional headers for the connection

        Yields:
            Tuple of (read_stream, write_stream) for MCP communication

        Raises:
            ConnectionError: If connection cannot be established
            AuthenticationError: If authentication fails

        Example:
            >>> async with client.connect() as (read_stream, write_stream):
            ...     # Use streams for MCP protocol communication
            ...     await write_stream.send(initialize_request)
            ...     response = await read_stream.receive()
        """
        async with sse_client_with_logging(
            url=self.server_url,
            server_name=self.server_name,
            headers=headers,
            oauth_enabled=self.oauth_enabled,
            authentication=self.authentication,
            verify_ssl=self.verify_ssl,
        ) as streams:
            yield streams


# Core SSE client function with authentication and error handling


@contextlib.asynccontextmanager
async def sse_client_with_logging(
    url: str,
    server_name: str,
    headers: dict[str, Any] | None = None,
    oauth_enabled: bool = False,
    oauth_config: dict[str, Any] | None = None,
    authentication: dict[str, Any] | None = None,
    verify_ssl: bool = True,
) -> AsyncGenerator[
    tuple[
        MemoryObjectReceiveStream[JSONRPCMessage],
        MemoryObjectSendStream[JSONRPCMessage],
    ],
    None,
]:
    """Enhanced SSE client with comprehensive authentication and error handling.

    This function provides the core SSE client functionality with support for
    multiple authentication methods, automatic OAuth flow initiation, and
    robust error handling with detailed logging.

    Args:
        url: SSE endpoint URL
        server_name: Human-readable server name for logging purposes
        headers: Optional headers for the SSE connection
        oauth_enabled: Whether this connection requires OAuth authentication
        oauth_config: OAuth configuration dictionary with provider-specific settings
        authentication: Authentication configuration dictionary
        verify_ssl: Whether to verify SSL/TLS certificates

    Yields:
        Tuple of (read_stream, write_stream) for MCP ClientSession

    Raises:
        ConnectionError: If SSE connection cannot be established
        AuthenticationError: If authentication fails

    Example:
        OAuth-enabled server:

        >>> async with sse_client_with_logging(
        ...     url="https://mcp.atlassian.com/v1/sse",
        ...     server_name="atlassian",
        ...     oauth_enabled=True
        ... ) as (read_stream, write_stream):
        ...     # Connection automatically handles OAuth flow if needed

        API key authentication:

        >>> auth_config = {
        ...     "type": "api_key",
        ...     "key": "your-api-key",
        ...     "header": "X-API-Key"
        ... }
        >>> async with sse_client_with_logging(
        ...     url="https://api.example.com/v1/sse",
        ...     server_name="example",
        ...     authentication=auth_config
        ... ) as streams:
        ...     # Connection uses API key authentication
    """
    logger.debug("Starting SSE client")

    try:
        # Initialize headers with defaults
        connection_headers = _prepare_connection_headers(headers)

        # Apply authentication methods
        await _apply_authentication(connection_headers, authentication, server_name)

        # Handle OAuth-enabled servers
        if oauth_enabled:
            logger.debug("OAuth enabled, loading tokens...")
            await _handle_oauth_authentication(url, connection_headers, server_name, oauth_config)
        else:
            logger.debug("OAuth not enabled")

        # Security: NO logging of connection details or headers
        logger.debug("Attempting SSE connection")
        # Try initial connection
        oauth_retry_attempted = False

        # Function to attempt SSE connection
        async def _try_sse_connection() -> AsyncGenerator[
            tuple[MemoryObjectReceiveStream[JSONRPCMessage], MemoryObjectSendStream[JSONRPCMessage]], None
        ]:
            async with sse_client(url=url, headers=connection_headers) as streams:
                yield streams

        # Try initial connection
        try:
            async with sse_client(url=url, headers=connection_headers) as streams:
                logger.debug("SSE client established")
                yield streams
                return
        except Exception as sse_error:
            logger.debug("SSE error: %s", type(sse_error).__name__)

            # Handle authentication errors with automatic OAuth flow (only try once)
            if oauth_enabled and not oauth_retry_attempted and _is_authentication_error(sse_error):
                logger.warning(
                    "SSE authentication failed for OAuth-enabled server '%s' - initiating automatic OAuth flow",
                    server_name,
                )

                # Attempt automatic OAuth flow and retry
                logger.info("Attempting OAuth token refresh due to authentication failure")

                oauth_retry_attempted = True
                try:
                    if await _handle_oauth_flow_and_retry(url, server_name, connection_headers, oauth_config):
                        # Retry connection with updated tokens in a new context
                        try:
                            async with sse_client(url=url, headers=connection_headers) as streams:
                                logger.info(
                                    "✅ SSE client established after OAuth token refresh for server: %s", server_name
                                )
                                yield streams
                                return
                        except Exception:
                            logger.exception(
                                "SSE connection failed even after OAuth retry for server '%s'",
                                server_name,
                            )
                            raise
                    else:
                        # OAuth flow failed or timed out
                        _log_oauth_failure_guidance(server_name)
                        raise sse_error from None
                except Exception as oauth_error:
                    logger.exception("OAuth retry failed for server '%s'", server_name)
                    _log_oauth_failure_guidance(server_name)
                    # Re-raise the original SSE error, not the OAuth error
                    raise sse_error from oauth_error
            else:
                # Not an auth error, or already tried OAuth retry, or OAuth disabled
                raise

    except Exception as e:
        logger.exception("SSE client failed for server '%s': %s", server_name, e)
        raise
    finally:
        logger.debug("SSE client cleanup completed")


# Authentication helper functions


async def _check_and_refresh_tokens_if_needed(
    oauth_flow: OAuthFlow, tokens: OAuthTokens, server_name: str
) -> OAuthTokens | None:
    """Check if tokens need refresh and attempt refresh if necessary.

    Args:
        oauth_flow: The OAuth flow instance
        tokens: Current tokens
        server_name: Server name for logging

    Returns:
        Refreshed tokens if successful, original tokens if not needed, None if refresh failed
    """
    # Check if token is close to expiring (within 5 minutes)
    if hasattr(tokens, "expires_in") and tokens.expires_in:
        if tokens.expires_in < 300:  # Less than 5 minutes
            logger.info("Token expiring soon, attempting refresh...")

            if tokens.refresh_token:
                try:
                    refreshed_tokens = oauth_flow.refresh_tokens(tokens.refresh_token)
                    logger.info("✅ Successfully refreshed tokens")
                    return refreshed_tokens
                except Exception as e:
                    logger.warning("Failed to refresh tokens: %s", type(e).__name__)
                    logger.info("Will attempt to use existing token anyway")
                    return tokens
            else:
                logger.warning("No refresh token available, cannot auto-refresh")
                return tokens
        else:
            logger.debug("Token still valid, no refresh needed")
            return tokens
    else:
        # No expiration info, assume token is valid
        logger.debug("No expiration info for tokens, assuming valid")
        return tokens


async def _attempt_token_refresh_and_retry(
    url: str, server_name: str, headers: dict[str, str], oauth_enabled: bool
) -> bool:
    """Attempt to refresh OAuth tokens and update headers.

    Args:
        url: Server URL
        server_name: Server name for logging
        headers: Headers dictionary to update
        oauth_enabled: Whether OAuth is enabled for this server

    Returns:
        True if tokens were successfully refreshed, False otherwise
    """
    if not oauth_enabled:
        return False

    try:
        oauth_port = get_oauth_port()  # Use dedicated OAuth port
        bridge_host = get_bridge_server_host()
        oauth_options = OAuthProviderOptions(
            server_url=url,
            callback_port=oauth_port,
            host=bridge_host,
            client_name="MCP Foxxy Bridge",
            client_uri="https://github.com/billybryant/mcp-foxxy-bridge",
            server_name=server_name,
        )
        oauth_flow = OAuthFlow(oauth_options)
        tokens = oauth_flow.provider.tokens()

        if not tokens or not tokens.refresh_token:
            logger.debug("No refresh token available, cannot auto-refresh")
            return False

        logger.info("Attempting automatic token refresh...")
        try:
            refreshed_tokens = oauth_flow.refresh_tokens(tokens.refresh_token)

            # Update headers with new tokens
            oauth_headers = create_oauth_headers(refreshed_tokens)
            if oauth_headers:
                # Remove old authorization header
                headers.pop("Authorization", None)
                # Add new authorization header
                headers.update(oauth_headers)
                logger.info("✅ Successfully refreshed and updated tokens")
                return True
            logger.warning("Failed to create headers from refreshed tokens")
            return False

        except Exception as e:
            logger.warning("Token refresh failed: %s", type(e).__name__)
            return False

    except Exception as e:
        logger.warning("Error during token refresh attempt: %s", type(e).__name__)
        return False


def _prepare_connection_headers(headers: dict[str, Any] | None) -> dict[str, str]:
    """Prepare base connection headers for SSE requests.

    Args:
        headers: Optional user-provided headers

    Returns:
        Dictionary with default SSE headers and user headers
    """
    connection_headers = headers.copy() if headers else {}

    # Add standard SSE headers
    connection_headers.setdefault("User-Agent", "mcp-foxxy-bridge/1.0 (MCP Client)")
    connection_headers.setdefault("Accept", "text/event-stream")
    connection_headers.setdefault("Cache-Control", "no-cache")

    return connection_headers


async def _apply_authentication(
    headers: dict[str, str], authentication: dict[str, Any] | None, server_name: str
) -> None:
    """Apply authentication configuration to request headers.

    Supports multiple authentication methods as specified in issue #10:
    - Bearer token authentication
    - API key authentication (configurable headers)
    - Basic authentication (username/password)

    Args:
        headers: Headers dictionary to modify
        authentication: Authentication configuration
        server_name: Server name for logging
    """
    if not authentication:
        return

    auth_type = authentication.get("type", "").lower()

    if auth_type == "bearer":
        await _apply_bearer_authentication(headers, authentication, server_name)
    elif auth_type == "api_key":
        await _apply_api_key_authentication(headers, authentication, server_name)
    elif auth_type == "basic":
        await _apply_basic_authentication(headers, authentication, server_name)
    else:
        logger.warning("Unknown authentication type: %s", auth_type)


async def _apply_bearer_authentication(headers: dict[str, str], auth_config: dict[str, Any], server_name: str) -> None:
    """Apply Bearer token authentication to headers."""
    token = auth_config.get("token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
        logger.debug("Applied bearer token authentication")
    else:
        logger.warning("Bearer authentication configured but no token provided")


async def _apply_api_key_authentication(headers: dict[str, str], auth_config: dict[str, Any], server_name: str) -> None:
    """Apply API key authentication to headers."""
    key = auth_config.get("key")
    header_name = auth_config.get("header", "X-API-Key")

    if key:
        headers[header_name] = key
        logger.debug("Applied API key authentication")
    else:
        logger.warning("API key authentication configured but no key provided")


async def _apply_basic_authentication(headers: dict[str, str], auth_config: dict[str, Any], server_name: str) -> None:
    """Apply Basic authentication to headers."""
    username = auth_config.get("username")
    password = auth_config.get("password", "")

    if username:
        credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
        headers["Authorization"] = f"Basic {credentials}"
        logger.debug("Applied basic authentication")
    else:
        logger.warning("Basic authentication configured but missing username")


async def _handle_oauth_authentication(
    url: str, headers: dict[str, str], server_name: str, oauth_config: dict[str, Any] | None = None
) -> None:
    """Handle OAuth authentication by loading existing tokens.

    Attempts to load existing OAuth tokens and apply them to the request headers.

    Args:
        url: Server URL for token lookup
        headers: Headers dictionary to update
        server_name: Server name for logging
        oauth_config: OAuth configuration dictionary with provider-specific settings
    """
    logger.info("OAuth-enabled server detected. Checking for existing OAuth tokens.")

    try:
        # OAuth is now integrated with bridge server - use bridge server port
        # Default to standard ports if bridge config isn't available yet
        bridge_host = "127.0.0.1"  # Default bridge host
        bridge_port = 8080  # Default bridge port

        # Try to get bridge config if available
        with contextlib.suppress(RuntimeError):
            bridge_host = get_bridge_server_host()
            # For now, use default bridge port since OAuth is integrated
            # TODO: Pass actual bridge port from server startup

        # Extract OAuth issuer from config if available
        oauth_issuer = None
        if oauth_config:
            oauth_issuer = oauth_config.get("issuer")
            if oauth_issuer:
                logger.debug("Found configured OAuth issuer.")

        oauth_options = OAuthProviderOptions(
            server_url=url,  # MCP server URL for primary discovery
            oauth_issuer=oauth_issuer,  # OAuth issuer for fallback discovery
            callback_port=bridge_port,  # Use bridge server port
            host=bridge_host,
            client_name="MCP Foxxy Bridge",
            client_uri="https://github.com/billybryant/mcp-foxxy-bridge",
            server_name=server_name,  # Pass server name for proper storage organization
        )
        oauth_flow = OAuthFlow(oauth_options)
        tokens = oauth_flow.provider.tokens()
        logger.debug("Loaded OAuth tokens: %s", tokens is not None)

        if tokens:
            # Check token expiration for debugging
            if hasattr(tokens, "expires_in") and tokens.expires_in:
                logger.debug("Token expires in: %s seconds", tokens.expires_in)
            logger.debug("Token type: %s", getattr(tokens, "token_type", "Bearer"))
            # Use the create_oauth_headers function for proper token formatting
            oauth_headers = create_oauth_headers(tokens)
            if oauth_headers:
                headers.update(oauth_headers)
                logger.info("Using existing OAuth tokens for authentication")
                logger.debug("OAuth authorization header added successfully")
                # Log safely without exposing any credential information
                logger.debug("Authorization header configured with token type")
            else:
                logger.warning("Failed to create OAuth headers from tokens")
        else:
            logger.warning("No valid OAuth tokens found. Server may require manual authentication.")

    except (ValueError, KeyError, TypeError) as e:
        logger.warning("OAuth configuration error: %s", e)
    except (FileNotFoundError, OSError) as e:
        logger.debug("OAuth tokens not found or inaccessible: %s", e)
    except Exception:
        logger.exception("Unexpected error loading OAuth tokens")
        # Don't re-raise here as we want to continue without OAuth


async def _initiate_automatic_oauth_flow(
    server_url: str, server_name: str, oauth_config: dict[str, Any] | None = None
) -> None:
    """Automatically initiate OAuth flow for a server that returned 401.

    Performs the complete OAuth flow to get access tokens.

    Args:
        server_url: The server URL that returned 401
        server_name: The server name for identification
        oauth_config: OAuth configuration dictionary with provider-specific settings

    Raises:
        Exception: If OAuth flow initiation fails
    """
    logger.info("Attempting to automatically initiate OAuth flow")

    try:
        oauth_port = get_oauth_port()  # Use dedicated OAuth port
        bridge_host = get_bridge_server_host()
        # Extract OAuth issuer from config if available
        oauth_issuer = None
        if oauth_config:
            oauth_issuer = oauth_config.get("issuer")
            if oauth_issuer:
                logger.debug("Found configured OAuth issuer for automatic flow: [ISSUER_CONFIGURED]")

        oauth_options = OAuthProviderOptions(
            server_url=server_url,  # MCP server URL for primary discovery
            oauth_issuer=oauth_issuer,  # OAuth issuer for fallback discovery
            callback_port=oauth_port,
            host=bridge_host,
            client_name="MCP Foxxy Bridge",
            client_uri="https://github.com/billybryant/mcp-foxxy-bridge",
            server_name=server_name,  # Pass server name for proper storage organization
        )
        oauth_flow = OAuthFlow(oauth_options)
        tokens = oauth_flow.authenticate(skip_browser=False)
        access_token = tokens.access_token if tokens else None

        if access_token:
            logger.info("OAuth flow completed successfully")
            logger.info("User should be able to retry connection now")
        else:
            logger.error("OAuth flow failed")
            raise RuntimeError("OAuth flow did not produce valid tokens")

    except Exception as e:
        logger.exception(f"Unexpected error initiating OAuth flow for '{server_name}': {e}")
        raise


async def _wait_for_oauth_completion_and_retry(
    server_url: str, server_name: str, headers: dict[str, str], max_wait_time: int = 300
) -> bool:
    """Wait for OAuth completion and update headers with new tokens.

    Polls for new OAuth tokens at regular intervals and updates the
    headers dictionary when tokens become available.

    Args:
        server_url: The server URL
        server_name: The server name for logging
        headers: Headers dictionary to update with new OAuth tokens
        max_wait_time: Maximum time to wait in seconds

    Returns:
        True if OAuth completed successfully, False if timed out
    """
    start_time = time.time()
    check_interval = 5  # Check every 5 seconds

    logger.debug("Waiting for OAuth completion (max %d seconds)", max_wait_time)

    while (time.time() - start_time) < max_wait_time:
        await asyncio.sleep(check_interval)

        try:
            bridge_host = get_bridge_server_host()
            oauth_port = get_oauth_port()  # Use dedicated OAuth port
            oauth_options = OAuthProviderOptions(
                server_url=server_url,
                callback_port=oauth_port,
                host=bridge_host,
                client_name="MCP Foxxy Bridge",
                client_uri="https://github.com/billybryant/mcp-foxxy-bridge",
                server_name=server_name,  # Pass server name for proper storage organization
            )
            oauth_flow = OAuthFlow(oauth_options)
            tokens = oauth_flow.provider.tokens()
            access_token = tokens.access_token if tokens else None

            if access_token:
                headers["Authorization"] = f"Bearer {access_token}"
                logger.info("✅ New OAuth tokens detected")
                return True

        except (ValueError, KeyError, TypeError) as e:
            logger.debug("OAuth token configuration error: %s", e)
        except (FileNotFoundError, OSError) as e:
            logger.debug("OAuth tokens not accessible: %s", e)
        except Exception as e:
            logger.warning("Unexpected error checking OAuth tokens: %s", str(e))

        elapsed = int(time.time() - start_time)
        if elapsed % 30 == 0:  # Log progress every 30 seconds
            logger.info("⏳ Still waiting for OAuth completion...")

    logger.warning("⏰ OAuth completion timeout")
    return False


async def _handle_oauth_flow_and_retry(
    server_url: str, server_name: str, headers: dict[str, str], oauth_config: dict[str, Any] | None = None
) -> bool:
    """Handle OAuth flow and retry connection.

    Initiates OAuth flow and waits for completion.

    Args:
        server_url: The server URL
        server_name: The server name for logging
        headers: Headers dictionary to update with OAuth tokens
        oauth_config: OAuth configuration dictionary with provider-specific settings

    Returns:
        True if OAuth completed successfully, False otherwise
    """
    try:
        # Initiate OAuth flow
        await _initiate_automatic_oauth_flow(server_url, server_name, oauth_config)

        logger.info(
            f"🌐 OAuth flow initiated for server '{server_name}'. Please check your browser to complete authorization."
        )

        logger.info("⏳ Waiting for OAuth completion...")
        success = await _wait_for_oauth_completion_and_retry(server_url, server_name, headers, max_wait_time=300)

        if success:
            logger.info("✅ OAuth completed successfully! Retrying connection")
        else:
            logger.warning("⏰ OAuth completion timed out or failed")

        return success

    except Exception as e:
        logger.exception(f"OAuth flow failed for '{server_name}': {e}")
        return False


def _log_oauth_failure_guidance(server_name: str) -> None:
    """Log helpful guidance when OAuth flow fails.

    Provides user-friendly instructions for completing OAuth manually.

    Args:
        server_name: The server name for URL generation
    """
    logger.error("❌ Authentication failed")
    logger.info("💡 OAuth tokens should now be stored for automatic use")
    logger.info("📋 If authentication continues to fail, check your OAuth server configuration")


def _is_authentication_error(exception: Exception) -> bool:
    """Detect if an exception indicates a 401 Unauthorized error.

    Analyzes various exception types and patterns to determine if
    the error represents an authentication failure.

    Args:
        exception: The exception to analyze

    Returns:
        True if the exception indicates a 401/authentication error
    """
    logger.debug(f"Checking if error is 401: {type(exception).__name__}: {str(exception)[:200]}")

    # Check error string for authentication indicators
    error_str = str(exception).lower()
    if "401" in error_str or "unauthorized" in error_str:
        logger.debug(f"401 detected via string matching in error: {error_str[:200]}")
        return True

    # Check for HTTPStatusError (direct case)
    if (
        hasattr(exception, "response")
        and hasattr(exception.response, "status_code")
        and exception.response.status_code == 401
    ):
        logger.debug("401 detected from HTTPStatusError")
        return True

    # Check for ExceptionGroup containing HTTPStatusError
    if hasattr(exception, "exceptions"):
        for exc in exception.exceptions:
            if hasattr(exc, "response") and hasattr(exc.response, "status_code"):
                if exc.response.status_code == 401:
                    logger.debug("401 detected in ExceptionGroup")
                    return True
            # Check nested ExceptionGroups
            elif hasattr(exc, "exceptions"):
                for nested_exc in exc.exceptions:
                    if (
                        hasattr(nested_exc, "response")
                        and hasattr(nested_exc.response, "status_code")
                        and nested_exc.response.status_code == 401
                    ):
                        logger.debug("401 detected in nested ExceptionGroup")
                        return True

    return False


# HTTP Client Wrapper (streamablehttp)


@contextlib.asynccontextmanager
async def http_client_with_logging(
    url: str,
    server_name: str,
    headers: dict[str, Any] | None = None,
    oauth_enabled: bool = False,
    oauth_config: dict[str, Any] | None = None,
    authentication: dict[str, Any] | None = None,
    verify_ssl: bool = True,
) -> AsyncGenerator[
    tuple[
        MemoryObjectReceiveStream[JSONRPCMessage],
        MemoryObjectSendStream[JSONRPCMessage],
    ],
    None,
]:
    """Enhanced HTTP client with comprehensive authentication and error handling.

    This function provides HTTP client functionality using streamablehttp transport
    with support for multiple authentication methods, automatic OAuth flow initiation,
    and robust error handling with detailed logging.

    Args:
        url: HTTP endpoint URL
        server_name: Human-readable server name for logging purposes
        headers: Optional headers for the HTTP connection
        oauth_enabled: Whether this connection requires OAuth authentication
        oauth_config: OAuth configuration dictionary with provider-specific settings
        authentication: Authentication configuration dictionary
        verify_ssl: Whether to verify SSL/TLS certificates

    Yields:
        Tuple of (read_stream, write_stream) for MCP communication

    Raises:
        ConnectionError: If HTTP connection cannot be established
        AuthenticationError: If authentication fails

    Example:
        >>> async with http_client_with_logging(
        ...     url="https://api.example.com/mcp",
        ...     server_name="example-server"
        ... ) as (read_stream, write_stream):
        ...     # Connection uses streamablehttp transport
    """
    logger.debug("Starting HTTP client")

    try:
        # Initialize headers with defaults
        connection_headers = _prepare_connection_headers(headers)

        # Apply authentication methods
        await _apply_authentication(connection_headers, authentication, server_name)

        # Handle OAuth-enabled servers
        if oauth_enabled:
            await _handle_oauth_authentication(url, connection_headers, server_name, oauth_config)

        # Attempt HTTP connection with automatic OAuth handling
        try:
            async with streamablehttp_client(url=url, headers=connection_headers) as connection_result:
                read_stream, write_stream = connection_result[:2]  # Extract first two elements safely
                logger.debug("HTTP client established")
                yield (read_stream, write_stream)  # type: ignore[misc]
                return

        except Exception as http_error:
            # Handle authentication errors with automatic OAuth flow
            if oauth_enabled and _is_authentication_error(http_error):
                logger.warning(
                    f"HTTP authentication failed for OAuth-enabled server '{server_name}' - "
                    "initiating automatic OAuth flow"
                )

                # Attempt automatic OAuth flow and retry
                if await _handle_oauth_flow_and_retry(url, server_name, connection_headers, oauth_config):
                    # Retry connection with updated OAuth tokens
                    async with streamablehttp_client(url=url, headers=connection_headers) as connection_result:
                        read_stream, write_stream = connection_result[:2]  # Extract first two elements safely
                        logger.debug("HTTP client established after OAuth")
                        yield (read_stream, write_stream)  # type: ignore[misc]
                        return

                # OAuth flow failed or timed out
                _log_oauth_failure_guidance(server_name)

            # Re-raise the original error
            raise

    except Exception as e:
        # Handle shutdown-related errors gracefully
        error_msg = str(e).lower()
        if any(phrase in error_msg for phrase in ["cancel scope", "shutdown", "cancelled", "closed"]):
            logger.debug("HTTP client shutdown: %s", type(e).__name__)
        else:
            logger.exception(f"HTTP client failed for server '{server_name}': {e}")
        raise
    finally:
        logger.debug("HTTP client cleanup completed")
