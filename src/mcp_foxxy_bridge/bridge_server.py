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

import logging
from typing import Any

from mcp import server, types

from .config_loader import BridgeConfiguration
from .server_manager import ServerManager

logger = logging.getLogger(__name__)

# Registry to store server manager instances for proper cleanup
_server_manager_registry: dict[Any, ServerManager] = {}


def _configure_prompts_capability(
    app: server.Server[object],
    server_manager: ServerManager,
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
    server_manager: ServerManager,
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

    async def _list_resource_templates(_: types.ListResourceTemplatesRequest) -> types.ServerResult:
        # For now, return empty templates as we don't aggregate templates yet
        result = types.ListResourceTemplatesResult(resourceTemplates=[])
        return types.ServerResult(result)

    app.request_handlers[types.ListResourceTemplatesRequest] = _list_resource_templates

    async def _read_resource(req: types.ReadResourceRequest) -> types.ServerResult:
        try:
            result = await server_manager.read_resource(str(req.params.uri))
            return types.ServerResult(result)
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

    async def _unsubscribe_resource(req: types.UnsubscribeRequest) -> types.ServerResult:
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
    server_manager: ServerManager,
) -> None:
    """Configure tools capability for the bridge server."""
    logger.debug("Configuring tools aggregation...")

    async def _list_tools(_: types.ListToolsRequest) -> types.ServerResult:
        try:
            tools = server_manager.get_aggregated_tools()
            result = types.ListToolsResult(tools=tools)
            return types.ServerResult(result)
        except Exception:
            logger.exception("Error listing tools")
            return types.ServerResult(types.ListToolsResult(tools=[]))

    app.request_handlers[types.ListToolsRequest] = _list_tools

    async def _call_tool(req: types.CallToolRequest) -> types.ServerResult:
        try:
            result = await server_manager.call_tool(
                req.params.name,
                req.params.arguments or {},
            )
            return types.ServerResult(result)
        except Exception:
            logger.exception("Error calling tool '%s'", req.params.name)
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
    server_manager: ServerManager,
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
    server_manager: ServerManager,
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
                "Progress update: %.1f%% (%s/%s)", percentage, req.params.progress, req.params.total
            )
        else:
            logger.info("Progress update: %s", req.params.progress)

    app.notification_handlers[types.ProgressNotification] = _send_progress_notification

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


async def create_bridge_server(bridge_config: BridgeConfiguration) -> server.Server[object]:
    """Create a bridge server that aggregates multiple MCP servers.

    Args:
        bridge_config: Configuration for the bridge and all MCP servers.

    Returns:
        A configured MCP server that bridges to multiple backends.
    """
    logger.info("Creating bridge server with %d configured servers", len(bridge_config.servers))

    # Create and start the server manager
    server_manager = ServerManager(bridge_config)
    await server_manager.start()

    # Create the bridge server
    bridge_name = "MCP Foxxy Bridge"
    app: server.Server[object] = server.Server(name=bridge_name)

    # Store server manager for cleanup using registry
    _server_manager_registry[id(app)] = server_manager

    # Configure capabilities based on aggregation settings
    if (
        bridge_config.bridge
        and bridge_config.bridge.aggregation
        and bridge_config.bridge.aggregation.prompts
    ):
        _configure_prompts_capability(app, server_manager)

    if (
        bridge_config.bridge
        and bridge_config.bridge.aggregation
        and bridge_config.bridge.aggregation.resources
    ):
        _configure_resources_capability(app, server_manager)

    if (
        bridge_config.bridge
        and bridge_config.bridge.aggregation
        and bridge_config.bridge.aggregation.tools
    ):
        _configure_tools_capability(app, server_manager)

    # Add logging capability
    logger.debug("Configuring logging...")
    _configure_logging_capability(app, server_manager)

    # Add notifications and completion capabilities
    _configure_notifications_and_completion(app, server_manager)

    # Completion handler is configured in _configure_notifications_and_completion

    logger.info(
        "Bridge server created successfully with %d active servers",
        len(server_manager.get_active_servers()),
    )

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
