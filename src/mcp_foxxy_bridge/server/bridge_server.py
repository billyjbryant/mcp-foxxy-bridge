#
# MCP Foxxy Bridge - Bridge Server
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
"""Create an MCP server that bridges multiple MCP servers.

This server aggregates capabilities from multiple MCP servers and provides
a unified interface for AI tools to interact with all of them.
"""

import asyncio
import logging
import time
from typing import Any, Protocol

from mcp import server, types
from mcp.shared.exceptions import McpError
from pydantic import BaseModel

from mcp_foxxy_bridge.config.config_loader import BridgeConfiguration, BridgeServerConfig
from mcp_foxxy_bridge.utils.logging import get_logger

from .server_manager import ServerManager

logger = get_logger(__name__, facility="BRIDGE")


class ServerManagerProtocol(Protocol):
    """Protocol for server manager interface used by bridge server."""

    capability_change_notifier: Any
    bridge_config: Any

    def get_active_servers(self) -> list[Any]:
        """Get list of currently active servers."""
        ...

    def get_aggregated_tools(self) -> list[types.Tool]:
        """Get aggregated tools from all active servers."""
        ...

    def get_aggregated_resources(self) -> list[types.Resource]:
        """Get aggregated resources from all active servers."""
        ...

    def get_aggregated_prompts(self) -> list[types.Prompt]:
        """Get aggregated prompts from all active servers."""
        ...

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        """Call a tool on the appropriate server."""
        ...

    async def read_resource(self, uri: str) -> types.ReadResourceResult:
        """Read a resource from the appropriate server."""
        ...

    async def get_prompt(self, name: str, arguments: dict[str, Any] | None = None) -> types.GetPromptResult:
        """Get a prompt from the appropriate server."""
        ...

    async def set_logging_level(self, level: types.LoggingLevel) -> None:
        """Set logging level on all servers."""
        ...

    async def get_completions(
        self, ref: types.ResourceReference | types.PromptReference, argument: types.CompletionArgument
    ) -> list[str]:
        """Get completions for a resource or prompt."""
        ...

    async def subscribe_resource(self, uri: str) -> None:
        """Subscribe to resource updates."""
        ...

    async def unsubscribe_resource(self, uri: str) -> None:
        """Unsubscribe from resource updates."""
        ...


# Registry to store server manager instances for proper cleanup
_server_manager_registry: dict[Any, ServerManager] = {}


# Custom notification types for capability changes
class CapabilitiesChangedParams(BaseModel):
    """Parameters for capabilities changed notification."""

    tools_added: list[str] = []
    tools_removed: list[str] = []
    resources_added: list[str] = []
    resources_removed: list[str] = []
    prompts_added: list[str] = []
    prompts_removed: list[str] = []
    message: str = "Server capabilities have changed"


class CapabilitiesChangedNotification(BaseModel):
    """Notification sent when server capabilities change."""

    method: str = "notifications/capabilities_changed"
    params: CapabilitiesChangedParams


# Store connected clients for capability change notifications
_connected_clients: set[Any] = set()


def _configure_prompts_capability(
    app: server.Server[object],
    server_manager: ServerManagerProtocol,
) -> None:
    """Configure prompts capability for the bridge server."""
    logger.debug("Configuring prompts aggregation...")

    async def _list_prompts(_: types.ListPromptsRequest) -> types.ServerResult:
        try:
            prompts = server_manager.get_aggregated_prompts()
            result = types.ListPromptsResult(prompts=prompts)
            return types.ServerResult(result)
        except Exception:
            logger.exception("Error listing prompts")
            return types.ServerResult(types.ListPromptsResult(prompts=[]))

    app.request_handlers[types.ListPromptsRequest] = _list_prompts

    async def _get_prompt(req: types.GetPromptRequest) -> types.ServerResult:
        try:
            result = await server_manager.get_prompt(
                req.params.name,
                req.params.arguments,
            )
            return types.ServerResult(result)
        except McpError as e:
            # Re-raise MCP errors so they're properly returned to the client
            logger.warning("MCP error getting prompt '%s': %s", req.params.name, e.error.message)
            raise
        except Exception:
            logger.exception("Error getting prompt '%s'", req.params.name)
            return types.ServerResult(
                types.GetPromptResult(
                    description=f"Error retrieving prompt: {req.params.name}",
                    messages=[
                        types.PromptMessage(
                            role="user",
                            content=types.TextContent(
                                type="text",
                                text="Error occurred while retrieving prompt",
                            ),
                        ),
                    ],
                ),
            )

    app.request_handlers[types.GetPromptRequest] = _get_prompt


def _configure_resources_capability(
    app: server.Server[object],
    server_manager: ServerManagerProtocol,
) -> None:
    """Configure resources capability for the bridge server."""
    logger.debug("Configuring resources aggregation...")

    async def _list_resources(_: types.ListResourcesRequest) -> types.ServerResult:
        try:
            resources = server_manager.get_aggregated_resources()
            result = types.ListResourcesResult(resources=resources)
            return types.ServerResult(result)
        except Exception:
            logger.exception("Error listing resources")
            return types.ServerResult(types.ListResourcesResult(resources=[]))

    app.request_handlers[types.ListResourcesRequest] = _list_resources

    async def _list_resource_templates(
        _: types.ListResourceTemplatesRequest,
    ) -> types.ServerResult:
        # For now, return empty templates as we don't aggregate templates yet
        result = types.ListResourceTemplatesResult(resourceTemplates=[])
        return types.ServerResult(result)

    app.request_handlers[types.ListResourceTemplatesRequest] = _list_resource_templates

    async def _read_resource(req: types.ReadResourceRequest) -> types.ServerResult:
        try:
            result = await server_manager.read_resource(str(req.params.uri))
            return types.ServerResult(result)
        except McpError as e:
            # Re-raise MCP errors so they're properly returned to the client
            logger.warning("MCP error reading resource '%s': %s", req.params.uri, e.error.message)
            raise
        except Exception:
            logger.exception("Error reading resource '%s'", req.params.uri)
            return types.ServerResult(
                types.ReadResourceResult(
                    contents=[
                        types.TextResourceContents(
                            uri=req.params.uri,
                            mimeType="text/plain",
                            text="Error occurred while reading resource",
                        ),
                    ],
                ),
            )

    app.request_handlers[types.ReadResourceRequest] = _read_resource

    async def _subscribe_resource(req: types.SubscribeRequest) -> types.ServerResult:
        try:
            await server_manager.subscribe_resource(str(req.params.uri))
            logger.debug("Successfully subscribed to resource: %s", req.params.uri)
            return types.ServerResult(types.EmptyResult())
        except Exception:
            logger.exception("Error subscribing to resource: %s", req.params.uri)
            return types.ServerResult(types.EmptyResult())

    app.request_handlers[types.SubscribeRequest] = _subscribe_resource

    async def _unsubscribe_resource(
        req: types.UnsubscribeRequest,
    ) -> types.ServerResult:
        try:
            await server_manager.unsubscribe_resource(str(req.params.uri))
            logger.debug("Successfully unsubscribed from resource: %s", req.params.uri)
            return types.ServerResult(types.EmptyResult())
        except Exception:
            logger.exception("Error unsubscribing from resource: %s", req.params.uri)
            return types.ServerResult(types.EmptyResult())

    app.request_handlers[types.UnsubscribeRequest] = _unsubscribe_resource


def _configure_tools_capability(
    app: server.Server[object],
    server_manager: ServerManagerProtocol,
) -> None:
    """Configure tools capability for the bridge server."""
    logger.debug("Configuring tools aggregation...")

    async def _list_tools(_: types.ListToolsRequest) -> types.ServerResult:
        try:
            logger.debug("Listing tools from server manager")

            # Get active servers first to diagnose
            active_servers = server_manager.get_active_servers()
            logger.debug("Active servers for tool listing: %d", len(active_servers))
            for server in active_servers:
                logger.debug("Active server: '%s' with %d tools", server.name, len(server.tools))

            tools = server_manager.get_aggregated_tools()
            logger.info("Found %d aggregated tools total", len(tools))

            if len(tools) == 0:
                logger.warning("No tools available from any servers")
                if len(active_servers) == 0:
                    logger.error("No active servers available")
                else:
                    logger.warning("Active servers exist but no tools aggregated")
            else:
                for tool in tools:
                    logger.debug("Aggregated tool: %s", tool.name)

            result = types.ListToolsResult(tools=tools)
            return types.ServerResult(result)
        except Exception:
            logger.exception("Error listing tools")
            return types.ServerResult(types.ListToolsResult(tools=[]))

    app.request_handlers[types.ListToolsRequest] = _list_tools

    async def _call_tool(req: types.CallToolRequest) -> types.ServerResult:
        tool_start_time = time.time()
        try:
            logger.debug("Calling tool '%s'", req.params.name)
            result = await server_manager.call_tool(
                req.params.name,
                req.params.arguments or {},
            )
            elapsed = time.time() - tool_start_time
            logger.debug("Tool '%s' completed in %.3f seconds", req.params.name, elapsed)
            return types.ServerResult(result)
        except TimeoutError:
            elapsed = time.time() - tool_start_time
            logger.exception("Tool '%s' timed out after %.3f seconds", req.params.name, elapsed)
            raise
        except McpError as e:
            elapsed = time.time() - tool_start_time
            logger.warning(
                "MCP error calling tool '%s' after %.3f seconds: %s", req.params.name, elapsed, e.error.message
            )
            raise
        except Exception:
            elapsed = time.time() - tool_start_time
            logger.exception("Error calling tool '%s' after %.3f seconds", req.params.name, elapsed)
            return types.ServerResult(
                types.CallToolResult(
                    content=[
                        types.TextContent(
                            type="text",
                            text=f"Error occurred while calling tool: {req.params.name}",
                        ),
                    ],
                ),
            )

    app.request_handlers[types.CallToolRequest] = _call_tool


def _configure_logging_capability(
    app: server.Server[object],
    server_manager: ServerManagerProtocol,
) -> None:
    """Configure logging capability for the bridge server."""

    async def _set_logging_level(req: types.SetLevelRequest) -> types.ServerResult:
        try:
            level = req.params.level
            bridge_logger = logging.getLogger("mcp_foxxy_bridge")
            level_str = str(level).lower()

            if level_str == "debug":
                bridge_logger.setLevel(logging.DEBUG)
            elif level_str == "info":
                bridge_logger.setLevel(logging.INFO)
            elif level_str == "warning":
                bridge_logger.setLevel(logging.WARNING)
            elif level_str == "error":
                bridge_logger.setLevel(logging.ERROR)

            # Forward logging level to all managed servers
            await server_manager.set_logging_level(level)

            logger.info(
                "Set logging level to %s",
                str(level),
            )
            return types.ServerResult(types.EmptyResult())
        except Exception:
            logger.exception("Error setting logging level")
            return types.ServerResult(types.EmptyResult())

    app.request_handlers[types.SetLevelRequest] = _set_logging_level


def _configure_notifications_and_completion(
    app: server.Server[object],
    server_manager: ServerManagerProtocol,
) -> None:
    """Configure progress notifications and completion for the bridge server."""

    # Add progress notification handler
    async def _send_progress_notification(req: types.ProgressNotification) -> None:
        logger.debug("Progress notification: %s/%s", req.params.progress, req.params.total)
        # Bridge typically receives progress notifications from managed servers
        # and relays them to clients transparently. The MCP framework handles
        # the actual forwarding to connected clients automatically.

        # Log the progress for debugging purposes
        if req.params.total and req.params.total > 0:
            percentage = (req.params.progress / req.params.total) * 100
            logger.info(
                "Progress update: %.1f%% (%s/%s)",
                percentage,
                req.params.progress,
                req.params.total,
            )
        else:
            logger.info("Progress update: %s", req.params.progress)

    app.notification_handlers[types.ProgressNotification] = _send_progress_notification

    # Add capability change notification handler
    async def _send_capability_change_notification(notification_data: dict[str, Any]) -> None:
        """Send capability change notification to all connected clients."""
        try:
            # Create notification params
            params = CapabilitiesChangedParams(**notification_data)

            # Create a custom notification using the MCP types system
            # We'll use a generic notification structure that MCP supports
            _ = types.JSONRPCNotification(
                jsonrpc="2.0",
                method="notifications/capabilities_changed",
                params=params.model_dump(),
            )

            # The MCP framework should handle sending this to all connected clients
            # For now, we'll log the notification
            logger.info(
                "Capability change notification: %d tools added, %d removed, "
                "%d resources added, %d removed, %d prompts added, %d removed",
                len(params.tools_added),
                len(params.tools_removed),
                len(params.resources_added),
                len(params.resources_removed),
                len(params.prompts_added),
                len(params.prompts_removed),
            )

            # Note: The actual client notification sending needs to be done through
            # the MCP server framework's session management system

        except Exception:
            logger.exception("Error sending capability change notification")

    # Store the notification sender in the server manager for use during updates
    server_manager.capability_change_notifier = _send_capability_change_notification

    # Add completion handler
    async def _complete(req: types.CompleteRequest) -> types.ServerResult:
        try:
            # Aggregate completions from all managed servers
            completions = await server_manager.get_completions(
                req.params.ref,
                req.params.argument,
            )

            result = types.CompleteResult(completion=types.Completion(values=completions))
            logger.debug("Returning %d aggregated completions", len(completions))
            return types.ServerResult(result)
        except Exception:
            logger.exception("Error handling completion")
            return types.ServerResult(types.CompleteResult(completion=types.Completion(values=[])))

    app.request_handlers[types.CompleteRequest] = _complete


async def create_bridge_server(
    bridge_config: BridgeConfiguration,
) -> server.Server[object]:
    """Create a bridge server that aggregates multiple MCP servers.

    Args:
        bridge_config: Configuration for the bridge and all MCP servers.

    Returns:
        A configured MCP server that bridges to multiple backends.
    """
    logger.info("Creating bridge server with %d configured servers", len(bridge_config.servers))

    # Create the server manager without starting it yet
    server_manager = ServerManager(bridge_config)

    # Create the bridge server first
    bridge_name = "MCP Foxxy Bridge"
    app: server.Server[object] = server.Server(name=bridge_name)

    # Store server manager for cleanup using registry
    _server_manager_registry[id(app)] = server_manager

    # Configure capabilities based on aggregation settings
    if bridge_config.bridge and bridge_config.bridge.aggregation and bridge_config.bridge.aggregation.prompts:
        _configure_prompts_capability(app, server_manager)

    if bridge_config.bridge and bridge_config.bridge.aggregation and bridge_config.bridge.aggregation.resources:
        _configure_resources_capability(app, server_manager)

    if bridge_config.bridge and bridge_config.bridge.aggregation and bridge_config.bridge.aggregation.tools:
        _configure_tools_capability(app, server_manager)

    # Add logging capability
    logger.debug("Configuring logging...")
    _configure_logging_capability(app, server_manager)

    # Add notifications and completion capabilities
    _configure_notifications_and_completion(app, server_manager)

    # Start server manager asynchronously in the background
    # This allows the bridge server to start immediately without waiting for all servers
    start_task = asyncio.create_task(server_manager.start())
    # Store task reference to prevent garbage collection
    if not hasattr(app, "background_tasks"):
        app.background_tasks = set()  # type: ignore[attr-defined]
    app.background_tasks.add(start_task)  # type: ignore[attr-defined]
    start_task.add_done_callback(app.background_tasks.discard)  # type: ignore[attr-defined]

    logger.info("Bridge server created successfully, servers connecting in background...")

    return app


async def shutdown_bridge_server(app: server.Server[object]) -> None:
    """Shutdown the bridge server and clean up resources.

    Args:
        app: The bridge server to shutdown.
    """
    logger.info("Shutting down bridge server...")

    # Stop the server manager if it exists in registry
    app_id = id(app)
    if app_id in _server_manager_registry:
        server_manager = _server_manager_registry.pop(app_id)
        if server_manager:
            await server_manager.stop()

    logger.info("Bridge server shutdown complete")


async def create_tag_filtered_bridge(
    servers: dict[str, BridgeServerConfig],
    tags: list[str],
    tag_mode: str = "intersection",
    bridge_name_suffix: str = "",
) -> server.Server[object]:
    """Create a bridge server with servers filtered by tags.

    Args:
        servers: Dictionary of all available servers
        tags: List of tags to filter by
        tag_mode: "intersection" (servers must have ALL tags) or "union" (servers must have ANY tag)
        bridge_name_suffix: Optional suffix for the bridge name (e.g., tag names)

    Returns:
        A configured MCP server that bridges to tag-filtered servers
    """

    def matches_tag_filter(server_config: BridgeServerConfig) -> bool:
        if not server_config.tags:
            return False

        server_tags = set(server_config.tags)
        filter_tags = set(tags)

        if tag_mode == "intersection":
            return filter_tags.issubset(server_tags)
        if tag_mode == "union":
            return bool(filter_tags.intersection(server_tags))
        return False

    # Filter servers by tag criteria
    filtered_servers = {
        name: config for name, config in servers.items() if config.enabled and matches_tag_filter(config)
    }

    logger.info(
        "Creating tag-filtered bridge for tags %s (%s mode) - %d servers match",
        tags,
        tag_mode,
        len(filtered_servers),
    )

    if not filtered_servers:
        logger.warning("No servers match the tag filter: %s (%s)", tags, tag_mode)

    # Create bridge configuration with filtered servers
    tag_bridge_config = BridgeConfiguration(
        servers=filtered_servers,
        bridge=None,  # Use default bridge config
    )

    # Create server manager with filtered servers
    server_manager = ServerManager(tag_bridge_config)
    await server_manager.start()

    # Create the bridge server
    tag_display = "+".join(tags) if tag_mode == "intersection" else ",".join(tags)
    bridge_name = f"MCP Foxxy Bridge - Tags: {tag_display}{bridge_name_suffix}"
    app: server.Server[object] = server.Server(name=bridge_name)

    # Store server manager for cleanup
    _server_manager_registry[id(app)] = server_manager

    # Configure capabilities with aggregation (since we may have multiple servers)
    # Use default aggregation settings - tools, resources, and prompts enabled
    _configure_prompts_capability(app, server_manager)
    _configure_resources_capability(app, server_manager)
    _configure_tools_capability(app, server_manager)
    _configure_logging_capability(app, server_manager)
    _configure_notifications_and_completion(app, server_manager)

    active_servers = server_manager.get_active_servers()
    logger.info(
        "Tag-filtered bridge created successfully for tags %s - %d active servers",
        tags,
        len(active_servers),
    )

    return app


async def create_server_filtered_bridge(
    servers: dict[str, BridgeServerConfig],
    server_name: str,
    bridge_name_suffix: str = "",
) -> server.Server[object]:
    """Create a bridge server with a single server filtered by name.

    This creates a filtered view of servers containing only the specified server,
    allowing individual server access while maintaining connection to the main
    server registry for proper tool aggregation.

    Args:
        servers: Dictionary of all available servers
        server_name: Name of the server to include
        bridge_name_suffix: Optional suffix for the bridge name

    Returns:
        Bridge server instance filtered to the specified server
    """
    # Filter servers to include only the specified server
    filtered_servers = {name: config for name, config in servers.items() if name == server_name and config.enabled}

    if not filtered_servers:
        logger.warning("No enabled server found for filtered bridge")
        # Create empty bridge to avoid errors
        filtered_servers = {}

    bridge_name = f"mcp-foxxy-bridge-server-{server_name.lower()}"
    if bridge_name_suffix:
        bridge_name += f"-{bridge_name_suffix}"

    logger.info(f"Creating server-filtered bridge '{bridge_name}' with {len(filtered_servers)} server(s)")

    # Create filtered configuration
    filtered_config = BridgeConfiguration(
        servers=filtered_servers,
        bridge=None,  # Use default bridge config
    )

    return await create_bridge_server(filtered_config)


class FilteredServerManager:
    """Wrapper around ServerManager that filters results based on criteria."""

    def __init__(self, main_server_manager: ServerManagerProtocol, filter_criteria: dict[str, Any]) -> None:
        self.main_server_manager = main_server_manager
        self.filter_criteria = filter_criteria
        self.capability_change_notifier = None  # Will be set by bridge server
        self.bridge_config = main_server_manager.bridge_config  # Delegate bridge_config

    def _should_include_server(self, server_info: Any) -> bool:
        """Check if a server should be included based on filter criteria."""
        filter_type = self.filter_criteria.get("type")

        if filter_type == "server_name":
            # Include only servers matching the specified name
            target_name = self.filter_criteria.get("server_name")
            if target_name and hasattr(server_info, "config") and hasattr(server_info.config, "name"):
                return bool(server_info.config.name == target_name)
            return False

        if filter_type == "tags":
            # Include servers matching tag criteria
            tags = self.filter_criteria.get("tags", [])
            tag_mode = self.filter_criteria.get("tag_mode", "union")

            if not server_info.config.tags:
                return False

            server_tags = set(server_info.config.tags)
            filter_tags = set(tags)

            if tag_mode == "intersection":
                return filter_tags.issubset(server_tags)
            if tag_mode == "union":
                return bool(filter_tags.intersection(server_tags))

        return True

    def get_active_servers(self) -> list[Any]:
        """Get filtered active servers."""
        all_servers = self.main_server_manager.get_active_servers()
        return [server for server in all_servers if self._should_include_server(server)]

    def get_aggregated_tools(self) -> list[types.Tool]:
        """Get tools from filtered servers only."""
        tools = []
        seen_names = set()

        # Get filtered active servers
        active_servers = sorted(self.get_active_servers(), key=lambda s: s.config.priority)

        for mcp_server in active_servers:
            namespace = mcp_server.get_effective_namespace("tools", self.main_server_manager.bridge_config.bridge)

            for tool in mcp_server.tools:
                tool_name = tool.name
                if namespace:
                    tool_name = f"{namespace}__{tool.name}"

                # Handle name conflicts
                if tool_name in seen_names:
                    bridge_config = self.main_server_manager.bridge_config.bridge
                    if bridge_config and bridge_config.conflict_resolution == "error":
                        msg = f"Tool name conflict: {tool_name}"
                        raise ValueError(msg)
                    if bridge_config and bridge_config.conflict_resolution == "first":
                        continue

                # Create tool with potentially namespaced name
                filtered_tool = tool.model_copy()
                filtered_tool.name = tool_name
                tools.append(filtered_tool)
                seen_names.add(tool_name)

        return tools

    def get_aggregated_resources(self) -> list[types.Resource]:
        """Get resources from filtered servers only."""
        resources = []
        seen_uris = set()

        active_servers = sorted(self.get_active_servers(), key=lambda s: s.config.priority)

        for mcp_server in active_servers:
            namespace = mcp_server.get_effective_namespace("resources", self.main_server_manager.bridge_config.bridge)

            for resource in mcp_server.resources:
                resource_uri = str(resource.uri)
                if namespace:
                    resource_uri = f"{namespace}://{resource.uri}"

                if resource_uri in seen_uris:
                    bridge_config = self.main_server_manager.bridge_config.bridge
                    if bridge_config and bridge_config.conflict_resolution == "error":
                        msg = f"Resource URI conflict: {resource_uri}"
                        raise ValueError(msg)
                    if bridge_config and bridge_config.conflict_resolution == "first":
                        continue

                filtered_resource = resource.model_copy()
                filtered_resource.uri = resource_uri
                resources.append(filtered_resource)
                seen_uris.add(resource_uri)

        return resources

    def get_aggregated_prompts(self) -> list[types.Prompt]:
        """Get prompts from filtered servers only."""
        prompts = []
        seen_names = set()

        active_servers = sorted(self.get_active_servers(), key=lambda s: s.config.priority)

        for mcp_server in active_servers:
            namespace = mcp_server.get_effective_namespace("prompts", self.main_server_manager.bridge_config.bridge)

            for prompt in mcp_server.prompts:
                prompt_name = prompt.name
                if namespace:
                    prompt_name = f"{namespace}__{prompt.name}"

                if prompt_name in seen_names:
                    bridge_config = self.main_server_manager.bridge_config.bridge
                    if bridge_config and bridge_config.conflict_resolution == "error":
                        msg = f"Prompt name conflict: {prompt_name}"
                        raise ValueError(msg)
                    if bridge_config and bridge_config.conflict_resolution == "first":
                        continue

                filtered_prompt = prompt.model_copy()
                filtered_prompt.name = prompt_name
                prompts.append(filtered_prompt)
                seen_names.add(prompt_name)

        return prompts

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        """Delegate tool calls to main server manager."""
        return await self.main_server_manager.call_tool(name, arguments)

    async def read_resource(self, uri: str) -> types.ReadResourceResult:
        """Delegate resource reads to main server manager."""
        return await self.main_server_manager.read_resource(uri)

    async def get_prompt(self, name: str, arguments: dict[str, Any] | None = None) -> types.GetPromptResult:
        """Delegate prompt requests to main server manager."""
        return await self.main_server_manager.get_prompt(name, arguments)

    async def set_logging_level(self, level: types.LoggingLevel) -> None:
        """Delegate logging level changes to main server manager."""
        await self.main_server_manager.set_logging_level(level)

    async def get_completions(
        self, ref: types.ResourceReference | types.PromptReference, argument: types.CompletionArgument
    ) -> list[str]:
        """Delegate completions to main server manager."""
        return await self.main_server_manager.get_completions(ref, argument)

    async def subscribe_resource(self, uri: str) -> None:
        """Delegate resource subscriptions to main server manager."""
        await self.main_server_manager.subscribe_resource(uri)

    async def unsubscribe_resource(self, uri: str) -> None:
        """Delegate resource unsubscriptions to main server manager."""
        await self.main_server_manager.unsubscribe_resource(uri)


async def create_server_filtered_bridge_view(
    servers: dict[str, BridgeServerConfig],
    server_name: str,
    main_bridge_server: server.Server[object] | None = None,
) -> server.Server[object]:
    """Create a filtered view showing only tools from a specific server."""
    if main_bridge_server is not None:
        # Get the main server manager from the registry
        main_server_manager = _server_manager_registry.get(id(main_bridge_server))
        if main_server_manager:
            # Create filtered server manager
            filter_criteria = {"type": "server_name", "server_name": server_name}
            filtered_manager = FilteredServerManager(main_server_manager, filter_criteria)

            # Create a new bridge server with the filtered manager
            bridge_name = f"MCP Foxxy Bridge - {server_name}"
            app: server.Server[object] = server.Server(name=bridge_name)

            # Configure capabilities with filtered manager
            _configure_prompts_capability(app, filtered_manager)
            _configure_resources_capability(app, filtered_manager)
            _configure_tools_capability(app, filtered_manager)
            _configure_logging_capability(app, filtered_manager)
            _configure_notifications_and_completion(app, filtered_manager)

            logger.debug("Created server-filtered bridge view")
            return app

    # Fallback to creating a separate instance
    return await create_single_server_bridge(server_name, servers[server_name])


async def create_tag_filtered_bridge_view(
    servers: dict[str, BridgeServerConfig],
    tags: list[str],
    tag_mode: str = "intersection",
    main_bridge_server: server.Server[object] | None = None,
) -> server.Server[object]:
    """Create a filtered view of the main bridge server showing only tag-filtered servers.

    This creates a view that filters tools/resources/prompts to only show those from
    servers that match the specified tag criteria, using the shared server instances
    from the main bridge.

    Args:
        servers: Dictionary of all available servers
        tags: List of tags to filter by
        tag_mode: "intersection" (servers must have ALL tags) or "union" (servers must have ANY tag)
        main_bridge_server: The main bridge server instance to create a filtered view of

    Returns:
        Bridge server instance filtered to the specified tag criteria
    """
    if main_bridge_server is not None:
        # Get the main server manager from the registry
        main_server_manager = _server_manager_registry.get(id(main_bridge_server))
        if main_server_manager:
            # Create filtered server manager
            filter_criteria = {"type": "tags", "tags": tags, "tag_mode": tag_mode}
            filtered_manager = FilteredServerManager(main_server_manager, filter_criteria)

            # Create a new bridge server with the filtered manager
            tag_display = "+".join(tags) if tag_mode == "intersection" else ",".join(tags)
            bridge_name = f"MCP Foxxy Bridge - Tags: {tag_display}"
            app: server.Server[object] = server.Server(name=bridge_name)

            # Configure capabilities with filtered manager
            _configure_prompts_capability(app, filtered_manager)
            _configure_resources_capability(app, filtered_manager)
            _configure_tools_capability(app, filtered_manager)
            _configure_logging_capability(app, filtered_manager)
            _configure_notifications_and_completion(app, filtered_manager)

            logger.debug(
                "Created tag-filtered bridge view for tags: %s (%s mode)",
                tags,
                tag_mode,
            )
            return app

    # Fallback to creating a separate instance (legacy approach)
    return await create_tag_filtered_bridge(servers, tags, tag_mode)


async def create_single_server_bridge(server_name: str, server_config: BridgeServerConfig) -> server.Server[object]:
    """Create a bridge server that exposes only a single MCP server.

    This creates an MCP server instance that connects to only one backend server,
    without any aggregation or namespacing. Tools, resources, and prompts are
    exposed directly with their original names.

    Args:
        server_name: The name of the server (for logging/identification)
        server_config: Configuration for the single MCP server

    Returns:
        A configured MCP server that bridges to a single backend server
    """
    logger.info("Creating single-server bridge")

    # Create a minimal bridge configuration with just this one server
    single_server_config = BridgeConfiguration(
        servers={server_name: server_config},
        bridge=None,  # Use default bridge config
    )

    # Create a server manager with just this one server
    server_manager = ServerManager(single_server_config)
    await server_manager.start()

    # Create the bridge server
    bridge_name = f"MCP Foxxy Bridge - {server_name}"
    app: server.Server[object] = server.Server(name=bridge_name)

    # Store server manager for cleanup
    _server_manager_registry[id(app)] = server_manager

    # For single server bridges, we want to expose capabilities directly
    # without namespacing, so we configure all capabilities regardless of
    # aggregation settings (there's no aggregation conflict with one server)

    # Configure all capabilities (no aggregation conflicts with single server)
    _configure_prompts_capability(app, server_manager)
    _configure_resources_capability(app, server_manager)
    _configure_tools_capability(app, server_manager)
    _configure_logging_capability(app, server_manager)
    _configure_notifications_and_completion(app, server_manager)

    active_servers = server_manager.get_active_servers()
    if active_servers:
        logger.info(
            "Single-server bridge created successfully for '%s' (%d tools, %d resources, %d prompts)",
            server_name,
            len(active_servers[0].tools),
            len(active_servers[0].resources),
            len(active_servers[0].prompts),
        )
    else:
        logger.warning("Single-server bridge created but server is not active")

    return app
