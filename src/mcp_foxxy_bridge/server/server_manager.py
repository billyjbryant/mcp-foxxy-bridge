#
# MCP Foxxy Bridge - Server Manager
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
"""Server connection management for MCP Foxxy Bridge.

This module provides functionality to manage connections to multiple MCP servers
and aggregate their capabilities for the bridge.
"""

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from mcp import types
from mcp.client.session import ClientSession
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData
from pydantic import AnyUrl

from mcp_foxxy_bridge.clients.sse_client_wrapper import (
    get_oauth_tokens,
    http_client_with_logging,
    sse_client_with_logging,
)
from mcp_foxxy_bridge.clients.stdio_client_wrapper import stdio_client_with_logging
from mcp_foxxy_bridge.config.config_loader import (
    BridgeConfig,
    BridgeConfiguration,
    BridgeServerConfig,
    normalize_server_name,
)
from mcp_foxxy_bridge.security.config import BridgeSecurityConfig
from mcp_foxxy_bridge.security.policy import SecurityPolicy
from mcp_foxxy_bridge.utils.config_migration import get_config_dir as _get_config_dir
from mcp_foxxy_bridge.utils.logging import get_logger, log_to_file, server_context


def _create_resource_uri(uri_string: str) -> AnyUrl | str:
    """Create a resource URI, allowing custom schemes for MCP resources.

    Args:
        uri_string: The URI string to validate

    Returns:
        AnyUrl object if it's a standard scheme, or string if it's a custom scheme

    Raises:
        ValueError: If the URI format is invalid
    """
    try:
        # Try standard URL validation first
        return AnyUrl(uri_string)
    except (ValueError, TypeError):
        # If AnyUrl fails, check if it's a reasonable URI with custom scheme
        if "://" in uri_string and not uri_string.startswith("//"):
            # Allow custom schemes like lambda-powertools://, config://, slack://
            return uri_string
        raise ValueError(f"Invalid URI format: {uri_string}") from None


logger = get_logger(__name__, facility="SERVER")


def _get_server_working_directory(server_name: str, configured_cwd: str | None = None) -> str | None:
    """Get the working directory for a server.

    Args:
        server_name: Name of the server
        configured_cwd: Explicitly configured working directory (takes precedence)

    Returns:
        Working directory path or None to use current directory

    If no working directory is explicitly configured, creates a default directory
    in the config directory: ~/.config/foxxy-bridge/servers/<server_name>/
    """
    if configured_cwd:
        return configured_cwd

    # Create default working directory in config dir

    config_dir = _get_config_dir()
    server_work_dir = config_dir / "servers" / server_name

    # Ensure directory exists
    try:
        server_work_dir.mkdir(parents=True, exist_ok=True)
        return str(server_work_dir)
    except Exception as e:
        logger.warning("Failed to create working directory for server '%s': %s", server_name, e)
        return None  # Fall back to current directory


# Import OAuth function (avoid circular import by importing only when needed)
def _get_oauth_env_vars(server_name: str) -> dict[str, str]:
    """Get OAuth environment variables for a server."""
    # Import here to avoid circular import
    from .mcp_server import get_oauth_env_vars  # noqa: PLC0415

    return get_oauth_env_vars(server_name)


class ServerStatus(Enum):
    """Status of a managed MCP server."""

    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    FAILED = "failed"
    DISABLED = "disabled"


@dataclass
class ServerHealth:
    """Health tracking for a managed server."""

    status: ServerStatus = ServerStatus.CONNECTING
    last_seen: float = field(default_factory=time.time)
    failure_count: int = 0
    last_error: str | None = None
    capabilities: types.ServerCapabilities | None = None
    consecutive_failures: int = 0
    restart_count: int = 0
    last_restart: float | None = None
    last_keep_alive: float = field(default_factory=time.time)
    keep_alive_failures: int = 0


@dataclass
class ManagedServer:
    """Represents a managed MCP server connection."""

    name: str
    config: BridgeServerConfig
    session: ClientSession | None = None
    health: ServerHealth = field(default_factory=ServerHealth)
    tools: list[types.Tool] = field(default_factory=list)
    resources: list[types.Resource] = field(default_factory=list)
    prompts: list[types.Prompt] = field(default_factory=list)

    def get_effective_namespace(
        self,
        capability_type: str,
        bridge_config: BridgeConfig | None,
    ) -> str | None:
        """Get the effective namespace for a capability type."""
        # Check explicit namespace configuration
        if capability_type == "tools" and self.config.tool_namespace:
            return self.config.tool_namespace
        if capability_type == "resources" and self.config.resource_namespace:
            return self.config.resource_namespace
        if capability_type == "prompts" and self.config.prompt_namespace:
            return self.config.prompt_namespace

        # Check if default namespace is enabled
        if bridge_config and bridge_config.default_namespace:
            return self.name

        return None


class ServerManager:
    """Manages multiple MCP server connections and aggregates their capabilities."""

    def __init__(self, bridge_config: BridgeConfiguration) -> None:
        """Initialize the server manager with bridge configuration."""
        self.bridge_config = bridge_config
        self.servers: dict[str, ManagedServer] = {}
        self.health_check_task: asyncio.Task[None] | None = None
        self.keep_alive_task: asyncio.Task[None] | None = None
        self.oauth_token_refresh_task: asyncio.Task[None] | None = None
        self._shutdown_event = asyncio.Event()
        self._server_contexts: dict[str, contextlib.AsyncExitStack] = {}
        self._restart_locks: dict[str, asyncio.Lock] = {}
        self._oauth_token_refresh_times: dict[str, float] = {}  # Track last token refresh per server

        # Track filtered tools for visibility
        self._filtered_tools: list[dict[str, str]] = []

        # Security will be handled per-request using SecurityPolicy and individual controllers

        # Capability change notification system
        self.capability_change_notifier: Callable[[dict[str, Any]], Any] | None = None
        self._last_capabilities: dict[str, Any] = {
            "tools": [],
            "resources": [],
            "prompts": [],
        }

    def _get_effective_log_level(self, server_config: BridgeServerConfig) -> str:
        """Get the effective log level for a server (server-specific or global default)."""
        # Server-specific log level takes precedence over global setting
        if hasattr(server_config, "log_level") and server_config.log_level:
            return server_config.log_level
        # Fall back to global bridge log level
        if self.bridge_config.bridge and hasattr(self.bridge_config.bridge, "mcp_log_level"):
            return self.bridge_config.bridge.mcp_log_level
        # Final fallback to ERROR (quiet mode)
        return "ERROR"

    async def start(self) -> None:
        """Start the server manager and connect to all configured servers."""
        logger.info(
            "Starting server manager with %d configured servers",
            len(self.bridge_config.servers),
        )

        # Create managed servers
        for name, config in self.bridge_config.servers.items():
            if not config.enabled:
                logger.info("Server '%s' is disabled, skipping", name)
                continue

            # Normalize server name to replace dots and special characters
            normalized_name = normalize_server_name(name)
            managed_server = ManagedServer(name=normalized_name, config=config)
            self.servers[normalized_name] = managed_server
            self._restart_locks[normalized_name] = asyncio.Lock()

        # Start connections
        connection_tasks = []
        for server in self.servers.values():
            task = asyncio.create_task(self._connect_server(server))
            connection_tasks.append(task)

        # Wait for initial connections (with timeout)
        if connection_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*connection_tasks, return_exceptions=True),
                    timeout=30.0,
                )
            except TimeoutError:
                logger.warning("Some servers took longer than 30 seconds to connect")

        # Start health check and keep-alive tasks
        if (
            self.bridge_config.bridge
            and self.bridge_config.bridge.failover
            and self.bridge_config.bridge.failover.enabled
        ):
            self.health_check_task = asyncio.create_task(self._health_check_loop())

        # Start keep-alive task for all servers with keep-alive enabled
        if any(server.config.health_check and server.config.health_check.enabled for server in self.servers.values()):
            self.keep_alive_task = asyncio.create_task(self._keep_alive_loop())

        # Start OAuth token refresh task for OAuth servers (both SSE and HTTP)
        if any(self._is_oauth_endpoint(server) for server in self.servers.values()):
            self.oauth_token_refresh_task = asyncio.create_task(self._oauth_token_refresh_loop())

        logger.info(
            "Server manager started with %d active servers",
            len(self.get_active_servers()),
        )

        # Initialize baseline capabilities for change detection
        self._last_capabilities = self._get_current_capability_names()
        logger.debug(
            "Initialized capability change tracking with %d tools, %d resources, %d prompts",
            len(self._last_capabilities["tools"]),
            len(self._last_capabilities["resources"]),
            len(self._last_capabilities["prompts"]),
        )

    async def stop(self) -> None:
        """Stop the server manager and disconnect from all servers."""
        logger.info("Stopping server manager gracefully...")

        # Signal shutdown
        self._shutdown_event.set()

        # Cancel health check and keep-alive tasks
        if self.health_check_task:
            self.health_check_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.health_check_task

        if self.keep_alive_task:
            self.keep_alive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.keep_alive_task

        if self.oauth_token_refresh_task:
            self.oauth_token_refresh_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.oauth_token_refresh_task

        # Close all server context stacks to cleanup managed connections
        cleanup_tasks = []
        for server_name, context_stack in self._server_contexts.items():

            async def cleanup_context(name: str, stack: contextlib.AsyncExitStack) -> None:
                try:
                    await asyncio.wait_for(stack.aclose(), timeout=2.0)
                    logger.debug("Cleaned up context for server: %s", name)
                except (
                    TimeoutError,
                    asyncio.CancelledError,
                    RuntimeError,
                    ProcessLookupError,
                ) as e:
                    logger.debug(
                        "Context cleanup for server '%s' completed with expected exceptions: %s",
                        name,
                        type(e).__name__,
                    )
                except (OSError, ValueError, AttributeError) as e:
                    logger.warning(
                        "Unexpected exception during context cleanup for server '%s': %s: %s",
                        name,
                        type(e).__name__,
                        e,
                    )

            cleanup_tasks.append(asyncio.create_task(cleanup_context(server_name, context_stack)))

        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)

        self._server_contexts.clear()

        logger.info("Server manager stopped")

    async def _connect_server(self, server: ManagedServer) -> None:
        """Connect to a single MCP server."""
        with server_context(server.name):
            logger.debug(
                'MCP Server Starting: "%s" %s',
                server.config.command,
                " ".join(server.config.args or []),
            )
            server.health.status = ServerStatus.CONNECTING

        # Create a dedicated context stack for this server
        context_stack = contextlib.AsyncExitStack()
        self._server_contexts[server.name] = context_stack

        try:
            # Create server parameters with modified environment for cleaner shutdown
            server_env = (server.config.env or {}).copy()
            # Add environment variable to help child processes handle shutdown gracefully
            server_env["MCP_BRIDGE_CHILD"] = "1"

            # Get the effective log level for this server
            effective_log_level = self._get_effective_log_level(server.config)
            server_env["MCP_SERVER_LOG_LEVEL"] = effective_log_level

            # Configure logging environment for child processes
            server_env["PYTHONPATH"] = server_env.get("PYTHONPATH", "")
            server_env["PYTHONUNBUFFERED"] = "1"  # Enable unbuffered output for real-time logging
            server_env["MCP_LOG_LEVEL"] = effective_log_level
            server_env["UVICORN_LOG_LEVEL"] = effective_log_level.lower()
            server_env["FASTAPI_LOG_LEVEL"] = effective_log_level.lower()
            server_env["LOGURU_LEVEL"] = effective_log_level
            server_env["LOG_LEVEL"] = effective_log_level
            server_env["MCP_SERVER_NAME"] = server.name  # For logging context

            # Add OAuth environment variables if this server needs OAuth proxy (not passthrough)
            if server.config.needs_oauth_proxy():
                oauth_env = _get_oauth_env_vars(server.name)
                server_env.update(oauth_env)

            # Connect with timeout and manage lifetime with context stack
            async with asyncio.timeout(server.config.timeout):
                # Get the effective log level for this server
                self._get_effective_log_level(server.config)

                # Handle different transport types
                logger.debug(f"Server '{server.name}' transport_type: {server.config.transport_type}")
                if server.config.transport_type == "sse":
                    if not server.config.url:
                        msg = f"SSE transport requires 'url' field for server '{server.name}'"
                        raise ValueError(msg)

                    # Create headers from environment variables if needed
                    headers = {}
                    if server_env:
                        # Convert OAuth and other env vars to headers if needed
                        for key, value in server_env.items():
                            if key.startswith("OAUTH_") or key.upper() in [
                                "AUTHORIZATION",
                                "BEARER",
                            ]:
                                # These might be useful as headers for SSE auth
                                header_key = key.lower().replace("_", "-")
                                if key.upper() == "AUTHORIZATION" or key.startswith("OAUTH_"):
                                    headers[header_key] = value

                    # Add custom headers from configuration (issue #10 compliance)
                    if server.config.headers:
                        headers.update(server.config.headers)
                        logger.debug(
                            "Added custom headers for server '%s': %s",
                            server.name,
                            list(server.config.headers.keys()),
                        )

                    # Enter the enhanced sse_client into the server's context stack
                    read_stream, write_stream = await context_stack.enter_async_context(
                        sse_client_with_logging(
                            server.config.url,
                            server.name,
                            headers=headers or None,
                            oauth_enabled=server.config.is_oauth_enabled(),
                            oauth_config=server.config.oauth_config.to_dict() if server.config.oauth_config else None,
                            authentication=server.config.authentication,
                            verify_ssl=server.config.verify_ssl,
                        ),
                    )
                elif server.config.transport_type == "http":
                    if not server.config.url:
                        msg = f"HTTP transport requires 'url' field for server '{server.name}'"
                        raise ValueError(msg)

                    # Create headers from environment variables if needed
                    headers = {}
                    if server_env:
                        # Convert OAuth and other env vars to headers if needed
                        for key, value in server_env.items():
                            if key.startswith("OAUTH_") or key.upper() in [
                                "AUTHORIZATION",
                                "BEARER",
                            ]:
                                # These might be useful as headers for HTTP auth
                                header_key = key.lower().replace("_", "-")
                                if key.upper() == "AUTHORIZATION" or key.startswith("OAUTH_"):
                                    headers[header_key] = value

                    # Add custom headers from configuration (issue #10 compliance)
                    if server.config.headers:
                        headers.update(server.config.headers)
                        logger.debug(
                            "Added custom headers for server '%s': %s",
                            server.name,
                            list(server.config.headers.keys()),
                        )

                    # Enter the enhanced http_client into the server's context stack
                    read_stream, write_stream = await context_stack.enter_async_context(
                        http_client_with_logging(
                            server.config.url,
                            server.name,
                            headers=headers or None,
                            oauth_enabled=server.config.is_oauth_enabled(),
                            oauth_config=server.config.oauth_config.to_dict() if server.config.oauth_config else None,
                            authentication=server.config.authentication,
                            verify_ssl=server.config.verify_ssl,
                        ),
                    )
                else:
                    # Default to stdio transport
                    if not server.config.command:
                        msg = f"STDIO transport requires 'command' field for server '{server.name}'"
                        raise ValueError(msg)

                    # Enter the enhanced stdio_client into the server's context stack
                    read_stream, write_stream = await context_stack.enter_async_context(
                        stdio_client_with_logging(
                            command=server.config.command,
                            args=server.config.args or [],
                            server_name=server.name,
                            cwd=_get_server_working_directory(server.name, server.config.working_directory),
                            env=server_env,
                            timeout=30.0,
                        ),
                    )

                # Create session and manage its lifetime
                session = await context_stack.enter_async_context(
                    ClientSession(read_stream, write_stream),  # type: ignore[arg-type]
                )
                server.session = session

                # Initialize the session with timeout - this is critical for OAuth discovery
                init_timeout = 8.0  # Fixed 8-second timeout for all session initialization

                # Check if this is a dynamic OAuth discovery attempt (only when no tokens exist yet)
                is_oauth_discovery = (
                    server.config.is_oauth_enabled()
                    and server.config.oauth_config
                    and server.config.oauth_config.type == "dynamic"
                    and not self._has_existing_oauth_tokens(server)
                )

                if is_oauth_discovery:
                    init_timeout = 3.0  # Very short timeout for OAuth discovery attempts
                    logger.debug(
                        "OAuth discovery attempt for server '%s' with %.1f second timeout",
                        server.name,
                        init_timeout,
                    )
                else:
                    logger.debug(
                        "Initializing session for server '%s' with %.1f second timeout",
                        server.name,
                        init_timeout,
                    )

                init_start_time = time.time()

                try:
                    # Use asyncio.wait_for with immediate cancellation on timeout
                    result = await asyncio.wait_for(session.initialize(), timeout=init_timeout)

                    init_duration = time.time() - init_start_time
                    logger.debug("Session initialized for server '%s' in %.3f seconds", server.name, init_duration)

                except TimeoutError:
                    init_duration = time.time() - init_start_time

                    # For OAuth discovery attempts, treat timeout as authentication failure
                    if is_oauth_discovery:
                        logger.info(
                            "OAuth discovery timeout for server '%s' after %.3f seconds - "
                            "server likely needs authentication",
                            server.name,
                            init_duration,
                        )
                        # Create authentication error to trigger OAuth flow
                        auth_error = McpError(
                            ErrorData(
                                code=-32001,
                                message="Authentication required - OAuth discovery timeout",
                                data={"requires_oauth": True, "server_url": server.config.url},
                            )
                        )
                        raise auth_error from None

                    logger.warning(
                        "Session initialization timed out for server '%s' after %.3f seconds (timeout: %.1fs)",
                        server.name,
                        init_duration,
                        init_timeout,
                    )
                    raise TimeoutError(f"Session initialization timeout after {init_duration:.3f}s") from None

                # Update server state
                server.health.status = ServerStatus.CONNECTED
                server.health.last_seen = time.time()
                server.health.failure_count = 0
                server.health.consecutive_failures = 0
                server.health.keep_alive_failures = 0
                server.health.last_error = None
                server.health.capabilities = result.capabilities
                server.health.last_keep_alive = time.time()

                # Load capabilities
                await self._load_server_capabilities(server)

                logger.info("Successfully connected to server")

                # Log connection success to server's file
                log_to_file(
                    server.name,
                    f"Successfully connected to MCP server (transport: {server.config.transport_type})",
                    logging.INFO,
                )

        except McpError as e:
            # Handle MCP-specific errors (including our OAuth discovery timeout)
            if e.error.code == -32001 and "OAuth discovery timeout" in e.error.message:
                logger.info("OAuth discovery timeout for server '%s' - triggering OAuth flow", server.name)
                # This is an authentication error - let the OAuth system handle it
                server.health.status = ServerStatus.FAILED
                server.health.failure_count += 1
                server.health.consecutive_failures += 1
                server.health.last_error = "OAuth authentication required"
                server.session = None
            else:
                logger.exception("MCP error connecting to server '%s'", server.name)
                server.health.status = ServerStatus.FAILED
                server.health.failure_count += 1
                server.health.consecutive_failures += 1
                server.health.last_error = str(e)
                server.session = None

            # Log connection failure to server's file
            log_to_file(
                server.name,
                f"Failed to connect to MCP server: {e}",
                logging.WARNING if "OAuth" in str(e) else logging.ERROR,
            )
        except Exception as e:
            logger.exception("Failed to connect to server '%s'", server.name)
            server.health.status = ServerStatus.FAILED
            server.health.failure_count += 1
            server.health.consecutive_failures += 1
            server.health.last_error = str(e)
            server.session = None

            # Log connection failure to server's file
            log_to_file(
                server.name,
                f"Failed to connect to MCP server: {e}",
                logging.ERROR,
            )

            # Clean up the context stack on failure
            try:
                await context_stack.aclose()
            except (RuntimeError, OSError) as e:
                logger.debug("Context cleanup error: %s", type(e).__name__)
            except Exception as e:
                logger.warning("Unexpected context cleanup error: %s", type(e).__name__)

            # Remove from tracking
            self._server_contexts.pop(server.name, None)

    async def _disconnect_server(self, server: ManagedServer) -> None:
        """Disconnect from a single MCP server."""
        logger.info("Disconnecting from server")

        # Clean up the server's context stack
        context_stack = self._server_contexts.pop(server.name, None)
        if context_stack:
            try:
                await context_stack.aclose()
                logger.debug("Cleaned up context stack")
            except (RuntimeError, OSError) as e:
                logger.debug("Context cleanup error: %s", type(e).__name__)
            except Exception as e:
                logger.warning("Unexpected context cleanup error: %s", type(e).__name__)

        server.session = None
        server.health.status = ServerStatus.DISCONNECTED
        server.health.consecutive_failures = 0
        server.health.keep_alive_failures = 0
        server.tools.clear()
        server.resources.clear()
        server.prompts.clear()

    async def _load_server_capabilities(self, server: ManagedServer) -> None:
        """Load capabilities from a connected server."""
        if not server.session:
            logger.warning("Cannot load capabilities: no session for server '%s'", server.name)
            return

        if not server.health.capabilities:
            logger.warning("Cannot load capabilities: no capabilities reported for server '%s'", server.name)
            return

        logger.debug("Loading capabilities for server '%s'", server.name)
        logger.debug(
            "Server capabilities: tools=%s, resources=%s, prompts=%s",
            server.health.capabilities.tools is not None,
            server.health.capabilities.resources is not None,
            server.health.capabilities.prompts is not None,
        )

        try:
            # Validate health check configuration against server capabilities
            if server.config.health_check:
                await self._validate_health_check_config(server)

            # Load tools
            if server.health.capabilities.tools:
                logger.debug("Requesting tools from server '%s'", server.name)
                try:
                    tools_result = await server.session.list_tools()
                    server.tools = tools_result.tools
                    logger.info("Loaded %d tools from server '%s'", len(server.tools), server.name)
                    for tool in server.tools:
                        logger.debug("Tool available: %s", tool.name)
                except Exception as e:
                    logger.exception("Failed to load tools from server '%s': %s", server.name, e)
            else:
                logger.debug("Server '%s' does not support tools", server.name)

            # Load resources
            if server.health.capabilities.resources:
                logger.debug("Requesting resources from server '%s'", server.name)
                try:
                    resources_result = await server.session.list_resources()
                    server.resources = resources_result.resources
                    logger.info("Loaded %d resources from server '%s'", len(server.resources), server.name)
                    for resource in server.resources:
                        logger.debug("Resource available: %s", resource.uri)
                except Exception as e:
                    logger.exception("Failed to load resources from server '%s': %s", server.name, e)
            else:
                logger.debug("Server '%s' does not support resources", server.name)

            # Load prompts
            if server.health.capabilities.prompts:
                logger.debug("Requesting prompts from server '%s'", server.name)
                try:
                    prompts_result = await server.session.list_prompts()
                    server.prompts = prompts_result.prompts
                    logger.info("Loaded %d prompts from server '%s'", len(server.prompts), server.name)
                    for prompt in server.prompts:
                        logger.debug("Prompt available: %s", prompt.name)
                except Exception as e:
                    logger.exception("Failed to load prompts from server '%s': %s", server.name, e)
            else:
                logger.debug("Server '%s' does not support prompts", server.name)

        except Exception:
            logger.exception(
                "Failed to load capabilities from server '%s'",
                server.name,
            )

    async def _validate_health_check_config(self, server: ManagedServer) -> None:
        """Validate health check configuration against server capabilities."""
        if not server.config.health_check or not server.health.capabilities:
            return

        hc = server.config.health_check
        caps = server.health.capabilities

        # Validate operation against server capabilities
        if hc.operation == "call_tool" and not caps.tools:
            logger.warning(
                "Server '%s' health check configured for 'call_tool' but server doesn't support tools",
                server.name,
            )
        elif hc.operation == "read_resource" and not caps.resources:
            logger.warning(
                "Server '%s' health check configured for 'read_resource' but server doesn't support resources",
                server.name,
            )
        elif hc.operation == "get_prompt" and not caps.prompts:
            logger.warning(
                "Server '%s' health check configured for 'get_prompt' but server doesn't support prompts",
                server.name,
            )

        # Validate specific tool exists if configured
        if hc.operation == "call_tool" and hc.tool_name and server.tools:
            tool_exists = any(tool.name == hc.tool_name for tool in server.tools)
            if not tool_exists:
                logger.warning(
                    "Server '%s' health check configured for tool '%s' but tool not found",
                    server.name,
                    hc.tool_name,
                )

        # Validate resource URI exists if configured
        if hc.operation == "read_resource" and hc.resource_uri and server.resources:
            resource_exists = any(str(resource.uri) == hc.resource_uri for resource in server.resources)
            if not resource_exists:
                logger.warning(
                    "Server '%s' health check configured for resource '%s' but resource not found",
                    server.name,
                    hc.resource_uri,
                )

        # Validate prompt exists if configured
        if hc.operation == "get_prompt" and hc.prompt_name and server.prompts:
            prompt_exists = any(prompt.name == hc.prompt_name for prompt in server.prompts)
            if not prompt_exists:
                logger.warning(
                    "Server '%s' health check configured for prompt '%s' but prompt not found",
                    server.name,
                    hc.prompt_name,
                )

    async def _health_check_loop(self) -> None:
        """Background health check loop."""
        while not self._shutdown_event.is_set():
            try:
                await self._perform_health_checks()
                await asyncio.sleep(30)  # Check every 30 seconds
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in health check loop")
                await asyncio.sleep(5)  # Brief pause before retrying

    async def _keep_alive_loop(self) -> None:
        """Keep-alive loop for all servers."""
        while not self._shutdown_event.is_set():
            try:
                await self._perform_keep_alive_checks()
                # Use the minimum keep-alive interval from all servers, with OAuth-specific intervals
                min_interval = min(
                    (
                        (
                            server.config.oauth_config.keep_alive_interval / 1000.0
                            if self._is_oauth_endpoint(server) and server.config.oauth_config
                            else server.config.health_check.keep_alive_interval / 1000.0
                        )
                        for server in self.servers.values()
                        if server.config.health_check and server.config.health_check.enabled
                    ),
                    default=60.0,
                )
                await asyncio.sleep(min_interval)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in keep-alive loop")
                await asyncio.sleep(5)  # Brief pause before retrying

    async def _oauth_token_refresh_loop(self) -> None:
        """Proactive OAuth token refresh loop for OAuth servers."""
        while not self._shutdown_event.is_set():
            try:
                await self._perform_oauth_token_refresh()
                # Check every 5 minutes for tokens that need refreshing
                await asyncio.sleep(300)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in OAuth token refresh loop")
                await asyncio.sleep(60)  # Brief pause before retrying

    async def _perform_health_checks(self) -> None:
        """Perform health checks on all servers."""
        for server in self.servers.values():
            if server.health.status == ServerStatus.CONNECTED and server.session:
                try:
                    # Use configured health check operation
                    health_timeout = 5.0
                    if server.config.health_check:
                        health_timeout = server.config.health_check.timeout / 1000.0

                    health_start_time = time.time()
                    await asyncio.wait_for(
                        self._execute_health_check_operation(server),
                        timeout=health_timeout,
                    )
                    health_elapsed = time.time() - health_start_time
                    logger.debug("Health check for server '%s' completed in %.3f seconds", server.name, health_elapsed)
                    server.health.last_seen = time.time()
                    server.health.consecutive_failures = 0  # Reset on successful check

                except Exception as e:
                    health_elapsed = time.time() - health_start_time

                    # Handle OAuth endpoints (SSE and HTTP) with special logic
                    if await self._handle_oauth_health_check_failure(server, e):
                        # OAuth recovery was attempted, continue to next server
                        continue

                    logger.warning(
                        "Health check failed for server '%s' after %.3f seconds: %s",
                        server.name,
                        health_elapsed,
                        type(e).__name__,
                    )
                    server.health.failure_count += 1
                    server.health.consecutive_failures += 1
                    server.health.last_error = str(e)

                    # Check if server should be marked as failed
                    max_failures = 3  # Default
                    if self.bridge_config.bridge and self.bridge_config.bridge.failover:
                        max_failures = self.bridge_config.bridge.failover.max_failures
                    elif server.config.health_check:
                        max_failures = server.config.health_check.max_consecutive_failures

                    # OAuth endpoints get more tolerance for connection issues
                    if self._is_oauth_endpoint(server):
                        max_failures = max(max_failures * 2, 6)  # Double the tolerance
                        logger.debug(
                            "OAuth endpoint '%s' gets increased failure tolerance: %d",
                            server.name,
                            max_failures,
                        )

                    if server.health.consecutive_failures >= max_failures:
                        logger.exception(
                            "Server '%s' marked as failed after %d consecutive failures",
                            server.name,
                            server.health.consecutive_failures,
                        )
                        server.health.status = ServerStatus.FAILED
                        await self._disconnect_server(server)

                        # Attempt automatic restart if enabled
                        if (
                            server.config.health_check
                            and server.config.health_check.auto_restart
                            and server.health.restart_count < server.config.health_check.max_restart_attempts
                        ):
                            # Start restart task and store reference to prevent GC
                            restart_task = asyncio.create_task(self._restart_server(server))
                            if not hasattr(self, "_restart_tasks"):
                                self._restart_tasks = set()
                            self._restart_tasks.add(restart_task)
                            restart_task.add_done_callback(self._restart_tasks.discard)

    def get_active_servers(self) -> list[ManagedServer]:
        """Get list of active (connected) servers."""
        active = [server for server in self.servers.values() if server.health.status == ServerStatus.CONNECTED]
        total_servers = len(self.servers)
        logger.info("Active servers: %d/%d", len(active), total_servers)
        for server in self.servers.values():
            logger.debug("Server '%s' status: %s", server.name, server.health.status)
        return active

    def _get_current_capability_names(self) -> dict[str, list[str]]:
        """Get current capability names for change detection."""
        try:
            tools = [tool.name for tool in self.get_aggregated_tools()]
            resources = [str(resource.uri) for resource in self.get_aggregated_resources()]
            prompts = [prompt.name for prompt in self.get_aggregated_prompts()]

            return {
                "tools": sorted(tools),
                "resources": sorted(resources),
                "prompts": sorted(prompts),
            }
        except Exception:
            logger.exception("Error getting current capabilities")
            return {"tools": [], "resources": [], "prompts": []}

    async def _check_and_notify_capability_changes(self) -> None:
        """Check for capability changes and notify clients if any are detected."""
        if not self.capability_change_notifier:
            return

        try:
            current_capabilities = self._get_current_capability_names()

            # Compare with last known capabilities
            changes_detected = False
            notification_data = {
                "tools_added": [],
                "tools_removed": [],
                "resources_added": [],
                "resources_removed": [],
                "prompts_added": [],
                "prompts_removed": [],
                "message": "Server capabilities have changed due to configuration update",
            }

            # Check tools changes
            old_tools = set(self._last_capabilities.get("tools", []))
            new_tools = set(current_capabilities["tools"])
            tools_added = list(new_tools - old_tools)
            tools_removed = list(old_tools - new_tools)

            if tools_added or tools_removed:
                changes_detected = True
                notification_data["tools_added"] = tools_added
                notification_data["tools_removed"] = tools_removed

            # Check resources changes
            old_resources = set(self._last_capabilities.get("resources", []))
            new_resources = set(current_capabilities["resources"])
            resources_added = list(new_resources - old_resources)
            resources_removed = list(old_resources - new_resources)

            if resources_added or resources_removed:
                changes_detected = True
                notification_data["resources_added"] = resources_added
                notification_data["resources_removed"] = resources_removed

            # Check prompts changes
            old_prompts = set(self._last_capabilities.get("prompts", []))
            new_prompts = set(current_capabilities["prompts"])
            prompts_added = list(new_prompts - old_prompts)
            prompts_removed = list(old_prompts - new_prompts)

            if prompts_added or prompts_removed:
                changes_detected = True
                notification_data["prompts_added"] = prompts_added
                notification_data["prompts_removed"] = prompts_removed

            # Update stored capabilities
            self._last_capabilities = current_capabilities

            # Send notification if changes were detected
            if changes_detected:
                logger.info("Capability changes detected, sending notification to clients")
                await self.capability_change_notifier(notification_data)
            else:
                logger.debug("No capability changes detected")

        except Exception:
            logger.exception("Error checking capability changes")

    def get_server_by_name(self, name: str) -> ManagedServer | None:
        """Get a server by name."""
        normalized_name = normalize_server_name(name)
        return self.servers.get(normalized_name)

    def get_aggregated_tools(self) -> list[types.Tool]:
        """Get aggregated tools from all active servers."""
        tools: list[types.Tool] = []
        seen_names = set()
        filtered_tools: list[dict[str, str]] = []  # Track filtered tools
        total_tools_before_filter = 0

        # Sort servers by priority (lower number = higher priority)
        active_servers = sorted(self.get_active_servers(), key=lambda s: s.config.priority)
        logger.debug("Aggregating tools from %d active servers", len(active_servers))

        if not active_servers:
            logger.warning("No active servers available for tool aggregation")
            return tools

        for server in active_servers:
            logger.debug(
                "Server '%s' status: %s, has %d tools", server.name, server.health.status.value, len(server.tools)
            )
            if server.tools:
                for tool in server.tools:
                    logger.debug("Server '%s' tool: %s", server.name, tool.name)

            namespace = server.get_effective_namespace("tools", self.bridge_config.bridge)

            # Create security policy for this server using bridge-level read_only_mode
            # Always create a BridgeSecurityConfig, using defaults if bridge config is None
            if self.bridge_config.bridge:
                bridge_security = BridgeSecurityConfig(
                    read_only_mode=self.bridge_config.bridge.read_only_mode,
                    tools=self.bridge_config.bridge.security.tools if self.bridge_config.bridge.security else None,
                )
            else:
                # Create default bridge security config
                bridge_security = BridgeSecurityConfig()

            security_policy = SecurityPolicy(
                bridge_config=bridge_security,
                server_config=server.config.security
                if hasattr(server.config, "security") and server.config.security
                else None,
            )

            for tool in server.tools:
                total_tools_before_filter += 1
                tool_name = tool.name
                original_tool_name = tool.name
                if namespace:
                    tool_name = f"{namespace}__{tool.name}"

                # Apply security filtering - check if tool is allowed
                if not security_policy.is_tool_allowed(original_tool_name):
                    logger.debug(
                        "Tool '%s' from server '%s' blocked by security policy", original_tool_name, server.name
                    )
                    filtered_tools.append(
                        {"tool": original_tool_name, "server": server.name, "namespaced_name": tool_name}
                    )
                    continue

                # Handle name conflicts based on configuration
                if tool_name in seen_names:
                    if self.bridge_config.bridge and self.bridge_config.bridge.conflict_resolution == "error":
                        msg = f"Tool name conflict: {tool_name}"
                        raise ValueError(msg)
                    if self.bridge_config.bridge and self.bridge_config.bridge.conflict_resolution == "first":
                        continue  # Skip this tool
                    # For "priority" and "namespace", we already handled it above

                # Create namespaced tool
                namespaced_tool = types.Tool(
                    name=tool_name,
                    description=tool.description,
                    inputSchema=tool.inputSchema,
                )

                tools.append(namespaced_tool)
                seen_names.add(tool_name)
                logger.debug("Tool '%s' from server '%s' allowed", original_tool_name, server.name)

        # Store filtered tools for status reporting
        self._filtered_tools = filtered_tools

        # Log filtering summary
        filtered_count = len(filtered_tools)
        if filtered_count > 0:
            logger.warning("Security filtering: %d tools filtered out, %d tools available", filtered_count, len(tools))
            if logger.level <= logging.DEBUG:
                for filtered in filtered_tools:
                    logger.debug("Filtered tool: %s from server %s", filtered["tool"], filtered["server"])
        else:
            logger.info("Security filtering: %d tools available (no tools filtered)", len(tools))

        return tools

    def get_filtered_tools(self) -> list[dict[str, str]]:
        """Get information about tools that were filtered out by security policies.

        Returns:
            List of filtered tool dictionaries with keys: tool, server, namespaced_name
        """
        return self._filtered_tools.copy()

    def get_aggregated_resources(self) -> list[types.Resource]:
        """Get aggregated resources from all active servers."""
        resources = []
        seen_uris = set()

        # Sort servers by priority
        active_servers = sorted(self.get_active_servers(), key=lambda s: s.config.priority)

        for server in active_servers:
            namespace = server.get_effective_namespace("resources", self.bridge_config.bridge)

            for resource in server.resources:
                resource_uri = str(resource.uri)
                if namespace:
                    # Create a safe namespace-prefixed URI
                    # Use a simple prefix approach instead of trying to create a valid URL scheme
                    original_uri = str(resource.uri)
                    # Just prefix with namespace and double underscore separator
                    resource_uri = f"{namespace}__{original_uri}"

                # Handle URI conflicts
                if resource_uri in seen_uris:
                    if self.bridge_config.bridge and self.bridge_config.bridge.conflict_resolution == "error":
                        msg = f"Resource URI conflict: {resource_uri}"
                        raise ValueError(msg)
                    if self.bridge_config.bridge and self.bridge_config.bridge.conflict_resolution == "first":
                        continue

                # Create namespaced resource
                try:
                    # Use helper function to handle both standard and custom URI schemes
                    parsed_uri = _create_resource_uri(resource_uri)

                    # If _create_resource_uri returned a string (custom scheme),
                    # don't try to convert to AnyUrl again as it will fail
                    if isinstance(parsed_uri, str):
                        # For custom schemes that failed AnyUrl validation, we need a different approach
                        # Try to namespace the path part instead of the scheme
                        if namespace and "://" in original_uri:
                            scheme, rest = original_uri.split("://", 1)
                            # Namespace the path part while keeping the scheme intact
                            rest_stripped = rest.strip("/ \t\r\n") if rest is not None else ""
                            if rest_stripped:
                                namespaced_uri = f"{scheme}://{namespace}/{rest_stripped}"
                            else:
                                namespaced_uri = f"{scheme}://{namespace}"
                        else:
                            namespaced_uri = original_uri

                        # Try to create AnyUrl with the properly namespaced URI
                        resource_uri_typed = AnyUrl(namespaced_uri)
                    else:
                        resource_uri_typed = parsed_uri

                    namespaced_resource = types.Resource(
                        uri=resource_uri_typed,
                        name=resource.name,
                        description=resource.description,
                        mimeType=resource.mimeType,
                    )
                except (ValueError, TypeError) as e:
                    # Skip resources with invalid URIs and log a detailed warning
                    error_msg = str(e)
                    if "Input should be a valid URL" in error_msg:
                        # Extract the relevant part of the pydantic validation error
                        error_details = error_msg.split("Input should be a valid URL")[0].strip()
                        if not error_details:
                            error_details = "Invalid URL format"
                    else:
                        error_details = error_msg

                    logger.warning(
                        "Skipping resource '%s' from server '%s' - URI validation failed: %s "
                        "(original: '%s', namespaced: '%s')",
                        resource.name,
                        server.name,
                        error_details,
                        str(resource.uri),
                        resource_uri,
                    )
                    continue

                resources.append(namespaced_resource)
                seen_uris.add(resource_uri)

        return resources

    def get_aggregated_prompts(self) -> list[types.Prompt]:
        """Get aggregated prompts from all active servers."""
        prompts = []
        seen_names = set()

        # Sort servers by priority
        active_servers = sorted(self.get_active_servers(), key=lambda s: s.config.priority)

        for server in active_servers:
            namespace = server.get_effective_namespace("prompts", self.bridge_config.bridge)

            for prompt in server.prompts:
                prompt_name = prompt.name
                if namespace:
                    prompt_name = f"{namespace}__{prompt.name}"

                # Handle name conflicts
                if prompt_name in seen_names:
                    if self.bridge_config.bridge and self.bridge_config.bridge.conflict_resolution == "error":
                        msg = f"Prompt name conflict: {prompt_name}"
                        raise ValueError(msg)
                    if self.bridge_config.bridge and self.bridge_config.bridge.conflict_resolution == "first":
                        continue

                # Create namespaced prompt
                namespaced_prompt = types.Prompt(
                    name=prompt_name,
                    description=prompt.description,
                    arguments=prompt.arguments,
                )

                prompts.append(namespaced_prompt)
                seen_names.add(prompt_name)

        return prompts

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        """Call a tool by name, routing to the appropriate server."""
        # Parse namespace from tool name
        if "__" in tool_name:
            namespace, actual_tool_name = tool_name.split("__", 1)
            # Find server that provides this namespaced tool
            server = None
            for s in self.get_active_servers():
                server_namespace = s.get_effective_namespace("tools", self.bridge_config.bridge)
                if server_namespace == namespace and any(tool.name == actual_tool_name for tool in s.tools):
                    server = s
                    break
        else:
            # No namespace, find first server with this tool
            server = None
            actual_tool_name = tool_name
            for s in self.get_active_servers():
                if any(tool.name == actual_tool_name for tool in s.tools):
                    server = s
                    break

        if not server or not server.session:
            msg = f"No active server found for tool: {tool_name}"
            raise ValueError(msg)

        # Verify tool exists
        if not any(tool.name == actual_tool_name for tool in server.tools):
            msg = f"Tool '{actual_tool_name}' not found on server '{server.name}'"
            raise ValueError(msg)

        # Apply security check for tool execution using bridge-level read_only_mode
        # Always create a BridgeSecurityConfig, using defaults if bridge config is None
        if self.bridge_config.bridge:
            bridge_security = BridgeSecurityConfig(
                read_only_mode=self.bridge_config.bridge.read_only_mode,
                tools=self.bridge_config.bridge.security.tools if self.bridge_config.bridge.security else None,
            )
        else:
            # Create default bridge security config
            bridge_security = BridgeSecurityConfig()

        security_policy = SecurityPolicy(
            bridge_config=bridge_security,
            server_config=server.config.security
            if hasattr(server.config, "security") and server.config.security
            else None,
        )

        if not security_policy.is_tool_allowed(actual_tool_name):
            msg = f"Tool '{actual_tool_name}' blocked by security policy"
            logger.warning("Blocked tool execution: %s", msg)
            raise PermissionError(msg)

        # Use original arguments for now (AccessController sanitization will be added later if needed)
        sanitized_arguments = arguments

        # Call the tool
        try:
            return await server.session.call_tool(actual_tool_name, sanitized_arguments)
        except McpError as e:
            # Log MCP errors as warnings and re-raise
            logger.warning(
                "MCP error calling tool '%s' on server '%s': %s",
                actual_tool_name,
                server.name,
                e.error.message,
            )
            raise
        except Exception:
            logger.exception(
                "Error calling tool '%s' on server '%s'",
                actual_tool_name,
                server.name,
            )
            raise

    async def read_resource(self, resource_uri: str) -> types.ReadResourceResult:
        """Read a resource by URI, routing to the appropriate server."""
        # Parse namespace from URI using our double underscore separator
        if "__" in resource_uri:
            namespace, actual_uri = resource_uri.split("__", 1)
            # Find server that provides this namespaced resource
            server = None
            for s in self.get_active_servers():
                server_namespace = s.get_effective_namespace("resources", self.bridge_config.bridge)
                if server_namespace == namespace and any(str(resource.uri) == actual_uri for resource in s.resources):
                    server = s
                    break
        else:
            # No namespace, find first server with this resource
            server = None
            actual_uri = resource_uri
            for s in self.get_active_servers():
                if any(str(resource.uri) == actual_uri for resource in s.resources):
                    server = s
                    break

        if not server or not server.session:
            msg = f"No active server found for resource: {resource_uri}"
            raise ValueError(msg)

        # Call the resource
        try:
            # Create resource URL using helper function
            try:
                resource_url = _create_resource_uri(actual_uri)
                # Convert to AnyUrl if needed
                typed_resource_url = AnyUrl(resource_url) if isinstance(resource_url, str) else resource_url
            except ValueError as url_error:
                # If the URI is invalid, wrap it in a more informative error
                msg = f"Invalid resource URI '{actual_uri}' from server '{server.name}': {url_error}"
                raise ValueError(msg) from url_error

            return await server.session.read_resource(typed_resource_url)
        except McpError as e:
            # Log MCP errors as warnings and re-raise
            logger.warning(
                "MCP error reading resource '%s' on server '%s': %s",
                actual_uri,
                server.name,
                e.error.message,
            )
            raise
        except Exception:
            logger.exception(
                "Error reading resource '%s' on server '%s'",
                actual_uri,
                server.name,
            )
            raise

    async def get_prompt(
        self,
        prompt_name: str,
        arguments: dict[str, str] | None = None,
    ) -> types.GetPromptResult:
        """Get a prompt by name, routing to the appropriate server."""
        # Parse namespace from prompt name
        if "__" in prompt_name:
            namespace, actual_prompt_name = prompt_name.split("__", 1)
            # Find server that provides this namespaced prompt
            server = None
            for s in self.get_active_servers():
                server_namespace = s.get_effective_namespace("prompts", self.bridge_config.bridge)
                if server_namespace == namespace and any(prompt.name == actual_prompt_name for prompt in s.prompts):
                    server = s
                    break
        else:
            # No namespace, find first server with this prompt
            server = None
            actual_prompt_name = prompt_name
            for s in self.get_active_servers():
                if any(prompt.name == actual_prompt_name for prompt in s.prompts):
                    server = s
                    break

        if not server or not server.session:
            msg = f"No active server found for prompt: {prompt_name}"
            raise ValueError(msg)

        # Call the prompt
        try:
            return await server.session.get_prompt(actual_prompt_name, arguments)
        except McpError as e:
            # Log MCP errors as warnings and re-raise
            logger.warning(
                "MCP error getting prompt '%s' on server '%s': %s",
                actual_prompt_name,
                server.name,
                e.error.message,
            )
            raise
        except Exception:
            logger.exception(
                "Error getting prompt '%s' on server '%s'",
                actual_prompt_name,
                server.name,
            )
            raise

    def get_server_status(self) -> dict[str, dict[str, Any]]:
        """Get status information for all servers."""
        status = {}
        for name, server in self.servers.items():
            status[name] = {
                "status": server.health.status.value,
                "last_seen": server.health.last_seen,
                "failure_count": server.health.failure_count,
                "last_error": server.health.last_error,
                "capabilities": {
                    "tools": len(server.tools),
                    "resources": len(server.resources),
                    "prompts": len(server.prompts),
                },
                "health": {
                    "consecutive_failures": server.health.consecutive_failures,
                    "restart_count": server.health.restart_count,
                    "last_restart": server.health.last_restart,
                    "keep_alive_failures": server.health.keep_alive_failures,
                    "last_keep_alive": server.health.last_keep_alive,
                },
                "config": {
                    "enabled": server.config.enabled,
                    "command": server.config.command,
                    "args": server.config.args,
                    "priority": server.config.priority,
                    "tags": server.config.tags,
                    "health_check_enabled": (
                        server.config.health_check.enabled if server.config.health_check else False
                    ),
                    "health_check_operation": (
                        server.config.health_check.operation if server.config.health_check else "list_tools"
                    ),
                    "auto_restart": (server.config.health_check.auto_restart if server.config.health_check else False),
                },
            }
        return status

    async def subscribe_resource(self, resource_uri: str) -> None:
        """Subscribe to a resource across all relevant servers."""
        logger.debug("Subscribing to resource: %s", resource_uri)

        # Parse namespace from URI to find target server
        if "://" in resource_uri:
            namespace, actual_uri = resource_uri.split("://", 1)
            # Find server that provides this namespaced resource
            for server in self.get_active_servers():
                server_namespace = server.get_effective_namespace("resources", self.bridge_config.bridge)
                if server_namespace == namespace and any(resource.uri == actual_uri for resource in server.resources):
                    if server.session:
                        try:
                            # Convert to AnyUrl for type safety
                            resource_uri_parsed = _create_resource_uri(actual_uri)
                            typed_resource_uri = (
                                AnyUrl(resource_uri_parsed)
                                if isinstance(resource_uri_parsed, str)
                                else resource_uri_parsed
                            )
                            await server.session.subscribe_resource(typed_resource_uri)
                            logger.debug(
                                "Subscribed to resource '%s' on server '%s'",
                                actual_uri,
                                server.name,
                            )
                        except Exception:
                            logger.exception(
                                "Failed to subscribe to resource '%s' on server '%s'",
                                actual_uri,
                                server.name,
                            )
                    break
        else:
            # No namespace, subscribe on all servers that have this resource
            actual_uri = resource_uri
            subscribed_count = 0
            for server in self.get_active_servers():
                if any(resource.uri == actual_uri for resource in server.resources) and server.session:
                    try:
                        await server.session.subscribe_resource(AnyUrl(actual_uri))
                        logger.debug(
                            "Subscribed to resource '%s' on server '%s'",
                            actual_uri,
                            server.name,
                        )
                        subscribed_count += 1
                    except Exception:
                        logger.exception(
                            "Failed to subscribe to resource '%s' on server '%s'",
                            actual_uri,
                            server.name,
                        )

            if subscribed_count == 0:
                logger.warning("No servers found with resource: %s", resource_uri)

    async def unsubscribe_resource(self, resource_uri: str) -> None:
        """Unsubscribe from a resource across all relevant servers."""
        logger.debug("Unsubscribing from resource: %s", resource_uri)

        # Parse namespace from URI to find target server
        if "://" in resource_uri:
            namespace, actual_uri = resource_uri.split("://", 1)
            # Find server that provides this namespaced resource
            for server in self.get_active_servers():
                server_namespace = server.get_effective_namespace("resources", self.bridge_config.bridge)
                if server_namespace == namespace and any(resource.uri == actual_uri for resource in server.resources):
                    if server.session:
                        try:
                            # Convert to AnyUrl for type safety
                            resource_uri_parsed = _create_resource_uri(actual_uri)
                            typed_resource_uri = (
                                AnyUrl(resource_uri_parsed)
                                if isinstance(resource_uri_parsed, str)
                                else resource_uri_parsed
                            )
                            await server.session.unsubscribe_resource(typed_resource_uri)
                            logger.debug(
                                "Unsubscribed from resource '%s' on server '%s'",
                                actual_uri,
                                server.name,
                            )
                        except Exception:
                            logger.exception(
                                "Failed to unsubscribe from resource '%s' on server '%s'",
                                actual_uri,
                                server.name,
                            )
                    break
        else:
            # No namespace, unsubscribe from all servers that have this resource
            actual_uri = resource_uri
            unsubscribed_count = 0
            for server in self.get_active_servers():
                if any(resource.uri == actual_uri for resource in server.resources) and server.session:
                    try:
                        await server.session.unsubscribe_resource(AnyUrl(actual_uri))
                        logger.debug(
                            "Unsubscribed from resource '%s' on server '%s'",
                            actual_uri,
                            server.name,
                        )
                        unsubscribed_count += 1
                    except Exception:
                        logger.exception(
                            "Failed to unsubscribe from resource '%s' on server '%s'",
                            actual_uri,
                            server.name,
                        )

            if unsubscribed_count == 0:
                logger.warning("No servers found with resource: %s", resource_uri)

    async def set_logging_level(self, level: types.LoggingLevel) -> None:
        """Set logging level on all active managed servers."""
        logger.debug("Setting logging level to %s on all managed servers", level)

        forwarded_count = 0
        for server in self.get_active_servers():
            if server.session:
                try:
                    await server.session.set_logging_level(level)
                    logger.debug("Set logging level to %s on server", level)
                    forwarded_count += 1
                except Exception:
                    logger.exception(
                        "Failed to set logging level to %s on server '%s'",
                        level,
                        server.name,
                    )

        logger.info("Forwarded logging level %s to %d servers", level, forwarded_count)

    async def get_completions(
        self,
        ref: types.ResourceReference | types.PromptReference,
        argument: types.CompletionArgument,
    ) -> list[str]:
        """Get completions from all active managed servers and aggregate them."""
        logger.debug("Getting completions for ref: %s", ref)

        all_completions = []

        for server in self.get_active_servers():
            if server.session:
                try:
                    # Convert CompletionArgument to dict[str, str] format for session.complete
                    argument_dict = {}
                    if hasattr(argument, "name") and hasattr(argument, "value"):
                        argument_dict[argument.name] = argument.value

                    # Call the server's completion endpoint
                    result = await server.session.complete(ref, argument_dict)
                    if result.completion and result.completion.values:
                        server_completions = result.completion.values
                        logger.debug(
                            "Got %d completions from server '%s'",
                            len(server_completions),
                            server.name,
                        )
                        all_completions.extend(server_completions)

                except Exception:
                    logger.exception(
                        "Failed to get completions from server '%s'",
                        server.name,
                    )

        # Remove duplicates while preserving order
        unique_completions = []
        seen = set()
        for completion in all_completions:
            if completion not in seen:
                seen.add(completion)
                unique_completions.append(completion)

        logger.debug(
            "Aggregated %d unique completions from %d servers",
            len(unique_completions),
            len(self.get_active_servers()),
        )

        return unique_completions

    async def _perform_keep_alive_checks(self) -> None:
        """Perform keep-alive checks on all connected servers."""
        current_time = time.time()

        for server in self.servers.values():
            if (
                server.health.status != ServerStatus.CONNECTED
                or not server.session
                or not server.config.health_check
                or not server.config.health_check.enabled
            ):
                continue

            # Check if it's time for a keep-alive ping (use OAuth-specific interval for OAuth servers)
            time_since_last_keep_alive = current_time - server.health.last_keep_alive
            keep_alive_interval = (
                server.config.oauth_config.keep_alive_interval / 1000.0
                if self._is_oauth_endpoint(server) and server.config.oauth_config
                else server.config.health_check.keep_alive_interval / 1000.0
            )

            if time_since_last_keep_alive >= keep_alive_interval:
                # Start keep-alive task and store reference to prevent GC
                keep_alive_task = asyncio.create_task(self._send_keep_alive(server))
                if not hasattr(self, "_keep_alive_tasks"):
                    self._keep_alive_tasks = set()
                self._keep_alive_tasks.add(keep_alive_task)
                keep_alive_task.add_done_callback(self._keep_alive_tasks.discard)

    async def _send_keep_alive(self, server: ManagedServer) -> None:
        """Send a keep-alive ping to a specific server."""
        if not server.session or not server.config.health_check:
            return

        try:
            # Use configured keep-alive operation (same as health check by default)
            timeout = server.config.health_check.keep_alive_timeout / 1000.0
            await asyncio.wait_for(self._execute_health_check_operation(server), timeout=timeout)

            # Update keep-alive tracking
            server.health.last_keep_alive = time.time()
            server.health.keep_alive_failures = 0
            logger.debug("Keep-alive successful")

        except Exception as e:
            server.health.keep_alive_failures += 1
            logger.warning(
                "Keep-alive failed for server '%s' (failure %d): %s",
                server.name,
                server.health.keep_alive_failures,
                str(e),
            )

            # If keep-alive failures exceed threshold, mark as problematic
            max_keep_alive_failures = 3
            if server.health.keep_alive_failures >= max_keep_alive_failures:
                logger.exception(
                    "Server '%s' has %d consecutive keep-alive failures, marking as failed",
                    server.name,
                    server.health.keep_alive_failures,
                )
                server.health.status = ServerStatus.FAILED
                server.health.consecutive_failures += server.health.keep_alive_failures
                await self._disconnect_server(server)

                # Attempt restart if enabled
                if (
                    server.config.health_check.auto_restart
                    and server.health.restart_count < server.config.health_check.max_restart_attempts
                ):
                    # Start restart task and store reference to prevent GC
                    restart_task = asyncio.create_task(self._restart_server(server))
                    if not hasattr(self, "_restart_tasks"):
                        self._restart_tasks = set()
                    self._restart_tasks.add(restart_task)
                    restart_task.add_done_callback(self._restart_tasks.discard)

    async def _restart_server(self, server: ManagedServer) -> None:
        """Restart a failed server."""
        # Prevent multiple simultaneous restart attempts
        if server.name not in self._restart_locks:
            self._restart_locks[server.name] = asyncio.Lock()

        async with self._restart_locks[server.name]:
            if server.health.status != ServerStatus.FAILED:
                return  # Server recovered while we were waiting for lock

            server.health.restart_count += 1
            server.health.last_restart = time.time()

            logger.info(
                "Attempting to restart server '%s' (attempt %d/%d)",
                server.name,
                server.health.restart_count,
                (server.config.health_check.max_restart_attempts if server.config.health_check else 5),
            )

            try:
                # Wait before restart attempt
                if server.config.health_check:
                    restart_delay = server.config.health_check.restart_delay / 1000.0
                    await asyncio.sleep(restart_delay)
                else:
                    await asyncio.sleep(5.0)  # Default delay

                # Ensure server is disconnected first
                await self._disconnect_server(server)

                # Reset some health metrics for restart
                server.health.consecutive_failures = 0
                server.health.keep_alive_failures = 0

                # Attempt to reconnect
                await self._connect_server(server)

                # Check if restart was successful
                # Note: _connect_server will set status to CONNECTED or FAILED
                if server.health.status is ServerStatus.CONNECTED:  # type: ignore[comparison-overlap]
                    logger.info("Successfully restarted server")  # type: ignore[unreachable]
                else:
                    logger.error("Failed to restart server")

            except Exception as e:
                logger.exception("Error during server restart for '%s'", server.name)
                server.health.last_error = f"Restart failed: {e!s}"

    async def reconnect_server(self, server: ManagedServer) -> None:
        """Force reconnection of a specific server.

        Args:
            server: The server to reconnect
        """
        logger.info("Forcing reconnection for server '%s'", server.name)

        try:
            # First disconnect cleanly if connected
            if server.health.status in (ServerStatus.CONNECTED, ServerStatus.CONNECTING):
                logger.debug("Disconnecting server '%s' before reconnecting", server.name)
                await self._disconnect_server(server)

            # Small delay to ensure cleanup completes
            await asyncio.sleep(0.1)

            # Now reconnect
            await self._connect_server(server)
            logger.info("Server '%s' reconnected successfully", server.name)

        except asyncio.CancelledError:
            logger.warning("Reconnection of server '%s' was cancelled", server.name)
            server.health.status = ServerStatus.FAILED
            raise
        except Exception:
            logger.exception("Failed to reconnect server '%s'", server.name)
            server.health.status = ServerStatus.FAILED
            raise

    async def update_servers(self, new_server_configs: dict[str, BridgeServerConfig]) -> None:
        """Update server configurations dynamically.

        This method compares the current server configuration with the new configuration
        and performs the necessary operations to add, remove, or update servers.

        Args:
            new_server_configs: New server configurations to apply
        """
        logger.info("Updating server configurations...")

        # Get current server names and new server names (normalized)
        current_names = set(self.servers.keys())
        new_names = {normalize_server_name(name) for name in new_server_configs}

        # Determine what changes need to be made
        servers_to_add = new_names - current_names
        servers_to_remove = current_names - new_names
        servers_to_check_update = current_names & new_names

        logger.info(
            "Server configuration changes: %d to add, %d to remove, %d to check for updates",
            len(servers_to_add),
            len(servers_to_remove),
            len(servers_to_check_update),
        )

        # Remove servers that are no longer in configuration
        for server_name in servers_to_remove:
            await self._remove_server(server_name)

        # Add new servers (need to find original config name from normalized name)
        for normalized_name in servers_to_add:
            # Find the original config name that normalizes to this name
            original_name = None
            for orig_name in new_server_configs:
                if normalize_server_name(orig_name) == normalized_name:
                    original_name = orig_name
                    break
            if original_name:
                config = new_server_configs[original_name]
                await self._add_server(original_name, config)

        # Check for configuration updates on existing servers
        for normalized_name in servers_to_check_update:
            # Find the original config name that normalizes to this name
            original_name = None
            for orig_name in new_server_configs:
                if normalize_server_name(orig_name) == normalized_name:
                    original_name = orig_name
                    break
            if original_name:
                old_config = self.servers[normalized_name].config
                new_config = new_server_configs[original_name]

                if self._server_config_changed(old_config, new_config):
                    logger.info(
                        "Configuration changed for server '%s', updating...",
                        original_name,
                    )
                    await self._update_server(original_name, new_config)

        logger.info("Server configuration update completed")

        # Check for capability changes and notify clients
        await self._check_and_notify_capability_changes()

    async def _add_server(self, name: str, config: BridgeServerConfig) -> None:
        """Add a new server to the manager."""
        if not config.enabled:
            logger.info("Server '%s' is disabled, skipping", name)
            return

        logger.info("Adding new server '%s'", name)

        # Create managed server with normalized name
        normalized_name = normalize_server_name(name)
        managed_server = ManagedServer(name=normalized_name, config=config)
        self.servers[normalized_name] = managed_server
        self._restart_locks[normalized_name] = asyncio.Lock()

        # Connect to the server
        await self._connect_server(managed_server)

        logger.info("Successfully added server '%s'", name)

    async def _remove_server(self, name: str) -> None:
        """Remove a server from the manager."""
        logger.info("Removing server '%s'", name)

        # Server is stored with normalized name
        normalized_name = normalize_server_name(name)
        server = self.servers.get(normalized_name)
        if server:
            # Disconnect the server
            await self._disconnect_server(server)

            # Remove from tracking
            del self.servers[normalized_name]
            if normalized_name in self._restart_locks:
                del self._restart_locks[normalized_name]

        logger.info("Successfully removed server '%s'", name)

    async def _update_server(self, name: str, new_config: BridgeServerConfig) -> None:
        """Update an existing server's configuration."""
        # Server is stored with normalized name
        normalized_name = normalize_server_name(name)
        server = self.servers.get(normalized_name)
        if not server:
            logger.warning("Attempted to update non-existent server '%s'", name)
            return

        logger.info("Updating configuration for server '%s'", name)

        # If the server is becoming disabled, just disconnect it
        if not new_config.enabled:
            await self._disconnect_server(server)
            server.config = new_config
            server.health.status = ServerStatus.DISABLED
            return

        # If server was disabled and is now enabled, reconnect with new config
        if not server.config.enabled and new_config.enabled:
            server.config = new_config
            await self._connect_server(server)
            return

        # For other configuration changes, we need to restart the connection
        # Check if command/args changed (requires restart)
        if (
            server.config.command != new_config.command
            or server.config.args != new_config.args
            or server.config.env != new_config.env
        ):
            logger.info("Server '%s' command/args changed, restarting connection...", name)
            await self._disconnect_server(server)
            server.config = new_config
            await self._connect_server(server)
        else:
            # For other config changes (priority, health check, etc.), just update config
            server.config = new_config

            # Re-validate health check configuration
            if server.session and server.health.capabilities:
                await self._validate_health_check_config(server)

        logger.info("Successfully updated server '%s'", name)

    def _server_config_changed(self, old_config: BridgeServerConfig, new_config: BridgeServerConfig) -> bool:
        """Check if server configuration has meaningfully changed."""
        # Check key fields that would require action
        return (
            old_config.enabled != new_config.enabled
            or old_config.command != new_config.command
            or old_config.args != new_config.args
            or old_config.env != new_config.env
            or old_config.priority != new_config.priority
            or old_config.timeout != new_config.timeout
            or old_config.health_check != new_config.health_check
            or old_config.tool_namespace != new_config.tool_namespace
            or old_config.resource_namespace != new_config.resource_namespace
            or old_config.prompt_namespace != new_config.prompt_namespace
            or old_config.tags != new_config.tags
        )

    async def _execute_health_check_operation(self, server: ManagedServer) -> None:
        """Execute the configured health check operation for a server."""
        if not server.session:
            msg = f"No session available for server '{server.name}'"
            raise RuntimeError(msg)

        if not server.config.health_check:
            # Fallback to default operation
            await server.session.list_tools()
            return

        operation = server.config.health_check.operation.lower()
        session = server.session

        try:
            if operation == "list_tools":
                await session.list_tools()
            elif operation == "list_resources":
                await session.list_resources()
            elif operation == "list_prompts":
                await session.list_prompts()
            elif operation == "call_tool":
                if not server.config.health_check.tool_name:
                    logger.warning(
                        "Health check operation 'call_tool' requires 'toolName' for server '%s', "
                        "falling back to list_tools",
                        server.name,
                    )
                    await session.list_tools()
                    return

                tool_args = server.config.health_check.tool_arguments or {}
                await session.call_tool(server.config.health_check.tool_name, tool_args)

            elif operation == "read_resource":
                if not server.config.health_check.resource_uri:
                    logger.warning(
                        "Health check operation 'read_resource' requires 'resourceUri' for "
                        "server '%s', falling back to list_tools",
                        server.name,
                    )
                    await session.list_tools()
                    return

                # Convert to AnyUrl for type safety
                resource_uri = _create_resource_uri(server.config.health_check.resource_uri)
                typed_uri = AnyUrl(resource_uri) if isinstance(resource_uri, str) else resource_uri
                await session.read_resource(typed_uri)

            elif operation == "get_prompt":
                if not server.config.health_check.prompt_name:
                    logger.warning(
                        "Health check operation 'get_prompt' requires 'promptName' for "
                        "server '%s', falling back to list_tools",
                        server.name,
                    )
                    await session.list_tools()
                    return

                prompt_args = server.config.health_check.prompt_arguments
                await session.get_prompt(server.config.health_check.prompt_name, prompt_args)

            elif operation in ["ping", "health", "status"]:
                # For common health check operations, try to use a ping if available
                # Fall back to list_tools if no specific ping operation exists
                try:
                    # Some servers might have a dedicated ping/health operation
                    if hasattr(session, "ping"):
                        await session.ping()
                    else:
                        await session.list_tools()
                except AttributeError:
                    await session.list_tools()

            else:
                logger.warning(
                    "Unknown health check operation '%s' for server '%s', falling back to list_tools",
                    operation,
                    server.name,
                )
                await session.list_tools()

        except Exception as e:
            # Log the specific operation that failed for debugging
            logger.debug(
                "Health check operation '%s' failed for server '%s': %s",
                operation,
                server.name,
                str(e),
            )
            # Re-raise the exception to be handled by the calling function
            raise

    def _is_oauth_sse_endpoint(self, server: ManagedServer) -> bool:
        """Check if server is an OAuth-enabled SSE endpoint."""
        return server.config.transport_type == "sse" and server.config.is_oauth_enabled()

    def _is_oauth_endpoint(self, server: ManagedServer) -> bool:
        """Check if server is an OAuth-enabled endpoint (SSE or HTTP)."""
        return server.config.is_oauth_enabled() and server.config.transport_type in ("sse", "http")

    async def _handle_oauth_health_check_failure(self, server: ManagedServer, error: Exception) -> bool:
        """Handle health check failures for OAuth endpoints (both SSE and HTTP).

        Returns:
            True if OAuth recovery was attempted (skip normal failure handling)
            False if normal failure handling should proceed
        """
        if not self._is_oauth_endpoint(server):
            return False

        error_str = str(error).lower()

        # Check for OAuth/connection-related errors
        oauth_error_indicators = [
            "unauthorized",
            "401",
            "authentication",
            "token",
            "closedresourceerror",
            "readerror",
            "connectionerror",
            "timeout",
            "connection closed",
            "broken",
        ]

        is_oauth_related = any(indicator in error_str for indicator in oauth_error_indicators)

        if is_oauth_related:
            logger.info(
                "[BRIDGE] OAuth SSE endpoint '%s' health check failed with connection issue - attempting recovery",
                server.name,
            )

            # Increment failure count but with special handling
            server.health.failure_count += 1
            server.health.consecutive_failures += 1
            server.health.last_error = str(error)

            # For OAuth endpoints, try to reconnect instead of immediate failure
            if server.health.consecutive_failures <= 3:  # Give it a few tries
                logger.info(
                    '[BRIDGE] %s - "%d"',
                    server.name,
                    server.health.consecutive_failures,
                )

                # Schedule a reconnection attempt in background
                reconnect_task = asyncio.create_task(self._attempt_oauth_sse_reconnection(server))
                if not hasattr(self, "_oauth_reconnect_tasks"):
                    self._oauth_reconnect_tasks = set()
                self._oauth_reconnect_tasks.add(reconnect_task)
                reconnect_task.add_done_callback(self._oauth_reconnect_tasks.discard)

                return True  # Skip normal failure handling

        return False  # Proceed with normal failure handling

    async def _attempt_oauth_sse_reconnection(self, server: ManagedServer) -> None:
        """Attempt to reconnect an OAuth SSE endpoint with fresh authentication.

        This method:
        1. Disconnects the current failed connection
        2. Waits a brief period for cleanup
        3. Attempts to reconnect with OAuth token refresh
        """
        try:
            # Disconnect current failed connection
            await self._disconnect_server(server)

            # Brief wait for cleanup
            await asyncio.sleep(2)

            # Attempt reconnection - this will trigger OAuth flow if needed
            await self._connect_server(server)

            if server.health.status == ServerStatus.CONNECTED:
                logger.info(
                    "[BRIDGE] OAuth SSE reconnection successful for server '%s'",
                    server.name,
                )
                # Reset consecutive failures on successful reconnection
                server.health.consecutive_failures = 0
            else:
                logger.warning(
                    "[BRIDGE] OAuth SSE reconnection failed for server '%s'",
                    server.name,
                )

        except (ConnectionError, TimeoutError, OSError) as e:
            logger.warning("OAuth SSE reconnection network error: %s", type(e).__name__)
        except Exception:
            logger.exception("Unexpected OAuth SSE reconnection error for server '%s'", server.name)

    async def _perform_oauth_token_refresh(self) -> None:
        """Proactively refresh OAuth tokens before they expire."""
        current_time = time.time()

        for server in self.servers.values():
            if not self._is_oauth_endpoint(server):
                continue

            if not server.config.oauth_config:
                continue

            # Check if it's time to refresh the token
            last_refresh = self._oauth_token_refresh_times.get(server.name, 0)
            refresh_interval = server.config.oauth_config.token_refresh_interval / 1000.0

            if current_time - last_refresh >= refresh_interval:
                await self._refresh_oauth_token(server)
                self._oauth_token_refresh_times[server.name] = current_time

    def _has_existing_oauth_tokens(self, server: ManagedServer) -> bool:
        """Check if OAuth tokens already exist for the server."""
        if not server.config.is_oauth_enabled():
            return False

        try:
            # Get server URL for token lookup
            server_url = getattr(server.config, "url", None)
            if not server_url:
                return False

            # Check if tokens exist
            tokens = get_oauth_tokens(server_url, server.name)
            return tokens is not None and tokens.access_token is not None

        except Exception:
            # If there's any error checking tokens, assume they don't exist
            return False

    async def _refresh_oauth_token(self, server: ManagedServer) -> None:
        """Refresh OAuth token for a specific server."""
        with server_context(server.name):
            if not server.config.oauth_config or not server.config.oauth_config.enabled:
                return

            try:
                # Import OAuth components when needed to avoid circular dependencies
                from mcp_foxxy_bridge.oauth import get_oauth_client_config  # noqa: PLC0415
                from mcp_foxxy_bridge.oauth.oauth_flow import OAuthFlow  # noqa: PLC0415
                from mcp_foxxy_bridge.oauth.types import OAuthProviderOptions  # noqa: PLC0415

                # Get client config for OAuth
                client_config = get_oauth_client_config()

                # Create OAuth provider options
                oauth_options = OAuthProviderOptions(
                    server_url=server.config.url or "",
                    host="localhost",
                    callback_port=self.bridge_config.bridge.oauth_port if self.bridge_config.bridge else 8080,
                    callback_path="/oauth/callback",
                    client_name=client_config["client_name"],
                    client_uri=client_config["client_uri"],
                    software_id=client_config["software_id"],
                    software_version=client_config["software_version"],
                    server_name=server.name,
                    oauth_issuer=server.config.oauth_config.issuer,
                    verify_ssl=server.config.oauth_config.verify_ssl,
                )

                oauth_flow = OAuthFlow(oauth_options)

                # Check if we have existing tokens with refresh capability
                existing_tokens = oauth_flow.provider.tokens_including_expired()
                if not existing_tokens or not existing_tokens.refresh_token:
                    return

                # Attempt to refresh the token
                refreshed_tokens = oauth_flow.refresh_tokens(existing_tokens.refresh_token)

                if refreshed_tokens and refreshed_tokens.access_token:
                    logger.info("OAuth token successfully refreshed for server")
                    # Token is automatically saved by the OAuth flow
                else:
                    logger.warning("OAuth token refresh returned invalid tokens for server")

            except Exception as e:
                logger.warning(
                    "Failed to proactively refresh OAuth token for server: %s",
                    str(e),
                )
