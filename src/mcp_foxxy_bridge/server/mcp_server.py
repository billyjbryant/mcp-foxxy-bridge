#
# MCP Foxxy Bridge - MCP Server
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
"""Create a local SSE server that proxies requests to a stdio MCP server."""

import asyncio
import contextlib
import hashlib
import os
import secrets
import signal
import socket
import time
import urllib.parse
import webbrowser
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Literal

import uvicorn
from mcp import server
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.server import Server as MCPServerSDK  # Renamed to avoid conflict
from mcp.server.sse import SseServerTransport
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import BaseRoute, Mount, Route
from starlette.types import Receive, Scope, Send

from mcp_foxxy_bridge.config.config_loader import (
    BridgeConfiguration,
    BridgeServerConfig,
    load_bridge_config_from_file,
    normalize_server_name,
)
from mcp_foxxy_bridge.oauth import OAUTH_USER_AGENT, OAuthFlow, OAuthProviderOptions, get_oauth_client_config
from mcp_foxxy_bridge.oauth.http_security import create_localhost_client
from mcp_foxxy_bridge.oauth.oauth_flow import OAuthFlow as OAuthFlowImpl
from mcp_foxxy_bridge.oauth.types import OAuthClientInformation
from mcp_foxxy_bridge.oauth.types import OAuthProviderOptions as OAuthProviderOptionsImpl
from mcp_foxxy_bridge.utils.bridge_config import get_oauth_port
from mcp_foxxy_bridge.utils.config_watcher import ConfigWatcher
from mcp_foxxy_bridge.utils.logging import get_logger

from .bridge_server import (
    _server_manager_registry,
    create_bridge_server,
    create_server_filtered_bridge_view,
    create_single_server_bridge,
    create_tag_filtered_bridge_view,
    shutdown_bridge_server,
)
from .bridge_server_config import set_bridge_server_config
from .proxy_server import create_proxy_server

logger = get_logger(__name__)


def validate_oauth_server_config(server_config: BridgeServerConfig, server_name: str) -> str:
    """Validate server configuration for OAuth and return the URL.

    Args:
        server_config: Server configuration to validate
        server_name: Name of the server for error messages

    Returns:
        The validated server URL

    Raises:
        ValueError: If server URL is missing or invalid
    """
    if not server_config.url:
        raise ValueError(f"Server URL is required for OAuth on server '{server_name}'")
    return server_config.url


# Global variables for config reloading
_current_bridge_config: BridgeConfiguration | None = None
_current_config_path: str | None = None
_server_manager_reference: object | None = None

# Global OAuth token storage
_oauth_tokens: dict[str, dict[str, Any]] = {}
_oauth_states: dict[str, dict[str, Any]] = {}
_pkce_verifiers: dict[str, str] = {}  # state -> code_verifier mapping

# Module-level callback server tracking for proper cleanup
_callback_servers: dict[int, Any] = {}  # port -> callback server instance
_callback_tasks: dict[int, Any] = {}  # port -> callback server task


# Ephemeral encrypted storage for bridge internal secret
class _EphemeralSecretStore:
    """Secure ephemeral storage for the bridge internal secret."""

    def __init__(self) -> None:
        """Initialize the ephemeral secret store."""
        self._key_material: bytes | None = None
        self._encrypted_secret: bytes | None = None
        self._process_id = os.getpid()

    def _derive_key(self) -> bytes:
        """Derive an encryption key from process-specific entropy."""
        # Use process ID, system random bytes, and current time as key material
        entropy = f"{self._process_id}:{time.time()}:{secrets.token_bytes(32).hex()}".encode()
        return hashlib.pbkdf2_hmac("sha256", entropy, b"mcp_bridge_internal", 100000)

    def _simple_encrypt(self, data: bytes, key: bytes) -> bytes:
        """Simple XOR encryption (sufficient for ephemeral process-local secrets)."""
        # For a more secure implementation, we'd use AES, but for process-local
        # ephemeral secrets, XOR with a strong key is sufficient
        return bytes(a ^ b for a, b in zip(data, key * (len(data) // len(key) + 1), strict=False))

    def _simple_decrypt(self, data: bytes, key: bytes) -> bytes:
        """Simple XOR decryption."""
        return self._simple_encrypt(data, key)  # XOR is its own inverse

    def initialize_secret(self) -> str:
        """Initialize and store the encrypted secret."""
        if self._encrypted_secret is not None:
            return self.get_secret()

        # Generate a strong random secret
        secret = secrets.token_urlsafe(32)

        # Derive encryption key from process-specific entropy
        self._key_material = self._derive_key()

        # Encrypt the secret
        secret_bytes = secret.encode("utf-8")
        self._encrypted_secret = self._simple_encrypt(secret_bytes, self._key_material)

        # Clear the plaintext secret from local variables (though Python may cache it)
        del secret, secret_bytes

        logger.debug("Bridge internal secret initialized")
        return self.get_secret()

    def get_secret(self) -> str:
        """Retrieve and decrypt the secret."""
        if self._encrypted_secret is None or self._key_material is None:
            return self.initialize_secret()

        # Decrypt the secret
        decrypted_bytes = self._simple_decrypt(self._encrypted_secret, self._key_material)
        return decrypted_bytes.decode("utf-8")

    def clear_secret(self) -> None:
        """Securely clear the secret from memory."""
        if self._key_material:
            # Overwrite key material with random bytes
            self._key_material = secrets.token_bytes(len(self._key_material))
        if self._encrypted_secret:
            # Overwrite encrypted secret with random bytes
            self._encrypted_secret = secrets.token_bytes(len(self._encrypted_secret))
        self._key_material = None
        self._encrypted_secret = None
        logger.debug("Bridge internal secret cleared")


# Global ephemeral secret store
_secret_store = _EphemeralSecretStore()


def _get_bridge_secret() -> str:
    """Get the bridge internal secret from encrypted ephemeral storage."""
    return _secret_store.get_secret()


def _clear_bridge_secret() -> None:
    """Clear the bridge internal secret from memory."""
    _secret_store.clear_secret()


def _verify_internal_request(request: Request) -> bool:
    """Verify that a request is from an internal bridge component using the shared secret."""
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return False

    # Expected format: "Bearer <secret>"
    if not auth_header.startswith("Bearer "):
        return False

    provided_secret = auth_header[7:]  # Remove "Bearer " prefix
    expected_secret = _get_bridge_secret()

    # Use constant-time comparison to prevent timing attacks
    return secrets.compare_digest(provided_secret, expected_secret)


async def create_oauth_callback_server(callback_port: int, bridge_port: int) -> None:
    """Create a temporary OAuth callback server on the calculated port."""
    if callback_port in _callback_servers:
        logger.debug("Callback server already exists on port %d", callback_port)
        return

    async def oauth_callback_handler(request: Request) -> Response:
        """Handle OAuth callback and forward to main bridge server."""
        logger.info("OAuth callback received on port %d", callback_port)
        logger.debug("Callback URL: %s", str(request.url))
        try:
            # Extract callback parameters
            query_params = dict(request.query_params)

            # Extract state to find the server name
            state = query_params.get("state")
            if not state or state not in _oauth_states:
                return HTMLResponse(
                    """
                <!DOCTYPE html>
                <html>
                <head>
                    <title>OAuth Error</title>
                    <style>
                        body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
                        .error { color: #dc3545; font-size: 24px; margin-bottom: 20px; }
                        .info { color: #6c757d; margin-bottom: 10px; }
                    </style>
                </head>
                <body>
                    <div class="error">❌ OAuth State Error</div>
                    <div class="info">Invalid or missing state parameter</div>
                    <div class="info">Please try the authorization process again.</div>
                </body>
                </html>
                """,
                    status_code=400,
                )

            # Get server ID from stored state
            server_id = _oauth_states[state]["server_id"]

            # Forward the callback to the main bridge server's generic OAuth callback handler
            bridge_url = f"http://localhost:{bridge_port}/oauth/callback"

            logger.info("Forwarding OAuth callback to bridge server generic handler for server '%s'", server_id)
            logger.debug("Bridge URL: %s", bridge_url)

            # Use localhost client for internal OAuth callback forwarding
            async with create_localhost_client() as client:
                start_time = time.time()
                logger.debug("Making HTTP request to bridge server")
                try:
                    # Include bridge internal secret for authentication
                    headers = {"User-Agent": OAUTH_USER_AGENT, "Authorization": f"Bearer {_get_bridge_secret()}"}
                    response = await client.get(
                        bridge_url,
                        params=query_params,
                        headers=headers,
                        timeout=30.0,  # Explicit 30-second timeout
                    )
                except Exception:
                    elapsed = time.time() - start_time
                    logger.exception("HTTP request to bridge server failed after %.2f seconds", elapsed)
                    raise
                elapsed = time.time() - start_time
                logger.debug("Bridge response received after %.2f seconds", elapsed)
                logger.debug("Bridge response status: %d", response.status_code)
                if response.status_code != 200:
                    logger.error("Bridge response error: %s", response.text)

                if response.status_code == 200:
                    logger.info("OAuth callback processed successfully")
                    # Success - show a nice completion page
                    return HTMLResponse(
                        """
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <title>OAuth Success</title>
                        <style>
                            body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
                            .success { color: #28a745; font-size: 24px; margin-bottom: 20px; }
                            .info { color: #6c757d; margin-bottom: 10px; }
                        </style>
                    </head>
                    <body>
                        <div class="success">✅ OAuth Authorization Successful!</div>
                        <div class="info">You can now close this window.</div>
                        <div class="info">The MCP Foxxy Bridge is now authorized to access your account.</div>
                        <script>
                            setTimeout(() => window.close(), 3000);
                        </script>
                    </body>
                    </html>
                    """
                    )
                # Error - show error page with details
                return HTMLResponse(
                    f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <title>OAuth Error</title>
                        <style>
                            body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                            .error {{ color: #dc3545; font-size: 24px; margin-bottom: 20px; }}
                            .info {{ color: #6c757d; margin-bottom: 10px; }}
                        </style>
                    </head>
                    <body>
                        <div class="error">❌ OAuth Authorization Failed</div>
                        <div class="info">Status: {response.status_code}</div>
                        <div class="info">Please try the authorization process again.</div>
                    </body>
                    </html>
                    """,
                    status_code=response.status_code,
                )

        except Exception as e:
            logger.exception("Error in OAuth callback handler")
            return HTMLResponse(
                f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>OAuth Error</title>
                <style>
                    body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                    .error {{ color: #dc3545; font-size: 24px; margin-bottom: 20px; }}
                    .info {{ color: #6c757d; margin-bottom: 10px; }}
                </style>
            </head>
            <body>
                <div class="error">❌ OAuth Callback Error</div>
                <div class="info">Error: {e!s}</div>
                <div class="info">Please try the authorization process again.</div>
            </body>
            </html>
            """,
                status_code=500,
            )

    # Create callback app
    callback_app = Starlette(
        routes=[
            Route("/oauth/callback", oauth_callback_handler, methods=["GET"]),
        ]
    )

    # Start callback server
    config = uvicorn.Config(
        callback_app,
        host="localhost",
        port=callback_port,
        log_level="warning",  # Reduce noise
        access_log=False,
    )

    server = uvicorn.Server(config)

    # Store server reference
    _callback_servers[callback_port] = server

    # Start server in background
    task = asyncio.create_task(server.serve())
    # Store task reference to prevent garbage collection
    _callback_tasks[callback_port] = task
    logger.info("Started OAuth callback server on port %d", callback_port)


async def cleanup_callback_servers() -> None:
    """Clean up all callback servers."""
    for port, callback_server in _callback_servers.items():
        try:
            if hasattr(callback_server, "shutdown"):
                await callback_server.shutdown()
            logger.debug("Cleaned up callback server on port %d", port)
        except Exception:
            logger.exception("Error cleaning up callback server on port %d", port)

    # Cancel any running tasks
    for port, task in _callback_tasks.items():
        try:
            if not task.done():
                task.cancel()
            logger.debug("Cleaned up callback task on port %d", port)
        except Exception:
            logger.exception("Error cleaning up callback task on port %d", port)

    _callback_servers.clear()
    _callback_tasks.clear()

    # Clear internal secrets
    _clear_bridge_secret()


@dataclass
class MCPServerSettings:
    """Settings for the MCP server."""

    bind_host: str
    port: int
    stateless: bool = False
    allow_origins: list[str] | None = None
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"


# To store last activity for multiple servers if needed, though status endpoint is global for now.
_global_status: dict[str, Any] = {
    "api_last_activity": datetime.now(UTC).isoformat(),
    "server_instances": {},  # Could be used to store per-instance status later
}


def _update_global_activity() -> None:
    _global_status["api_last_activity"] = datetime.now(UTC).isoformat()


async def _handle_status(_: Request) -> Response:
    """Global health check and service usage monitoring endpoint."""
    return JSONResponse(_global_status)


def create_single_instance_routes(
    mcp_server_instance: MCPServerSDK[object],
    *,
    stateless_instance: bool,
) -> tuple[list[BaseRoute], StreamableHTTPSessionManager]:  # Return the manager itself
    """Create Starlette routes and the HTTP session manager for a single MCP server instance."""
    logger.debug(
        "Creating routes for a single MCP server instance (stateless: %s)",
        stateless_instance,
    )

    sse_transport = SseServerTransport("/messages/")
    http_session_manager = StreamableHTTPSessionManager(
        app=mcp_server_instance,
        event_store=None,
        json_response=True,
        stateless=stateless_instance,
    )

    async def handle_sse_instance(request: Request) -> Response:
        async with sse_transport.connect_sse(
            request.scope,
            request.receive,
            request._send,  # noqa: SLF001
        ) as (read_stream, write_stream):
            _update_global_activity()
            await mcp_server_instance.run(
                read_stream,
                write_stream,
                mcp_server_instance.create_initialization_options(),
            )
        return Response()

    async def handle_streamable_http_instance(scope: Scope, receive: Receive, send: Send) -> None:
        _update_global_activity()
        await http_session_manager.handle_request(scope, receive, send)

    routes = [
        Mount("/mcp", app=handle_streamable_http_instance),
        Route("/sse", endpoint=handle_sse_instance),
        Mount("/messages/", app=sse_transport.handle_post_message),
    ]
    return routes, http_session_manager


def create_individual_server_routes(
    bridge_config: BridgeConfiguration,
    main_bridge_server: Any = None,
) -> list[BaseRoute]:
    """Create routes for individual MCP server access.

    Creates routes of the form /sse/mcp/{server-name} for each configured server,
    allowing clients to connect to individual servers without aggregation.
    Routes are created lazily when accessed to improve startup performance.

    Args:
        bridge_config: Bridge configuration containing server definitions
        main_bridge_server: Optional main bridge server instance for OAuth integration

    Returns:
        List of routes for individual server access
    """
    individual_routes: list[BaseRoute] = []

    for server_name, server_config in bridge_config.servers.items():
        if not server_config.enabled:
            logger.debug("Skipping disabled server for individual routes")
            continue

        # Normalize server name for URL
        normalized_name = normalize_server_name(server_name)
        logger.debug("Creating lazy route for server endpoint")

        # Create a factory function with proper closure isolation
        def create_lazy_routes_factory(
            srv_name: str, srv_config: BridgeServerConfig, norm_name: str
        ) -> list[BaseRoute]:
            """Factory function to create lazy routes with proper SSE session management."""

            # Create a class to properly encapsulate the server state
            class IndividualServerHandler:
                def __init__(self) -> None:
                    self._server_bridge_cache: Any = None
                    self._sse_transport_cache: Any = None
                    self._server_name = srv_name
                    self._server_config = srv_config
                    self._normalized_name = norm_name

                async def get_or_create_bridge(self) -> tuple[Any, Any]:
                    if self._server_bridge_cache is None:
                        logger.debug(
                            "Creating filtered bridge view for server '%s'",
                            self._server_name,
                        )
                        # Use the new server-filtered bridge view approach
                        if main_bridge_server is not None:
                            self._server_bridge_cache = await create_server_filtered_bridge_view(
                                bridge_config.servers,
                                self._server_name,
                                main_bridge_server,
                            )
                        else:
                            # Fallback to individual bridge if main bridge not available
                            logger.warning(
                                "Main bridge server not available, creating individual bridge for '%s'",
                                self._server_name,
                            )
                            self._server_bridge_cache = await create_single_server_bridge(
                                self._server_name, self._server_config
                            )
                        self._sse_transport_cache = SseServerTransport(f"/sse/mcp/{self._normalized_name}/messages/")
                    return self._server_bridge_cache, self._sse_transport_cache

            # Create the handler instance
            handler = IndividualServerHandler()

            async def handle_individual_sse(request: Request) -> Response:
                try:
                    bridge, sse_transport = await handler.get_or_create_bridge()
                    async with sse_transport.connect_sse(
                        request.scope,
                        request.receive,
                        request._send,  # noqa: SLF001
                    ) as (read_stream, write_stream):
                        _update_global_activity()
                        await bridge.run(
                            read_stream,
                            write_stream,
                            bridge.create_initialization_options(),
                        )
                    return Response()
                except Exception:
                    logger.exception("Error handling individual SSE for '%s'", srv_name)
                    return Response(status_code=500)

            async def handle_individual_messages(scope: Scope, receive: Receive, send: Send) -> None:
                try:
                    _, sse_transport = await handler.get_or_create_bridge()
                    _update_global_activity()
                    await sse_transport.handle_post_message(scope, receive, send)
                except Exception:
                    logger.exception("Error handling individual messages for '%s'", srv_name)
                    await send(
                        {
                            "type": "http.response.start",
                            "status": 500,
                            "headers": [],
                        }
                    )
                    await send(
                        {
                            "type": "http.response.body",
                            "body": b"",
                        }
                    )

            return [
                Route(f"/sse/mcp/{norm_name}", endpoint=handle_individual_sse),
                Mount(f"/sse/mcp/{norm_name}/messages/", app=handle_individual_messages),
            ]

        # Create the lazy routes for this server with proper isolation
        server_routes = create_lazy_routes_factory(server_name, server_config, normalized_name)
        individual_routes.extend(server_routes)

        # Create status route with proper closure to avoid variable binding issues
        def create_status_route_factory(srv_name: str, norm_name: str) -> BaseRoute:
            async def handle_individual_status(_: Request) -> Response:
                try:
                    # Get server status from server manager
                    server_info = None
                    for manager in _server_manager_registry.values():
                        server = manager.get_server_by_name(srv_name)
                        if server:
                            capabilities_dict = (
                                server.health.capabilities.model_dump() if server.health.capabilities else None
                            )
                            server_info = {
                                "name": srv_name,
                                "normalized_name": norm_name,
                                "status": server.health.status.value,
                                "last_seen": server.health.last_seen,
                                "failure_count": server.health.failure_count,
                                "consecutive_failures": server.health.consecutive_failures,
                                "restart_count": server.health.restart_count,
                                "last_restart": server.health.last_restart,
                                "last_error": server.health.last_error,
                                "last_keep_alive": server.health.last_keep_alive,
                                "keep_alive_failures": server.health.keep_alive_failures,
                                "capabilities": capabilities_dict,
                                "config": asdict(server.config),
                                "tools_count": len(server.tools),
                                "resources_count": len(server.resources),
                                "prompts_count": len(server.prompts),
                            }
                            break

                    if not server_info:
                        return JSONResponse({"error": f"Server '{srv_name}' not found"}, status_code=404)

                    return JSONResponse(server_info)

                except Exception:
                    logger.exception("Error getting status for server '%s'", srv_name)
                    return JSONResponse({"error": "Internal server error"}, status_code=500)

            return Route(f"/sse/mcp/{norm_name}/status", endpoint=handle_individual_status)

        status_route = create_status_route_factory(server_name, normalized_name)
        individual_routes.append(status_route)

        logger.debug(
            "Lazy routes created: /sse/mcp/%s, /sse/mcp/%s/messages/, and /sse/mcp/%s/status",
            normalized_name,
            normalized_name,
            normalized_name,
        )

    return individual_routes


def create_tag_based_routes(
    bridge_config: BridgeConfiguration,
    main_bridge_server: server.Server[object],
) -> list[BaseRoute]:
    """Create routes for tag-based MCP server access.

    Creates routes of the form /sse/tag/{tag_query} for accessing servers filtered by tags.
    Tag queries support:
    - Single tags: /sse/tag/development
    - Intersection (ALL tags): /sse/tag/dev+local
    - Union (ANY tag): /sse/tag/web,api,remote

    Routes are created on-demand to improve startup performance.

    Args:
        bridge_config: Bridge configuration containing server definitions
        main_bridge_server: Main bridge server instance for tag-based filtering

    Returns:
        List of routes for tag-based server access
    """

    # Create a handler class that uses filtered views of the main bridge server
    class TagRouteHandler:
        def __init__(self) -> None:
            self._tag_bridge_cache: dict[str, tuple[Any, Any]] = {}
            self._bridge_config = bridge_config
            self._main_bridge_server = main_bridge_server

        async def get_or_create_tag_bridge(self, tag_path: str) -> tuple[Any, Any]:
            cache_key = tag_path
            if cache_key not in self._tag_bridge_cache:
                logger.debug("Creating tag-filtered view for: %s", tag_path)

                # Parse the tag query
                tags, tag_mode = parse_tag_query(tag_path)

                # Create tag-filtered bridge using shared server instance
                tag_bridge = await create_tag_filtered_bridge_view(
                    self._bridge_config.servers,
                    tags,
                    tag_mode,
                    self._main_bridge_server,
                )

                # Create SSE transport for this tag combination
                sse_transport = SseServerTransport(f"/sse/tag/{tag_path}/messages/")

                self._tag_bridge_cache[cache_key] = (tag_bridge, sse_transport)

            return self._tag_bridge_cache[cache_key]

    # Create the handler instance
    tag_handler = TagRouteHandler()

    async def handle_tag_sse(request: Request) -> Response:
        try:
            # Extract tag path from URL
            tag_path = request.path_params.get("tag_path", "")
            if not tag_path:
                return Response(content="Tag path required", status_code=400)

            bridge, sse_transport = await tag_handler.get_or_create_tag_bridge(tag_path)
            async with sse_transport.connect_sse(
                request.scope,
                request.receive,
                request._send,  # noqa: SLF001
            ) as (read_stream, write_stream):
                _update_global_activity()
                await bridge.run(
                    read_stream,
                    write_stream,
                    bridge.create_initialization_options(),
                )
            return Response()
        except Exception:
            logger.exception(
                "Error handling tag SSE for path: %s",
                request.path_params.get("tag_path", ""),
            )
            return Response(status_code=500)

    async def handle_tag_messages(scope: Scope, receive: Receive, send: Send) -> None:
        try:
            # Extract tag path from the full URL path
            # The full path will be something like "/sse/tag/development/messages/"
            full_path = scope.get("path", "")

            # Extract tag path from URL like "/sse/tag/development/messages/"
            if full_path.startswith("/sse/tag/") and "/messages/" in full_path:
                # Extract the tag part between "/sse/tag/" and "/messages/"
                tag_start = len("/sse/tag/")
                tag_end = full_path.find("/messages/")
                tag_path = full_path[tag_start:tag_end] if tag_end > tag_start else ""
            else:
                tag_path = ""

            if not tag_path:
                logger.warning("No tag path found in URL")
                await send(
                    {
                        "type": "http.response.start",
                        "status": 400,
                        "headers": [("content-type", "text/plain")],
                    }
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": b"Tag path required",
                    }
                )
                return

            logger.debug("Handling tag messages for tag path: %s", tag_path)
            _, sse_transport = await tag_handler.get_or_create_tag_bridge(tag_path)
            _update_global_activity()
            await sse_transport.handle_post_message(scope, receive, send)
        except Exception:
            logger.exception("Error handling tag messages for path: %s", scope.get("path", ""))
            await send(
                {
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [("content-type", "text/plain")],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": b"Internal server error",
                }
            )

    tag_routes = [
        Route("/sse/tag/{tag}/list_tools", endpoint=handle_list_tools_by_tag),
        Route("/sse/tag/{tag_path:path}", endpoint=handle_tag_sse),
        Mount("/sse/tag/{tag_path:path}/messages/", app=handle_tag_messages),
    ]

    logger.debug("Created %d tag-based routes", len(tag_routes))
    return tag_routes


def parse_tag_query(tag_path: str) -> tuple[list[str], str]:
    """Parse tag path into tags and operation mode.

    Args:
        tag_path: URL path segment containing tags (e.g., "dev+local" or "web,api")

    Returns:
        Tuple of (tags_list, mode) where mode is "intersection" or "union"

    Examples:
        "development" -> (["development"], "union")
        "dev+local" -> (["dev", "local"], "intersection")
        "web,api,remote" -> (["web", "api", "remote"], "union")
    """
    # URL decode the tag path first

    tag_path = urllib.parse.unquote(tag_path)

    if "+" in tag_path:
        # Intersection: servers must have ALL tags
        return tag_path.split("+"), "intersection"
    if "," in tag_path:
        # Union: servers must have ANY tag
        return tag_path.split(","), "union"
    # Single tag
    return [tag_path], "union"


async def handle_server_discovery(request: Request) -> Response:
    """Handle server discovery endpoint that lists available individual servers.

    Returns JSON with information about all available individual server endpoints.
    """
    try:
        # Get current bridge configuration from global state
        if not _current_bridge_config:
            return JSONResponse({"error": "No bridge configuration available"}, status_code=500)

        available_servers = []
        base_url = f"{request.url.scheme}://{request.url.netloc}"

        for server_name, server_config in _current_bridge_config.servers.items():
            if server_config.enabled:
                normalized_name = normalize_server_name(server_name)

                # Get server status if we can access the server manager
                server_status = "unknown"
                last_seen = None
                for manager in _server_manager_registry.values():
                    server = manager.get_server_by_name(server_name)
                    if server:
                        server_status = server.health.status.value
                        last_seen = getattr(server.health, "last_seen", None)
                        break

                server_info = {
                    "name": normalized_name,
                    "endpoint": f"{base_url}/sse/mcp/{normalized_name}",
                    "tags": server_config.tags or [],
                    "status": server_status,
                    "transport": getattr(server_config, "transport_type", "stdio"),
                }

                if last_seen is not None:
                    server_info["last_seen"] = last_seen

                available_servers.append(server_info)

        return JSONResponse(
            {
                "servers": available_servers,
                "count": len(available_servers),
                "aggregated_endpoint": f"{base_url}/sse",
            }
        )

    except Exception:
        logger.exception("Error in server discovery endpoint")
        return JSONResponse({"error": "Internal server error"}, status_code=500)


async def handle_tag_discovery(request: Request) -> Response:
    """Handle tag discovery endpoint that lists available tags and their servers.

    Returns JSON with information about all available tags and which servers belong to each.
    """
    try:
        # Get current bridge configuration from global state
        if not _current_bridge_config:
            return JSONResponse({"error": "No bridge configuration available"}, status_code=500)

        tag_mapping: dict[str, list[dict[str, str]]] = {}
        base_url = f"{request.url.scheme}://{request.url.netloc}"

        # Build mapping of tags to servers
        for server_name, server_config in _current_bridge_config.servers.items():
            if server_config.enabled and server_config.tags:
                # Get server status
                server_status = "unknown"
                for manager in _server_manager_registry.values():
                    server = manager.get_server_by_name(server_name)
                    if server:
                        server_status = server.health.status.value
                        break

                # Add this server to each of its tags
                for tag in server_config.tags:
                    if tag not in tag_mapping:
                        tag_mapping[tag] = []

                    tag_mapping[tag].append(
                        {
                            "server": server_name,
                            "status": server_status,
                        }
                    )

        # Build the response with tag information
        tags_info = {}
        for tag, servers in tag_mapping.items():
            tags_info[tag] = {
                "servers": servers,
                "count": len(servers),
                "endpoint": f"{base_url}/sse/tag/{tag}",
            }

        return JSONResponse(
            {
                "tags": tags_info,
                "tag_count": len(tags_info),
                "total_servers": len([s for s in _current_bridge_config.servers.values() if s.enabled]),
                "examples": {
                    "single_tag": f"{base_url}/sse/tag/development",
                    "intersection": f"{base_url}/sse/tag/development+local",
                    "union": f"{base_url}/sse/tag/web,api",
                },
            }
        )

    except Exception:
        logger.exception("Error in tag discovery endpoint")
        return JSONResponse({"error": "Internal server error"}, status_code=500)


async def handle_list_tools_all(request: Request) -> Response:
    """Handle /sse/list_tools endpoint that lists all available tools from all servers."""
    try:
        tools_info = []

        # Get all active servers and their tools
        for manager in _server_manager_registry.values():
            for server in manager.get_active_servers():
                # Get effective namespace for this server
                namespace = server.get_effective_namespace("tools", manager.bridge_config.bridge)

                for tool in server.tools:
                    tool_name = tool.name
                    if namespace:
                        tool_name = f"{namespace}__{tool.name}"

                    tools_info.append(
                        {
                            "name": tool_name,
                            "original_name": tool.name,
                            "server": server.name,
                            "namespace": namespace,
                            "description": tool.description,
                            "tags": server.config.tags or [],
                            "server_status": server.health.status.value,
                        }
                    )

        return JSONResponse(
            {
                "tools": tools_info,
                "total_tools": len(tools_info),
                "aggregated": True,
            }
        )

    except Exception:
        logger.exception("Error in list tools endpoint")
        return JSONResponse({"error": "Internal server error"}, status_code=500)


async def handle_list_tools_by_server(request: Request) -> Response:
    """Handle /sse/mcp/<server_name>/list_tools endpoint for server-specific tools."""
    try:
        server_name = request.path_params.get("server_name", "")
        if not server_name:
            return JSONResponse({"error": "Server name required"}, status_code=400)

        # Find the server across all managers
        target_server = None
        for manager in _server_manager_registry.values():
            server = manager.get_server_by_name(server_name)
            if server:
                target_server = server
                break

        if not target_server:
            return JSONResponse({"error": f"Server '{server_name}' not found"}, status_code=404)

        if target_server.health.status.value not in ("connected", "healthy"):
            return JSONResponse(
                {"error": f"Server '{server_name}' is not active (status: {target_server.health.status.value})"},
                status_code=503,
            )

        tools_info = [
            {
                "name": tool.name,
                "description": tool.description,
                "server": target_server.name,
                "tags": target_server.config.tags or [],
                "server_status": target_server.health.status.value,
            }
            for tool in target_server.tools
        ]

        return JSONResponse(
            {
                "server": server_name,
                "tools": tools_info,
                "total_tools": len(tools_info),
                "server_status": target_server.health.status.value,
                "tags": target_server.config.tags or [],
            }
        )

    except Exception:
        logger.exception("Error in server-specific list tools endpoint")
        return JSONResponse({"error": "Internal server error"}, status_code=500)


async def handle_list_tools_by_tag(request: Request) -> Response:
    """Handle /sse/tag/<tag>/list_tools endpoint for tag-filtered tools."""
    try:
        tag = request.path_params.get("tag", "")
        if not tag:
            return JSONResponse({"error": "Tag required"}, status_code=400)

        # Parse tag expression (supporting comma for union, + for intersection)
        tags_to_match, operation = parse_tag_query(tag)

        tools_info = []
        servers_matched = []

        # Get all active servers and filter by tags
        for manager in _server_manager_registry.values():
            for server in manager.get_active_servers():
                server_tags = set(server.config.tags or [])

                # Apply tag filtering logic
                if operation == "intersection":
                    matches = all(t in server_tags for t in tags_to_match)
                else:  # union
                    matches = any(t in server_tags for t in tags_to_match)

                if matches:
                    servers_matched.append(server.name)
                    namespace = server.get_effective_namespace("tools", manager.bridge_config.bridge)

                    for tool in server.tools:
                        tool_name = tool.name
                        if namespace:
                            tool_name = f"{namespace}__{tool.name}"

                        tools_info.append(
                            {
                                "name": tool_name,
                                "original_name": tool.name,
                                "server": server.name,
                                "namespace": namespace,
                                "description": tool.description,
                                "tags": server.config.tags or [],
                                "server_status": server.health.status.value,
                            }
                        )

        return JSONResponse(
            {
                "tag_filter": tag,
                "operation": operation,
                "matched_tags": tags_to_match,
                "servers_matched": servers_matched,
                "tools": tools_info,
                "total_tools": len(tools_info),
                "total_servers": len(servers_matched),
            }
        )

    except Exception:
        logger.exception("Error in tag-filtered list tools endpoint")
        return JSONResponse({"error": "Internal server error"}, status_code=500)


async def handle_server_reconnect(request: Request) -> Response:
    """Handle server reconnect endpoint for forcing server reconnection."""
    try:
        server_name = request.path_params.get("server_name", "")
        if not server_name:
            return JSONResponse({"error": "Server name required"}, status_code=400)

        # Find the server and its manager
        target_server = None
        target_manager = None
        for manager in _server_manager_registry.values():
            server = manager.get_server_by_name(server_name)
            if server:
                target_server = server
                target_manager = manager
                break

        if not target_server or not target_manager:
            return JSONResponse({"error": f"Server '{server_name}' not found"}, status_code=404)

        # Force reconnection by updating the server's connection
        try:
            await target_manager.reconnect_server(target_server)

            return JSONResponse(
                {
                    "message": f"Server '{server_name}' reconnected successfully",
                    "server": server_name,
                    "status": target_server.health.status.value,
                }
            )
        except asyncio.CancelledError:
            logger.warning("Server reconnection was cancelled for '%s'", server_name)
            return JSONResponse(
                {
                    "error": f"Reconnection of server '{server_name}' was cancelled",
                    "server": server_name,
                    "status": target_server.health.status.value,
                },
                status_code=408,  # Request Timeout
            )
        except Exception as reconnect_error:
            logger.exception("Failed to reconnect server '%s'", server_name)
            return JSONResponse(
                {
                    "error": f"Failed to reconnect server '{server_name}': {reconnect_error}",
                    "server": server_name,
                    "status": target_server.health.status.value,
                },
                status_code=500,
            )

    except Exception:
        logger.exception("Error in server reconnect endpoint")
        return JSONResponse({"error": "Internal server error"}, status_code=500)


async def handle_tools_rescan(request: Request) -> Response:
    """Handle tools rescan endpoint for refreshing tool capabilities."""
    try:
        # Trigger capability refresh for all active servers
        rescan_results = []

        for manager in _server_manager_registry.values():
            for server in manager.get_active_servers():
                try:
                    if server.session:
                        # Request fresh capabilities
                        result = await server.session.list_tools()
                        server.tools = result.tools

                        rescan_results.append(
                            {
                                "server": server.name,
                                "status": "success",
                                "tools_count": len(server.tools),
                                "server_status": server.health.status.value,
                            }
                        )
                        logger.info("Rescanned tools for server '%s': %d tools", server.name, len(server.tools))
                    else:
                        rescan_results.append(
                            {
                                "server": server.name,
                                "status": "skipped",
                                "reason": "No active session",
                                "server_status": server.health.status.value,
                            }
                        )
                except Exception as e:
                    rescan_results.append(
                        {
                            "server": server.name,
                            "status": "error",
                            "error": str(e),
                            "server_status": server.health.status.value,
                        }
                    )
                    logger.exception("Failed to rescan tools for server '%s'", server.name)

        success_count = sum(1 for r in rescan_results if r["status"] == "success")

        return JSONResponse(
            {
                "message": f"Tools rescan completed for {success_count}/{len(rescan_results)} servers",
                "results": rescan_results,
                "total_servers": len(rescan_results),
                "successful_rescans": success_count,
            }
        )

    except Exception:
        logger.exception("Error in tools rescan endpoint")
        return JSONResponse({"error": "Internal server error"}, status_code=500)


def create_oauth_routes(bridge_config: BridgeConfiguration, base_url: str) -> list[BaseRoute]:
    """Create OAuth callback routes for servers that have oauth: true.

    Args:
        bridge_config: Bridge configuration containing server definitions
        base_url: Base URL of the bridge server (e.g., http://localhost:8080)

    Returns:
        List of OAuth callback routes
    """
    oauth_routes: list[BaseRoute] = []

    for server_name, server_config in bridge_config.servers.items():
        if not server_config.enabled or not server_config.is_oauth_enabled():
            continue

        # Normalize server name for URL
        normalized_name = normalize_server_name(server_name)
        logger.debug("Creating OAuth routes for server")

        async def handle_oauth_start(request: Request) -> Response:
            """Handle OAuth flow initiation using new OAuth implementation."""
            try:
                # Extract server name from path
                path_parts = request.url.path.split("/")
                server_id = path_parts[2] if len(path_parts) > 2 else ""

                if not server_id:
                    return JSONResponse({"error": "Server ID required"}, status_code=400)

                # Get server config and actual server name
                server_config = None
                actual_server_name = None
                for name, config in bridge_config.servers.items():
                    if normalize_server_name(name) == server_id:
                        server_config = config
                        actual_server_name = name
                        break

                if not server_config or not server_config.is_oauth_enabled():
                    return JSONResponse(
                        {
                            "error": (
                                "OAuth not enabled for this server. "
                                "Please add oauth_config.enabled: true to your server configuration."
                            )
                        },
                        status_code=400,
                    )

                logger.info("Starting OAuth flow")

                # Use the new OAuthFlow implementation
                bridge_host = request.url.hostname or "127.0.0.1"

                # Create OAuth provider options
                try:
                    server_url = validate_oauth_server_config(server_config, actual_server_name or server_name)
                except ValueError as e:
                    return JSONResponse({"error": str(e)}, status_code=400)

                client_config = get_oauth_client_config()
                oauth_options = OAuthProviderOptions(
                    server_url=server_url,
                    oauth_issuer=None,
                    callback_port=get_oauth_port(),
                    host=bridge_host,
                    client_name=client_config["client_name"],
                    client_uri=client_config["client_uri"],
                    software_id=client_config["software_id"],
                    software_version=client_config["software_version"],
                    server_name=actual_server_name,
                )

                oauth_flow = OAuthFlow(oauth_options)

                # Check for existing valid tokens first
                existing_tokens = oauth_flow.provider.tokens()
                if existing_tokens and existing_tokens.access_token:
                    logger.info("Using existing OAuth tokens")
                    return JSONResponse(
                        {
                            "status": "success",
                            "message": "Already authenticated with valid tokens",
                        }
                    )

                # Discover OAuth endpoints to get authorization URL
                try:
                    endpoints = oauth_flow.discover_endpoints()
                    if not endpoints.get("authorization_endpoint"):
                        raise RuntimeError("Could not discover authorization endpoint")

                    # Get or register client
                    client_info = None
                    if endpoints.get("registration_endpoint"):
                        try:
                            client_info = oauth_flow.register_client(endpoints["registration_endpoint"])
                        except Exception as reg_error:
                            logger.exception(f"Client registration failed: {reg_error}")

                    # If no client info from registration or no registration endpoint, try to get existing
                    if not client_info:
                        client_info = oauth_flow.provider.client_information()

                    # Validate we have client info
                    if not client_info:
                        raise RuntimeError("No OAuth client information available")

                    # Build authorization URL
                    auth_url = oauth_flow.provider.build_authorization_url(
                        endpoints["authorization_endpoint"], client_info.client_id
                    )

                    # Track this OAuth state for callback routing with complete OAuth flow context
                    _oauth_states[oauth_flow.provider.state] = {
                        "server_name": actual_server_name,
                        "server_id": actual_server_name,  # Add server_id for callback server compatibility
                        "server_config": server_config,
                        "oauth_flow": oauth_flow,  # Store the actual OAuth flow instance
                        "timestamp": time.time(),
                    }

                    # Note: We don't start the full OAuth flow here since it would conflict
                    # with our callback server. The token exchange will happen in the
                    # generic OAuth callback endpoint when the user completes authorization

                    # Open browser immediately
                    try:
                        webbrowser.open(auth_url)
                        logger.info("Opened browser for OAuth authorization")
                    except OSError as e:
                        logger.warning("Could not open browser automatically: %s", e)
                    except Exception as e:
                        logger.warning("Unexpected error opening browser: %s", str(e))

                    return JSONResponse(
                        {
                            "status": "pending",
                            "message": "OAuth flow initiated. Please complete authorization in your browser.",
                            "auth_url": auth_url,
                            "status_url": f"{base_url}/oauth/{server_id}/status",
                        }
                    )

                except Exception as e:
                    logger.exception(f"OAuth flow initiation failed: {e}")
                    return JSONResponse(
                        {
                            "status": "error",
                            "message": f"Failed to initiate OAuth flow: {e!s}",
                        },
                        status_code=500,
                    )

            except Exception as e:
                logger.exception("Error starting OAuth flow")
                return JSONResponse({"error": f"OAuth flow error: {e!s}"}, status_code=500)

        async def handle_oauth_callback(request: Request) -> Response:
            """Handle OAuth callback from provider using new OAuth implementation."""
            callback_start_time = time.time()

            logger.info("OAuth callback received from provider")
            logger.debug("Callback path: %s", request.url.path)
            logger.debug("Callback received at: %.3f", callback_start_time)
            try:
                # Extract server name from path
                path_parts = request.url.path.split("/")
                server_id = path_parts[2] if len(path_parts) > 2 else ""

                if not server_id:
                    return JSONResponse({"error": "Server ID required"}, status_code=400)

                # Get OAuth parameters
                code = request.query_params.get("code")
                request.query_params.get("state")
                error = request.query_params.get("error")

                if error:
                    logger.error("OAuth error: %s", error)
                    return HTMLResponse(
                        f"""
                    <html>
                    <head><title>OAuth Error</title></head>
                    <body>
                        <h1>❌ OAuth Error</h1>
                        <p>Error: {error}</p>
                        <p>Server: {server_id}</p>
                        <p>Please try the authorization process again.</p>
                    </body>
                    </html>
                    """,
                        status_code=400,
                    )

                if not code:
                    return HTMLResponse(
                        """
                    <html>
                    <head><title>OAuth Error</title></head>
                    <body>
                        <h1>❌ OAuth Error</h1>
                        <p>No authorization code received</p>
                        <p>Please try the authorization process again.</p>
                    </body>
                    </html>
                    """,
                        status_code=400,
                    )

                # Get server config
                server_config = None
                for name, config in bridge_config.servers.items():
                    if normalize_server_name(name) == server_id:
                        server_config = config
                        break

                if not server_config:
                    return HTMLResponse(
                        """
                    <html>
                    <head><title>OAuth Error</title></head>
                    <body>
                        <h1>❌ OAuth Error</h1>
                        <p>Server configuration not found</p>
                        <p>Please check your server configuration.</p>
                    </body>
                    </html>
                    """,
                        status_code=400,
                    )

                logger.info("Processing OAuth callback for server '%s'", server_id)
                logger.debug("OAuth authorization code received (length: %d)", len(code) if code else 0)

                # Actually perform token exchange instead of just showing success

                bridge_host = request.url.hostname or "127.0.0.1"

                # Create OAuth flow instance for this server
                oauth_config: dict[str, Any] = (
                    server_config.oauth_config.to_dict() if server_config.oauth_config else {}
                )
                oauth_options = OAuthProviderOptionsImpl(
                    client_name=oauth_config.get("client_name", f"{server_id}-client"),
                    server_url=oauth_config.get("issuer", ""),
                    callback_port=get_oauth_port(),
                    host=bridge_host,
                )

                oauth_flow = OAuthFlowImpl(oauth_options)

                try:
                    # Perform token exchange with the authorization code
                    logger.info("Exchanging authorization code for tokens...")
                    exchange_start_time = time.time()
                    # Get token endpoint from discovery or config
                    token_endpoint = oauth_config.get("token_endpoint")
                    if not token_endpoint:
                        endpoints = oauth_flow.discover_endpoints()
                        token_endpoint = endpoints.get("token_endpoint")

                    if not token_endpoint:
                        raise ValueError("Token endpoint not found in OAuth configuration or discovery")

                    # Get client info (simplified for now)
                    client_info = OAuthClientInformation(
                        client_id=oauth_config.get("client_id", f"{server_id}-client"),
                        client_secret=oauth_config.get("client_secret"),
                    )

                    oauth_flow.exchange_code_for_tokens(token_endpoint, code, client_info)
                    exchange_duration = time.time() - exchange_start_time
                    total_duration = time.time() - callback_start_time
                    logger.success(  # type: ignore[attr-defined]
                        "Token exchange successful for server '%s' (exchange: %.2fs, total: %.2fs)",
                        server_id,
                        exchange_duration,
                        total_duration,
                    )

                    # Success page
                    return HTMLResponse(
                        f"""
                    <html>
                    <head>
                        <title>OAuth Success</title>
                        <style>
                            body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                            .success {{ color: #28a745; font-size: 24px; margin-bottom: 20px; }}
                            .info {{ color: #6c757d; margin-bottom: 10px; }}
                        </style>
                    </head>
                    <body>
                        <div class="success">✅ OAuth Authorization Complete!</div>
                        <div class="info">Tokens saved for <strong>{server_id}</strong></div>
                        <div class="info">You can now close this window and return to your application.</div>
                        <script>
                            setTimeout(() => {{ window.close(); }}, 2000);
                        </script>
                    </body>
                    </html>
                    """
                    )

                except Exception as e:
                    logger.exception("Token exchange failed for server '%s': %s", server_id, e)
                    return HTMLResponse(
                        f"""
                    <html>
                    <head><title>OAuth Error</title></head>
                    <body>
                        <h1>❌ OAuth Token Exchange Failed</h1>
                        <p>Error: {e}</p>
                        <p>Server: {server_id}</p>
                        <p>Please try the authorization process again.</p>
                    </body>
                    </html>
                    """,
                        status_code=500,
                    )

            except Exception as e:
                logger.exception("Error handling OAuth callback")
                return HTMLResponse(
                    f"""
                <html>
                <head><title>OAuth Error</title></head>
                <body>
                    <h1>❌ OAuth Callback Error</h1>
                    <p>Error: {e!s}</p>
                    <p>Please try the authorization process again.</p>
                </body>
                </html>
                """,
                    status_code=500,
                )

        async def handle_oauth_status(request: Request) -> Response:
            """Check OAuth status for a server using new OAuth implementation."""
            try:
                # Extract server name from path
                path_parts = request.url.path.split("/")
                server_id = path_parts[2] if len(path_parts) > 2 else ""

                if not server_id:
                    return JSONResponse({"error": "Server ID required"}, status_code=400)

                # Get server config and actual server name
                server_config = None
                actual_server_name = None
                for name, config in bridge_config.servers.items():
                    if normalize_server_name(name) == server_id:
                        server_config = config
                        actual_server_name = name
                        break

                if not server_config:
                    return JSONResponse({"error": "Server configuration not found"}, status_code=400)

                # Use the new OAuthFlow to check token status
                bridge_host = request.url.hostname or "127.0.0.1"

                # Create OAuth provider options
                try:
                    server_url = validate_oauth_server_config(server_config, actual_server_name or server_name)
                except ValueError as e:
                    return JSONResponse({"error": str(e)}, status_code=400)

                client_config = get_oauth_client_config()
                oauth_options = OAuthProviderOptions(
                    server_url=server_url,
                    oauth_issuer=None,
                    callback_port=get_oauth_port(),
                    host=bridge_host,
                    client_name=client_config["client_name"],
                    client_uri=client_config["client_uri"],
                    software_id=client_config["software_id"],
                    software_version=client_config["software_version"],
                    server_name=actual_server_name,
                )

                oauth_flow = OAuthFlow(oauth_options)

                # Check if we have valid tokens
                tokens = oauth_flow.provider.tokens()

                if tokens and tokens.access_token:
                    status = "authenticated"
                    expires_in = tokens.expires_in or 0

                    return JSONResponse(
                        {
                            "server_id": server_id,
                            "status": status,
                            "expires_in": expires_in,
                            "token_type": tokens.token_type,
                            "has_refresh_token": bool(tokens.refresh_token),
                        }
                    )
                return JSONResponse(
                    {
                        "server_id": server_id,
                        "status": "not_authenticated",
                        "auth_url": f"{base_url}/oauth/{server_id}/start",
                    }
                )

            except Exception as e:
                logger.exception("Error checking OAuth status")
                return JSONResponse({"error": f"OAuth status error: {e!s}"}, status_code=500)

        # Create routes for this server
        oauth_routes.extend(
            [
                Route(f"/oauth/{normalized_name}/start", endpoint=handle_oauth_start),
                Route(f"/oauth/{normalized_name}/callback", endpoint=handle_oauth_callback),
                Route(f"/oauth/{normalized_name}/status", endpoint=handle_oauth_status),
            ]
        )

        logger.debug(
            "OAuth routes created for '%s': /oauth/%s/start, /oauth/%s/callback, /oauth/%s/status",
            server_name,
            normalized_name,
            normalized_name,
            normalized_name,
        )

    # Add a generic OAuth callback route that handles callbacks for all servers
    # This is needed because the OAuth client provider uses /oauth/callback
    async def handle_generic_oauth_callback(request: Request) -> Response:
        """Handle generic OAuth callback that routes to the appropriate server."""
        try:
            # Get OAuth parameters
            code = request.query_params.get("code")
            state = request.query_params.get("state")
            error = request.query_params.get("error")

            if error:
                logger.error("OAuth error in generic callback: %s", error)
                return HTMLResponse(
                    f"""
                <html>
                <head><title>OAuth Error</title></head>
                <body>
                    <h1>❌ OAuth Error</h1>
                    <p>Error: {error}</p>
                    <p>Please try the authorization process again.</p>
                </body>
                </html>
                """,
                    status_code=400,
                )

            if not code:
                return HTMLResponse(
                    """
                <html>
                <head><title>OAuth Error</title></head>
                <body>
                    <h1>❌ OAuth Error</h1>
                    <p>No authorization code received</p>
                    <p>Please try the authorization process again.</p>
                </body>
                </html>
                """,
                    status_code=400,
                )

            logger.info("Received generic OAuth callback with authorization code")
            logger.debug("OAuth authorization code received (length: %d)", len(code) if code else 0)

            # Perform token exchange using the authorization code
            try:
                # Find which server this callback is for using the state parameter
                actual_server_name = None

                if state and state in _oauth_states:
                    # Found the server using tracked state
                    state_info = _oauth_states[state]
                    actual_server_name = state_info["server_name"]
                    oauth_flow = state_info["oauth_flow"]  # Use the stored OAuth flow instance
                    logger.info(f"Found server '{actual_server_name}' for OAuth callback using tracked state")

                    # Use the stored OAuth flow for token exchange (preserves PKCE state)
                    try:
                        # Discover endpoints using the original OAuth flow
                        endpoints = oauth_flow.discover_endpoints()
                        logger.info(f"Discovered endpoint keys for '{actual_server_name}': {list(endpoints.keys())}")

                        # Get client information from the original flow
                        client_info = oauth_flow.provider.client_information()
                        logger.info(f"Client info available for '{actual_server_name}': {client_info is not None}")

                        if client_info and endpoints.get("token_endpoint"):
                            # Exchange code for tokens using the SAME OAuth flow instance
                            oauth_flow.exchange_code_for_tokens(endpoints["token_endpoint"], code, client_info)
                            logger.info("Successfully exchanged authorization code for tokens")
                            logger.info(f"Tokens saved to: {oauth_flow.provider.server_url_hash}")
                        else:
                            missing_parts = []
                            if not client_info:
                                missing_parts.append("client info")
                            if not endpoints.get("token_endpoint"):
                                missing_parts.append("token endpoint")
                            logger.error(f"Could not exchange code for tokens: missing {', '.join(missing_parts)}")
                    finally:
                        # Clean up the state after use
                        del _oauth_states[state]

                    return HTMLResponse(
                        """
                    <html>
                    <head>
                        <title>OAuth Success</title>
                        <style>
                            body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
                            .success { color: #28a745; font-size: 24px; margin-bottom: 20px; }
                            .info { color: #6c757d; margin-bottom: 10px; }
                        </style>
                    </head>
                    <body>
                        <div class="success">✅ OAuth Authorization Successful!</div>
                        <div class="info">Authorization completed successfully</div>
                        <div class="info">You can now close this window and return to your application.</div>
                        <script>
                            setTimeout(() => { window.close(); }, 2000);
                        </script>
                    </body>
                    </html>
                    """
                    )

                # No tracked state found - this shouldn't happen in normal operation
                if state:
                    logger.error(f"OAuth state '{state}' not found in tracked states")
                else:
                    logger.error("No OAuth state parameter in callback")

                return HTMLResponse(
                    """
                    <html>
                    <head><title>OAuth Error</title></head>
                    <body>
                        <h1>❌ OAuth State Error</h1>
                        <p>OAuth state not found or missing. The authorization session may have expired.</p>
                        <p>Please start a new OAuth flow.</p>
                    </body>
                    </html>
                    """,
                    status_code=400,
                )

            except Exception as e:
                logger.exception(f"Failed to exchange authorization code for tokens: {e}")
                # Continue to show success page even if token exchange fails
            return HTMLResponse(
                """
            <html>
            <head>
                <title>OAuth Success</title>
                <style>
                    body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
                    .success { color: #28a745; font-size: 24px; margin-bottom: 20px; }
                    .info { color: #6c757d; margin-bottom: 10px; }
                </style>
            </head>
            <body>
                <div class="success">✅ OAuth Authorization Successful!</div>
                <div class="info">Authorization completed successfully</div>
                <div class="info">You can now close this window and return to your application.</div>
                <script>
                    // Try to close the window after a short delay
                    setTimeout(() => {
                        window.close();
                    }, 2000);
                </script>
            </body>
            </html>
            """
            )

        except Exception as e:
            logger.exception("Error handling generic OAuth callback")
            return HTMLResponse(
                f"""
            <html>
            <head><title>OAuth Error</title></head>
            <body>
                <h1>❌ OAuth Callback Error</h1>
                <p>Error: {e!s}</p>
                <p>Please try the authorization process again.</p>
            </body>
            </html>
            """,
                status_code=500,
            )

    # Add the generic callback route
    oauth_routes.append(Route("/oauth/callback", endpoint=handle_generic_oauth_callback))

    return oauth_routes


def get_oauth_env_vars(server_name: str) -> dict[str, str]:
    """Get OAuth environment variables for a server if it has been authorized.

    Args:
        server_name: Normalized server name

    Returns:
        Dictionary of environment variables to pass to mcp-remote
    """
    normalized_name = normalize_server_name(server_name)
    token_info = _oauth_tokens.get(normalized_name)

    if not token_info or token_info.get("status") != "authorized":
        return {}

    # For redirect-based flows, we just indicate authorization status
    # For traditional OAuth, we'd pass the authorization code/tokens
    env_vars = {
        "OAUTH_STATUS": "authorized",
        "OAUTH_TIMESTAMP": token_info.get("timestamp", ""),
    }

    # Add authorization code if we have one (traditional OAuth flow)
    if "authorization_code" in token_info:
        env_vars["OAUTH_AUTHORIZATION_CODE"] = token_info.get("authorization_code", "")

    # Add any callback data that might be useful for mcp-remote
    if "callback_data" in token_info:
        for key, value in token_info["callback_data"].items():
            env_vars[f"OAUTH_{key.upper()}"] = str(value)

    return env_vars


async def run_mcp_server(
    mcp_settings: MCPServerSettings,
    default_server_params: StdioServerParameters | None = None,
    named_server_params: dict[str, StdioServerParameters] | None = None,
) -> None:
    """Run stdio client(s) and expose an MCP server with multiple possible backends."""
    if named_server_params is None:
        named_server_params = {}

    all_routes: list[BaseRoute] = [
        Route("/status", endpoint=_handle_status),  # Global status endpoint
    ]
    # Use AsyncExitStack to manage lifecycles of multiple components
    async with contextlib.AsyncExitStack() as stack:
        # Manage lifespans of all StreamableHTTPSessionManagers
        @contextlib.asynccontextmanager
        async def combined_lifespan(_app: Starlette) -> AsyncIterator[None]:
            logger.info("Main application lifespan starting...")
            # All http_session_managers' .run() are already entered into the stack
            yield
            logger.info("Main application lifespan shutting down...")

        # Setup default server if configured
        if default_server_params:
            logger.info(
                "Setting up default server: %s %s",
                default_server_params.command,
                " ".join(default_server_params.args),
            )
            stdio_streams = await stack.enter_async_context(stdio_client(default_server_params))
            session = await stack.enter_async_context(ClientSession(*stdio_streams))
            proxy = await create_proxy_server(session)

            instance_routes, http_manager = create_single_instance_routes(
                proxy,
                stateless_instance=mcp_settings.stateless,
            )
            await stack.enter_async_context(http_manager.run())  # Manage lifespan by calling run()
            all_routes.extend(instance_routes)
            _global_status["server_instances"]["default"] = "configured"

        # Setup named servers
        for name, params in named_server_params.items():
            logger.info(
                "Setting up named server '%s': %s %s",
                name,
                params.command,
                " ".join(params.args),
            )
            stdio_streams_named = await stack.enter_async_context(stdio_client(params))
            session_named = await stack.enter_async_context(ClientSession(*stdio_streams_named))
            proxy_named = await create_proxy_server(session_named)

            instance_routes_named, http_manager_named = create_single_instance_routes(
                proxy_named,
                stateless_instance=mcp_settings.stateless,
            )
            await stack.enter_async_context(
                http_manager_named.run(),
            )  # Manage lifespan by calling run()

            # Mount these routes under /servers/<name>/
            server_mount = Mount(f"/servers/{name}", routes=instance_routes_named)
            all_routes.append(server_mount)
            _global_status["server_instances"][name] = "configured"

        if not default_server_params and not named_server_params:
            logger.error("No servers configured to run.")
            return

        middleware: list[Middleware] = []
        if mcp_settings.allow_origins:
            middleware.append(
                Middleware(
                    CORSMiddleware,
                    allow_origins=mcp_settings.allow_origins,
                    allow_methods=["*"],
                    allow_headers=["*"],
                ),
            )

        starlette_app = Starlette(
            debug=(mcp_settings.log_level == "DEBUG"),
            routes=all_routes,
            middleware=middleware,
            lifespan=combined_lifespan,
        )

        starlette_app.router.redirect_slashes = False

        # Check if port is available - hard fail if configured port is unavailable

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind((mcp_settings.bind_host, mcp_settings.port))
            bridge_port = mcp_settings.port
        except OSError as e:
            error_msg = (
                f"Port {mcp_settings.port} is not available: {e}. "
                f"Cannot start server with conflicting port. "
                f"Please change the port in config or free up port {mcp_settings.port}."
            )
            logger.exception(error_msg)
            raise RuntimeError(error_msg) from e

        config = uvicorn.Config(
            starlette_app,
            host=mcp_settings.bind_host,
            port=bridge_port,
            log_level=mcp_settings.log_level.lower(),
            access_log=False,  # Disable uvicorn's default access logging
        )
        http_server = uvicorn.Server(config)

        # Print out the SSE URLs for all configured servers
        base_url = f"http://{mcp_settings.bind_host}:{bridge_port}"
        sse_urls = []

        # Add default server if configured
        if default_server_params:
            sse_urls.append(f"{base_url}/sse")

        # Add named servers
        sse_urls.extend([f"{base_url}/servers/{name}/sse" for name in named_server_params])

        # Display the SSE URLs prominently
        if sse_urls:
            # Using print directly for user visibility, with noqa to ignore linter warnings
            logger.info("Serving MCP Servers via SSE:")
            for _ in sse_urls:
                logger.info("  - [ENDPOINT]")

        logger.debug(
            "Serving incoming MCP requests on %s:%s",
            mcp_settings.bind_host,
            mcp_settings.port,
        )
        await http_server.serve()


async def _handle_config_reload() -> bool:
    """Handle configuration file reload.

    Returns:
        True if reload was successful, False otherwise.
    """
    global _current_bridge_config, _current_config_path, _server_manager_reference  # noqa: PLW0602

    if not _current_config_path:
        logger.error("No configuration available for reload")
        return False

    try:
        logger.info("Reloading configuration from: %s", _current_config_path)

        # Load and validate the new configuration
        base_env = dict(os.environ) if os.getenv("PASS_ENVIRONMENT") else {}

        # This will raise an exception if configuration is invalid
        new_config = load_bridge_config_from_file(_current_config_path, base_env)

        # Validate configuration before applying
        if not _server_manager_reference or _server_manager_reference not in _server_manager_registry:
            logger.error("No active server manager found for reload")
            return False

        server_manager = _server_manager_registry[_server_manager_reference]

        # Check if we're in validate-only mode
        if (
            _current_bridge_config
            and _current_bridge_config.bridge
            and _current_bridge_config.bridge.config_reload
            and _current_bridge_config.bridge.config_reload.validate_only
        ):
            logger.info("Configuration validation successful (validate_only mode)")
            return True

        # Apply configuration changes through server manager
        await server_manager.update_servers(new_config.servers)

        # Update bridge config (this mainly affects conflict resolution, namespacing, etc.)
        server_manager.bridge_config = new_config

        # Update the global config reference
        _current_bridge_config = new_config

    except Exception:
        logger.exception("Failed to reload configuration")
        return False
    else:
        logger.info("Configuration reloaded successfully")
        return True


async def run_bridge_server(
    mcp_settings: MCPServerSettings,
    bridge_config: BridgeConfiguration,
    config_file_path: str | None = None,
    oauth_config_dir: str | None = None,
) -> None:
    """Run the bridge server that aggregates multiple MCP servers.

    Args:
        mcp_settings: Server settings for the bridge.
        bridge_config: Configuration for the bridge and all MCP servers.
        config_file_path: Path to the configuration file for dynamic reloading.
        oauth_config_dir: Directory where OAuth tokens should be stored.
    """
    logger.info("Starting MCP Foxxy Bridge server...")

    # Set global variables for config reloading
    global _current_bridge_config, _current_config_path, _server_manager_reference
    _current_bridge_config = bridge_config
    _current_config_path = config_file_path

    # Set OAuth config directory globally if provided
    if oauth_config_dir:
        os.environ["MCP_OAUTH_CONFIG_DIR"] = oauth_config_dir

    # Global status for bridge server
    _global_status["server_instances"] = {}
    for name, server_config in bridge_config.servers.items():
        _global_status["server_instances"][name] = {
            "enabled": server_config.enabled,
            "command": server_config.command,
            "status": "configuring",
        }

    all_routes: list[BaseRoute] = [
        Route("/status", endpoint=_handle_status),
    ]

    # Check if bridge port is available BEFORE entering async contexts
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((mcp_settings.bind_host, mcp_settings.port))
        bridge_port = mcp_settings.port
    except OSError as e:
        error_msg = (
            f"Bridge port {mcp_settings.port} is not available: {e}. "
            f"Cannot start bridge with conflicting bridge port. "
            f"Please change the port in config or free up port {mcp_settings.port}."
        )
        logger.exception(error_msg)
        raise RuntimeError(error_msg) from e

    # Use AsyncExitStack to manage bridge server lifecycle
    async with contextlib.AsyncExitStack() as stack:

        @contextlib.asynccontextmanager
        async def bridge_lifespan(_app: Starlette) -> AsyncIterator[None]:
            logger.info("Bridge application lifespan starting...")
            try:
                yield
            finally:
                logger.info("Bridge application lifespan shutting down...")
                # Give some time for cleanup
                with contextlib.suppress(asyncio.CancelledError):
                    await asyncio.sleep(0.1)

        # Set global bridge server configuration BEFORE creating bridge server
        # This ensures OAuth flows use consistent configuration during server startup
        oauth_port = getattr(bridge_config.bridge, "oauth_port", bridge_port) if bridge_config.bridge else bridge_port
        set_bridge_server_config(mcp_settings.bind_host, bridge_port, oauth_port)

        # Create and configure the bridge server
        # Initialize internal authentication secret
        _get_bridge_secret()  # This will initialize the secret if not already done
        logger.info("Internal authentication initialized")

        bridge_server = await create_bridge_server(bridge_config)

        # Store server manager reference for config reloading
        _server_manager_reference = id(bridge_server)

        # Setup config file watcher if enabled and config path provided
        config_watcher = None
        if (
            config_file_path
            and bridge_config.bridge
            and bridge_config.bridge.config_reload
            and bridge_config.bridge.config_reload.enabled
        ):
            logger.debug("Starting configuration file watcher...")
            config_watcher = ConfigWatcher(
                config_path=config_file_path,
                reload_callback=_handle_config_reload,
                debounce_ms=bridge_config.bridge.config_reload.debounce_ms,
                enabled=True,
            )
            await stack.enter_async_context(config_watcher)
            logger.debug("Configuration file watcher started successfully")

        # Register cleanup on exit
        stack.callback(lambda: asyncio.create_task(shutdown_bridge_server(bridge_server)))

        # Create routes for the bridge server
        instance_routes, http_manager = create_single_instance_routes(
            bridge_server,
            stateless_instance=mcp_settings.stateless,
        )
        await stack.enter_async_context(http_manager.run())
        all_routes.extend(instance_routes)

        # Create individual server routes using the SAME bridge server instance
        # This ensures all servers are launched once and shared between routes
        logger.debug("Creating individual server routes with shared server instances...")
        try:
            individual_routes = create_individual_server_routes(bridge_config, bridge_server)
            all_routes.extend(individual_routes)
            logger.debug("Created %d individual server routes", len(individual_routes))
        except Exception:
            logger.exception("Failed to create individual server routes")

        # Create tag-based routes using the SAME bridge server instance
        logger.debug("Creating tag-based routes with shared server instances...")
        try:
            tag_routes = create_tag_based_routes(bridge_config, bridge_server)
            all_routes.extend(tag_routes)
            logger.debug("Created %d tag-based routes", len(tag_routes))
        except Exception:
            logger.exception("Failed to create tag-based routes")

        # Add discovery endpoints
        server_discovery_route = Route("/sse/servers", endpoint=handle_server_discovery)
        tag_discovery_route = Route("/sse/tags", endpoint=handle_tag_discovery)

        # Add debug route to list all routes
        async def handle_routes_debug(request: Request) -> Response:
            """Debug endpoint to list all registered routes."""
            route_list = []
            for route in all_routes:
                if hasattr(route, "path"):
                    route_list.append(route.path)
                elif hasattr(route, "path_regex"):
                    route_list.append(str(route.path_regex.pattern))
                elif hasattr(route, "routes"):  # Mount
                    route_list.extend(
                        [
                            f"{route.path.rstrip('/')}{subroute.path}"
                            for subroute in route.routes
                            if hasattr(subroute, "path") and hasattr(route, "path")
                        ]
                    )

            return JSONResponse({"routes": sorted(route_list)})

        debug_route = Route("/debug/routes", endpoint=handle_routes_debug)

        # Add new tool listing and management endpoints
        tools_all_route = Route("/sse/list_tools", endpoint=handle_list_tools_all)
        server_tools_route = Route("/sse/mcp/{server_name}/list_tools", endpoint=handle_list_tools_by_server)
        server_reconnect_route = Route(
            "/sse/mcp/{server_name}/reconnect", endpoint=handle_server_reconnect, methods=["POST"]
        )
        tools_rescan_route = Route("/sse/tools/rescan", endpoint=handle_tools_rescan, methods=["POST"])

        all_routes.extend(
            [
                server_discovery_route,
                tag_discovery_route,
                debug_route,
                tools_all_route,
                server_tools_route,
                server_reconnect_route,
                tools_rescan_route,
            ]
        )

        # Bridge server configuration already set earlier before server creation

        # Integrate OAuth routes directly into the main bridge server
        logger.debug("Creating OAuth routes...")
        try:
            bridge_base_url = f"http://{mcp_settings.bind_host}:{mcp_settings.port}"
            oauth_routes = create_oauth_routes(bridge_config, bridge_base_url)

            if oauth_routes:
                # Add OAuth routes to the main bridge server routes
                all_routes.extend(oauth_routes)

                logger.info("OAuth endpoints integrated with bridge server:")
                for route in oauth_routes:
                    if hasattr(route, "path"):
                        logger.info("  %s%s", bridge_base_url, route.path)
            else:
                logger.debug("No OAuth routes to serve")
        except Exception:
            logger.exception("Failed to create OAuth routes")

        # Update server status
        server_manager = getattr(bridge_server, "_server_manager", None)
        if server_manager:
            server_statuses = server_manager.get_server_status()
            for name, status in server_statuses.items():
                _global_status["server_instances"][name]["status"] = status["status"]

        # Setup middleware
        middleware: list[Middleware] = []
        if mcp_settings.allow_origins:
            middleware.append(
                Middleware(
                    CORSMiddleware,
                    allow_origins=mcp_settings.allow_origins,
                    allow_methods=["*"],
                    allow_headers=["*"],
                ),
            )

        # Create Starlette app
        starlette_app = Starlette(
            debug=(mcp_settings.log_level == "DEBUG"),
            routes=all_routes,
            middleware=middleware,
            lifespan=bridge_lifespan,
        )

        starlette_app.router.redirect_slashes = False

        # Custom exception handler to suppress shutdown-related errors
        async def handle_shutdown_exceptions(scope: Scope, receive: Receive, send: Send) -> None:
            try:
                await starlette_app(scope, receive, send)
            except asyncio.CancelledError:
                # Handle cancellation gracefully - common during reconnection
                logger.debug("ASGI operation cancelled - likely due to server reconnection")
                return
            except RuntimeError as e:
                if "Expected ASGI message" in str(e) or "response" in str(e).lower():
                    # These are normal during graceful shutdown
                    logger.debug("ASGI shutdown error suppressed: %s", e)
                    return
                raise
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                # Client disconnected during shutdown
                logger.debug("Client connection error during shutdown")
                return

        # Use the port determined earlier for OAuth routes
        # (bridge_port was already set above)

        # Configure uvicorn server with the available port
        config = uvicorn.Config(
            handle_shutdown_exceptions,  # Use our exception handler
            host=mcp_settings.bind_host,
            port=bridge_port,
            log_level="warning",  # Minimal uvicorn logging
            access_log=False,  # Disable access logging
            use_colors=False,  # Disable uvicorn colors to not interfere with Rich
        )
        http_server = uvicorn.Server(config)

        # Display connection information
        base_url = f"http://{mcp_settings.bind_host}:{bridge_port}"
        logger.info("MCP Foxxy Bridge server is ready!")
        logger.info("SSE endpoint: %s/sse", base_url)
        logger.info("Status endpoint: %s/status", base_url)
        logger.info("Bridging %d configured servers", len(bridge_config.servers))

        # Setup graceful shutdown
        shutdown_event = asyncio.Event()

        def signal_handler(signum: int, _: object) -> None:
            logger.info("Received signal %d, initiating graceful shutdown...", signum)
            shutdown_event.set()

        # Install signal handlers (but don't let them propagate to child processes)
        old_sigint_handler = signal.signal(signal.SIGINT, signal_handler)
        old_sigterm_handler = signal.signal(signal.SIGTERM, signal_handler)

        try:
            # Start server in a task so we can handle shutdown
            server_task = asyncio.create_task(http_server.serve())
            shutdown_task = asyncio.create_task(shutdown_event.wait())

            # Wait for either server completion or shutdown signal
            done, pending = await asyncio.wait(
                [server_task, shutdown_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # If shutdown was triggered, cancel the server
            if shutdown_task in done:
                logger.info("Shutdown requested, stopping server...")
                server_task.cancel()
                with contextlib.suppress(TimeoutError, asyncio.CancelledError, RuntimeError):
                    await asyncio.wait_for(server_task, timeout=2.0)

            # Cancel remaining tasks
            for task in pending:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        except Exception:
            logger.exception("Server error")
        finally:
            logger.info("Starting graceful shutdown cleanup...")

            # Restore original signal handlers
            with contextlib.suppress(Exception):
                signal.signal(signal.SIGINT, old_sigint_handler)
                signal.signal(signal.SIGTERM, old_sigterm_handler)

            # Force close any remaining HTTP connections
            with contextlib.suppress(Exception):
                await http_server.shutdown()

            # Clean up OAuth callback servers
            with contextlib.suppress(Exception):
                await cleanup_callback_servers()

            # OAuth is now integrated with bridge server, no separate cleanup needed

            # Give AsyncExitStack time to clean up
            with contextlib.suppress(asyncio.CancelledError, RuntimeError, ProcessLookupError):
                await asyncio.sleep(0.2)

            logger.info("Bridge server shutdown complete")
