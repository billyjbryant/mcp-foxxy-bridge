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
        self._shutdown_event = asyncio.Event()
        self._context_stack = contextlib.AsyncExitStack()

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

        # Start health check task
        if (
            self.bridge_config.bridge
            and self.bridge_config.bridge.failover
            and self.bridge_config.bridge.failover.enabled
        ):
            self.health_check_task = asyncio.create_task(self._health_check_loop())

        logger.info("Server manager started with %d active servers", len(self.get_active_servers()))

    async def stop(self) -> None:
        """Stop the server manager and disconnect from all servers."""
        logger.info("Stopping server manager gracefully...")

        # Signal shutdown
        self._shutdown_event.set()

        # Cancel health check task
        if self.health_check_task:
            self.health_check_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.health_check_task

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
                server.health.last_error = None
                server.health.capabilities = result.capabilities

                # Load capabilities
                await self._load_server_capabilities(server)

                logger.info("Successfully connected to server '%s'", server.name)

        except Exception as e:
            logger.exception("Failed to connect to server '%s'", server.name)
            server.health.status = ServerStatus.FAILED
            server.health.failure_count += 1
            server.health.last_error = str(e)
            server.session = None

    async def _disconnect_server(self, server: ManagedServer) -> None:
        """Disconnect from a single MCP server."""
        logger.info("Disconnecting from server '%s'", server.name)

        # The context stack will handle the actual cleanup
        server.session = None
        server.health.status = ServerStatus.DISCONNECTED
        server.tools.clear()
        server.resources.clear()
        server.prompts.clear()

    async def _load_server_capabilities(self, server: ManagedServer) -> None:
        """Load capabilities from a connected server."""
        if not server.session or not server.health.capabilities:
            return

        try:
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

    async def _perform_health_checks(self) -> None:
        """Perform health checks on all servers."""
        for server in self.servers.values():
            if server.health.status == ServerStatus.CONNECTED and server.session:
                try:
                    # Simple ping to check if server is responsive
                    await asyncio.wait_for(
                        server.session.list_tools(),
                        timeout=5.0,
                    )
                    server.health.last_seen = time.time()

                except Exception as e:
                    logger.warning("Health check failed for server '%s': %s", server.name, str(e))
                    server.health.failure_count += 1
                    server.health.last_error = str(e)

                    # Check if server should be marked as failed
                    if (
                        self.bridge_config.bridge
                        and self.bridge_config.bridge.failover
                        and server.health.failure_count
                        >= self.bridge_config.bridge.failover.max_failures
                    ):
                        logger.exception(
                            "Server '%s' marked as failed after %d failures",
                            server.name,
                            server.health.failure_count,
                        )
                        server.health.status = ServerStatus.FAILED
                        await self._disconnect_server(server)

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
                "config": {
                    "enabled": server.config.enabled,
                    "command": server.config.command,
                    "args": server.config.args,
                    "priority": server.config.priority,
                    "tags": server.config.tags,
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
