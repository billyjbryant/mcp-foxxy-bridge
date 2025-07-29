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
from typing import Any

from mcp import types
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from pydantic import AnyUrl

from .config_loader import BridgeConfig, BridgeConfiguration, BridgeServerConfig

logger = logging.getLogger(__name__)


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
        self._shutdown_event = asyncio.Event()
        self._context_stack = contextlib.AsyncExitStack()
        self._restart_locks: dict[str, asyncio.Lock] = {}

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

            managed_server = ManagedServer(name=name, config=config)
            self.servers[name] = managed_server
            self._restart_locks[name] = asyncio.Lock()

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
        if any(
            server.config.health_check and server.config.health_check.enabled
            for server in self.servers.values()
        ):
            self.keep_alive_task = asyncio.create_task(self._keep_alive_loop())

        logger.info("Server manager started with %d active servers", len(self.get_active_servers()))

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

        # Close the context stack to cleanup all managed connections
        # This will gracefully terminate all child processes
        try:
            # Set a shorter timeout for cleanup to avoid hanging
            await asyncio.wait_for(self._context_stack.aclose(), timeout=1.0)
        except (TimeoutError, Exception) as e:
            logger.debug(
                "Context cleanup completed with exceptions (normal during shutdown): %s",
                type(e).__name__,
            )

        logger.info("Server manager stopped")

    async def _connect_server(self, server: ManagedServer) -> None:
        """Connect to a single MCP server."""
        logger.info(
            "Connecting to server '%s': %s %s",
            server.name,
            server.config.command,
            " ".join(server.config.args or []),
        )

        server.health.status = ServerStatus.CONNECTING

        try:
            # Create server parameters with modified environment for cleaner shutdown
            server_env = (server.config.env or {}).copy()
            # Add environment variable to help child processes handle shutdown gracefully
            server_env["MCP_BRIDGE_CHILD"] = "1"
            # Suppress traceback output during shutdown
            server_env["PYTHONPATH"] = server_env.get("PYTHONPATH", "")

            params = StdioServerParameters(
                command=server.config.command,
                args=server.config.args or [],
                env=server_env,
                cwd=None,
            )

            # Connect with timeout and manage lifetime with context stack
            async with asyncio.timeout(server.config.timeout):
                # Enter the stdio_client into the context stack to keep it alive
                read_stream, write_stream = await self._context_stack.enter_async_context(
                    stdio_client(params),
                )

                # Create session and manage its lifetime
                session = await self._context_stack.enter_async_context(
                    ClientSession(read_stream, write_stream),
                )
                server.session = session

                # Initialize the session
                result = await session.initialize()

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

                logger.info("Successfully connected to server '%s'", server.name)

        except Exception as e:
            logger.exception("Failed to connect to server '%s'", server.name)
            server.health.status = ServerStatus.FAILED
            server.health.failure_count += 1
            server.health.consecutive_failures += 1
            server.health.last_error = str(e)
            server.session = None

    async def _disconnect_server(self, server: ManagedServer) -> None:
        """Disconnect from a single MCP server."""
        logger.info("Disconnecting from server '%s'", server.name)

        # The context stack will handle the actual cleanup
        server.session = None
        server.health.status = ServerStatus.DISCONNECTED
        server.health.consecutive_failures = 0
        server.health.keep_alive_failures = 0
        server.tools.clear()
        server.resources.clear()
        server.prompts.clear()

    async def _load_server_capabilities(self, server: ManagedServer) -> None:
        """Load capabilities from a connected server."""
        if not server.session or not server.health.capabilities:
            return

        try:
            # Validate health check configuration against server capabilities
            if server.config.health_check:
                await self._validate_health_check_config(server)

            # Load tools
            if server.health.capabilities.tools:
                tools_result = await server.session.list_tools()
                server.tools = tools_result.tools
                logger.debug("Loaded %d tools from server '%s'", len(server.tools), server.name)

            # Load resources
            if server.health.capabilities.resources:
                resources_result = await server.session.list_resources()
                server.resources = resources_result.resources
                logger.debug(
                    "Loaded %d resources from server '%s'",
                    len(server.resources),
                    server.name,
                )

            # Load prompts
            if server.health.capabilities.prompts:
                prompts_result = await server.session.list_prompts()
                server.prompts = prompts_result.prompts
                logger.debug("Loaded %d prompts from server '%s'", len(server.prompts), server.name)

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
                "Server '%s' health check configured for 'call_tool' "
                "but server doesn't support tools",
                server.name,
            )
        elif hc.operation == "read_resource" and not caps.resources:
            logger.warning(
                "Server '%s' health check configured for 'read_resource' "
                "but server doesn't support resources",
                server.name,
            )
        elif hc.operation == "get_prompt" and not caps.prompts:
            logger.warning(
                "Server '%s' health check configured for 'get_prompt' "
                "but server doesn't support prompts",
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
            resource_exists = any(
                str(resource.uri) == hc.resource_uri for resource in server.resources
            )
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
                # Use the minimum keep-alive interval from all servers
                min_interval = min(
                    (
                        server.config.health_check.keep_alive_interval / 1000.0
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

    async def _perform_health_checks(self) -> None:
        """Perform health checks on all servers."""
        for server in self.servers.values():
            if server.health.status == ServerStatus.CONNECTED and server.session:
                try:
                    # Use configured health check operation
                    health_timeout = 5.0
                    if server.config.health_check:
                        health_timeout = server.config.health_check.timeout / 1000.0

                    await asyncio.wait_for(
                        self._execute_health_check_operation(server),
                        timeout=health_timeout,
                    )
                    server.health.last_seen = time.time()
                    server.health.consecutive_failures = 0  # Reset on successful check

                except Exception as e:
                    logger.warning("Health check failed for server '%s': %s", server.name, str(e))
                    server.health.failure_count += 1
                    server.health.consecutive_failures += 1
                    server.health.last_error = str(e)

                    # Check if server should be marked as failed
                    max_failures = 3  # Default
                    if self.bridge_config.bridge and self.bridge_config.bridge.failover:
                        max_failures = self.bridge_config.bridge.failover.max_failures
                    elif server.config.health_check:
                        max_failures = server.config.health_check.max_consecutive_failures

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
                            and server.health.restart_count
                            < server.config.health_check.max_restart_attempts
                        ):
                            # Start restart task and store reference to prevent GC
                            restart_task = asyncio.create_task(self._restart_server(server))
                            if not hasattr(self, "_restart_tasks"):
                                self._restart_tasks = set()
                            self._restart_tasks.add(restart_task)
                            restart_task.add_done_callback(self._restart_tasks.discard)

    def get_active_servers(self) -> list[ManagedServer]:
        """Get list of active (connected) servers."""
        return [
            server
            for server in self.servers.values()
            if server.health.status == ServerStatus.CONNECTED
        ]

    def get_server_by_name(self, name: str) -> ManagedServer | None:
        """Get a server by name."""
        return self.servers.get(name)

    def get_aggregated_tools(self) -> list[types.Tool]:
        """Get aggregated tools from all active servers."""
        tools = []
        seen_names = set()

        # Sort servers by priority (lower number = higher priority)
        active_servers = sorted(self.get_active_servers(), key=lambda s: s.config.priority)

        for server in active_servers:
            namespace = server.get_effective_namespace("tools", self.bridge_config.bridge)

            for tool in server.tools:
                tool_name = tool.name
                if namespace:
                    tool_name = f"{namespace}.{tool.name}"

                # Handle name conflicts based on configuration
                if tool_name in seen_names:
                    if (
                        self.bridge_config.bridge
                        and self.bridge_config.bridge.conflict_resolution == "error"
                    ):
                        msg = f"Tool name conflict: {tool_name}"
                        raise ValueError(msg)
                    if (
                        self.bridge_config.bridge
                        and self.bridge_config.bridge.conflict_resolution == "first"
                    ):
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

        return tools

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
                    resource_uri = f"{namespace}://{resource.uri!s}"

                # Handle URI conflicts
                if resource_uri in seen_uris:
                    if (
                        self.bridge_config.bridge
                        and self.bridge_config.bridge.conflict_resolution == "error"
                    ):
                        msg = f"Resource URI conflict: {resource_uri}"
                        raise ValueError(msg)
                    if (
                        self.bridge_config.bridge
                        and self.bridge_config.bridge.conflict_resolution == "first"
                    ):
                        continue

                # Create namespaced resource
                namespaced_resource = types.Resource(
                    uri=AnyUrl(resource_uri),
                    name=resource.name,
                    description=resource.description,
                    mimeType=resource.mimeType,
                )

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
                    prompt_name = f"{namespace}.{prompt.name}"

                # Handle name conflicts
                if prompt_name in seen_names:
                    if (
                        self.bridge_config.bridge
                        and self.bridge_config.bridge.conflict_resolution == "error"
                    ):
                        msg = f"Prompt name conflict: {prompt_name}"
                        raise ValueError(msg)
                    if (
                        self.bridge_config.bridge
                        and self.bridge_config.bridge.conflict_resolution == "first"
                    ):
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
        if "." in tool_name:
            namespace, actual_tool_name = tool_name.split(".", 1)
            # Find server that provides this namespaced tool
            server = None
            for s in self.get_active_servers():
                server_namespace = s.get_effective_namespace("tools", self.bridge_config.bridge)
                if server_namespace == namespace and any(
                    tool.name == actual_tool_name for tool in s.tools
                ):
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

        # Call the tool
        try:
            return await server.session.call_tool(actual_tool_name, arguments)
        except Exception:
            logger.exception(
                "Error calling tool '%s' on server '%s'",
                actual_tool_name,
                server.name,
            )
            raise

    async def read_resource(self, resource_uri: str) -> types.ReadResourceResult:
        """Read a resource by URI, routing to the appropriate server."""
        # Parse namespace from URI
        if "://" in resource_uri:
            namespace, actual_uri = resource_uri.split("://", 1)
            # Find server that provides this namespaced resource
            server = None
            for s in self.get_active_servers():
                server_namespace = s.get_effective_namespace("resources", self.bridge_config.bridge)
                if server_namespace == namespace and any(
                    resource.uri == actual_uri for resource in s.resources
                ):
                    server = s
                    break
        else:
            # No namespace, find first server with this resource
            server = None
            actual_uri = resource_uri
            for s in self.get_active_servers():
                if any(resource.uri == actual_uri for resource in s.resources):
                    server = s
                    break

        if not server or not server.session:
            msg = f"No active server found for resource: {resource_uri}"
            raise ValueError(msg)

        # Call the resource
        try:
            return await server.session.read_resource(AnyUrl(actual_uri))
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
        if "." in prompt_name:
            namespace, actual_prompt_name = prompt_name.split(".", 1)
            # Find server that provides this namespaced prompt
            server = None
            for s in self.get_active_servers():
                server_namespace = s.get_effective_namespace("prompts", self.bridge_config.bridge)
                if server_namespace == namespace and any(
                    prompt.name == actual_prompt_name for prompt in s.prompts
                ):
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
                    "health_check_enabled": server.config.health_check.enabled
                    if server.config.health_check
                    else False,
                    "health_check_operation": server.config.health_check.operation
                    if server.config.health_check
                    else "list_tools",
                    "auto_restart": server.config.health_check.auto_restart
                    if server.config.health_check
                    else False,
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
                server_namespace = server.get_effective_namespace(
                    "resources", self.bridge_config.bridge
                )
                if server_namespace == namespace and any(
                    resource.uri == actual_uri for resource in server.resources
                ):
                    if server.session:
                        try:
                            await server.session.subscribe_resource(AnyUrl(actual_uri))
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
                if (
                    any(resource.uri == actual_uri for resource in server.resources)
                    and server.session
                ):
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
                server_namespace = server.get_effective_namespace(
                    "resources", self.bridge_config.bridge
                )
                if server_namespace == namespace and any(
                    resource.uri == actual_uri for resource in server.resources
                ):
                    if server.session:
                        try:
                            await server.session.unsubscribe_resource(AnyUrl(actual_uri))
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
                if (
                    any(resource.uri == actual_uri for resource in server.resources)
                    and server.session
                ):
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
                    logger.debug("Set logging level to %s on server '%s'", level, server.name)
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

            # Check if it's time for a keep-alive ping
            time_since_last_keep_alive = current_time - server.health.last_keep_alive
            keep_alive_interval = server.config.health_check.keep_alive_interval / 1000.0

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
            logger.debug("Keep-alive successful for server '%s'", server.name)

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
                    and server.health.restart_count
                    < server.config.health_check.max_restart_attempts
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
                server.config.health_check.max_restart_attempts
                if server.config.health_check
                else 5,
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
                    logger.info("Successfully restarted server '%s'", server.name)  # type: ignore[unreachable]
                else:
                    logger.error("Failed to restart server '%s'", server.name)

            except Exception as e:
                logger.exception("Error during server restart for '%s'", server.name)
                server.health.last_error = f"Restart failed: {e!s}"

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

                await session.read_resource(AnyUrl(server.config.health_check.resource_uri))

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
                    "Unknown health check operation '%s' for server '%s', "
                    "falling back to list_tools",
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
