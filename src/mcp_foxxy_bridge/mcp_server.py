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
import logging
import os
import signal
import socket
import urllib.parse
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

import uvicorn
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.server import Server as MCPServerSDK  # Renamed to avoid conflict
from mcp.server.sse import SseServerTransport
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import BaseRoute, Mount, Route
from starlette.types import Receive, Scope, Send

from .bridge_server import (
    _server_manager_registry,
    create_bridge_server,
    create_single_server_bridge,
    create_tag_filtered_bridge,
    shutdown_bridge_server,
)
from .config_loader import (
    BridgeConfiguration,
    BridgeServerConfig,
    load_bridge_config_from_file,
    normalize_server_name,
)
from .config_watcher import ConfigWatcher
from .proxy_server import create_proxy_server

logger = logging.getLogger(__name__)

# Global variables for config reloading
_current_bridge_config: BridgeConfiguration | None = None
_current_config_path: str | None = None
_server_manager_reference: object | None = None


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


def _find_available_port(host: str, requested_port: int) -> int:
    """Find an available port starting from the requested port."""
    actual_port = requested_port
    max_attempts = 100  # Try up to 100 ports

    for _attempt in range(max_attempts):
        try:
            with socket.socket() as s:
                s.bind((host, actual_port))
                # Port is available, break out of loop
                if actual_port != requested_port:
                    logger.info(
                        "Port %d was in use, using port %d instead",
                        requested_port,
                        actual_port,
                    )
                return actual_port
        except OSError:
            # Port is in use, try the next one
            actual_port += 1

    # If we exhausted all attempts, fall back to system-assigned port
    with socket.socket() as s:
        s.bind((host, 0))
        actual_port = s.getsockname()[1]
    logger.warning(
        "Could not find available port in range %d-%d, using system-assigned port %d",
        requested_port,
        requested_port + max_attempts - 1,
        actual_port,
    )
    return actual_port


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
) -> list[BaseRoute]:
    """Create routes for individual MCP server access.

    Creates routes of the form /sse/mcp/{server-name} for each configured server,
    allowing clients to connect to individual servers without aggregation.
    Routes are created lazily when accessed to improve startup performance.

    Args:
        bridge_config: Bridge configuration containing server definitions

    Returns:
        List of routes for individual server access
    """
    individual_routes: list[BaseRoute] = []

    for server_name, server_config in bridge_config.servers.items():
        if not server_config.enabled:
            logger.debug("Skipping disabled server '%s' for individual routes", server_name)
            continue

        # Normalize server name for URL
        normalized_name = normalize_server_name(server_name)
        logger.debug("Creating lazy route for '%s' -> /sse/mcp/%s", server_name, normalized_name)

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
                        logger.debug("Initializing server bridge for '%s'", self._server_name)
                        self._server_bridge_cache = await create_single_server_bridge(
                            self._server_name, self._server_config
                        )
                        self._sse_transport_cache = SseServerTransport(
                            f"/sse/mcp/{self._normalized_name}/messages/"
                        )
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

            async def handle_individual_messages(
                scope: Scope, receive: Receive, send: Send
            ) -> None:
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

        logger.debug(
            "Lazy routes created: /sse/mcp/%s and /sse/mcp/%s/messages/",
            normalized_name,
            normalized_name,
        )

    return individual_routes


def create_tag_based_routes(
    bridge_config: BridgeConfiguration,
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

    Returns:
        List of routes for tag-based server access
    """

    # Create a handler class similar to the individual server routes approach
    class TagRouteHandler:
        def __init__(self) -> None:
            self._tag_bridge_cache: dict[str, tuple[Any, Any]] = {}
            self._bridge_config = bridge_config

        async def get_or_create_tag_bridge(self, tag_path: str) -> tuple[Any, Any]:
            cache_key = tag_path
            if cache_key not in self._tag_bridge_cache:
                logger.debug("Initializing tag-filtered bridge for: %s", tag_path)

                # Parse the tag query
                tags, tag_mode = parse_tag_query(tag_path)

                # Create tag-filtered bridge
                tag_bridge = await create_tag_filtered_bridge(
                    self._bridge_config.servers, tags, tag_mode
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
                "Error handling tag SSE for path: %s", request.path_params.get("tag_path", "")
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
                logger.warning("No tag path found in URL: %s", full_path)
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
        Route("/sse/tag/{tag_path:path}", endpoint=handle_tag_sse),
        Mount("/sse/tag/{tag_path:path}/messages/", app=handle_tag_messages),
    ]

    logger.info("Created %d tag-based routes", len(tag_routes))
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
                for manager in _server_manager_registry.values():
                    server = manager.get_server_by_name(server_name)
                    if server:
                        server_status = server.health.status.value
                        break

                available_servers.append(
                    {
                        "name": normalized_name,
                        "endpoint": f"{base_url}/sse/mcp/{normalized_name}",
                        "tags": server_config.tags or [],
                        "status": server_status,
                        "transport_type": getattr(server_config, "transport_type", "stdio"),
                    }
                )

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
                "total_servers": len(
                    [s for s in _current_bridge_config.servers.values() if s.enabled]
                ),
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

        # Find an available port
        actual_port = _find_available_port(mcp_settings.bind_host, mcp_settings.port)

        config = uvicorn.Config(
            starlette_app,
            host=mcp_settings.bind_host,
            port=actual_port,
            log_level=mcp_settings.log_level.lower(),
            access_log=False,  # Disable uvicorn's default access logging
        )
        http_server = uvicorn.Server(config)

        # Print out the SSE URLs for all configured servers
        base_url = f"http://{mcp_settings.bind_host}:{actual_port}"
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
            for url in sse_urls:
                logger.info("  - %s", url)

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
    global _current_bridge_config, _current_config_path, _server_manager_reference  # noqa: PLW0602, PLW0603

    if not _current_config_path:
        logger.error("No config path available for reload")
        return False

    try:
        logger.info("Reloading configuration from: %s", _current_config_path)

        # Load and validate the new configuration
        base_env = dict(os.environ) if os.getenv("PASS_ENVIRONMENT") else {}

        # This will raise an exception if configuration is invalid
        new_config = load_bridge_config_from_file(_current_config_path, base_env)

        # Validate configuration before applying
        if (
            not _server_manager_reference
            or _server_manager_reference not in _server_manager_registry
        ):
            logger.error("No active server manager found for config reload")
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
) -> None:
    """Run the bridge server that aggregates multiple MCP servers.

    Args:
        mcp_settings: Server settings for the bridge.
        bridge_config: Configuration for the bridge and all MCP servers.
        config_file_path: Path to the configuration file for dynamic reloading.
    """
    logger.info("Starting MCP Foxxy Bridge server...")

    # Set global variables for config reloading
    global _current_bridge_config, _current_config_path, _server_manager_reference  # noqa: PLW0603
    _current_bridge_config = bridge_config
    _current_config_path = config_file_path

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

        # Create and configure the bridge server
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
            logger.info("Starting configuration file watcher...")
            config_watcher = ConfigWatcher(
                config_path=config_file_path,
                reload_callback=_handle_config_reload,
                debounce_ms=bridge_config.bridge.config_reload.debounce_ms,
                enabled=True,
            )
            await stack.enter_async_context(config_watcher)
            logger.info("Configuration file watcher started successfully")

        # Register cleanup on exit
        stack.callback(lambda: asyncio.create_task(shutdown_bridge_server(bridge_server)))

        # Create routes for the bridge server
        instance_routes, http_manager = create_single_instance_routes(
            bridge_server,
            stateless_instance=mcp_settings.stateless,
        )
        await stack.enter_async_context(http_manager.run())
        all_routes.extend(instance_routes)

        # Create individual server routes
        # Note: Individual server routes are created at startup. For dynamic updates
        # when config changes, a server restart is currently required. Future enhancement
        # could implement dynamic route management with more complex routing logic.
        logger.info("Creating individual server routes...")
        try:
            individual_routes = create_individual_server_routes(bridge_config)
            all_routes.extend(individual_routes)
            logger.info("Created %d individual server routes", len(individual_routes))
        except Exception:
            logger.exception("Failed to create individual server routes")

        # Create tag-based routes
        logger.info("Creating tag-based routes...")
        try:
            tag_routes = create_tag_based_routes(bridge_config)
            all_routes.extend(tag_routes)
            logger.info("Created %d tag-based routes", len(tag_routes))
        except Exception:
            logger.exception("Failed to create tag-based routes")

        # Add discovery endpoints
        server_discovery_route = Route("/sse/servers", endpoint=handle_server_discovery)
        tag_discovery_route = Route("/sse/tags", endpoint=handle_tag_discovery)
        all_routes.extend([server_discovery_route, tag_discovery_route])

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

        # Find an available port
        actual_port = _find_available_port(mcp_settings.bind_host, mcp_settings.port)

        # Create a custom log config to force uvicorn to use our Rich handler
        log_config = {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(message)s",
                    "use_colors": False,
                },
                "access": {
                    "format": "%(message)s",
                    "use_colors": False,
                },
            },
            "handlers": {
                "default": {
                    "class": "mcp_foxxy_bridge.logging_config.MCPRichHandler",
                    "formatter": "default",
                },
                "access": {
                    "class": "mcp_foxxy_bridge.logging_config.MCPRichHandler",
                    "formatter": "access",
                },
            },
            "loggers": {
                "uvicorn": {
                    "handlers": ["default"],
                    "level": "INFO",
                    "propagate": False,
                },
                "uvicorn.error": {
                    "handlers": ["default"],
                    "level": "INFO",
                    "propagate": False,
                },
                "uvicorn.access": {
                    "handlers": ["access"],
                    "level": "INFO",
                    "propagate": False,
                },
            },
        }

        # Configure uvicorn server with the available port
        config = uvicorn.Config(
            handle_shutdown_exceptions,  # Use our exception handler
            host=mcp_settings.bind_host,
            port=actual_port,
            log_level=mcp_settings.log_level.lower(),
            access_log=True,  # Enable access logging
            use_colors=False,  # Disable uvicorn's built-in colors since we use Rich
            log_config=log_config,  # Use our custom log config
        )
        http_server = uvicorn.Server(config)

        # Display connection information
        base_url = f"http://{mcp_settings.bind_host}:{actual_port}"
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

            # Give AsyncExitStack time to clean up
            with contextlib.suppress(asyncio.CancelledError, RuntimeError, ProcessLookupError):
                await asyncio.sleep(0.2)

            logger.info("Bridge server shutdown complete")
