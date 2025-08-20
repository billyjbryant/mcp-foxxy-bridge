"""Server modules for MCP Foxxy Bridge.

This module contains the server-side components of the MCP Foxxy Bridge,
including HTTP server setup, route handlers, middleware, and server
lifecycle management.

Key Components:
    - bridge_server: Core MCP bridge server implementation
    - mcp_server: HTTP/SSE server with route handlers
    - server_manager: Backend MCP server lifecycle management
    - middleware: HTTP middleware for authentication, logging, etc.
    - routes: Route definitions and handlers

Example:
    from mcp_foxxy_bridge.server import BridgeServer, create_app

    bridge = BridgeServer(config)
    app = create_app(bridge)
"""

from .bridge_server import (
    FilteredServerManager,
    create_bridge_server,
    create_server_filtered_bridge_view,
    create_tag_filtered_bridge_view,
)
from .mcp_server import (
    MCPServerSettings,
    run_bridge_server,
    run_mcp_server,
)
from .server_manager import (
    ManagedServer,
    ServerHealth,
    ServerManager,
    ServerStatus,
)

__all__ = [
    "FilteredServerManager",
    # MCP HTTP server
    "MCPServerSettings",
    "ManagedServer",
    "ServerHealth",
    # Server management
    "ServerManager",
    "ServerStatus",
    # Bridge server
    "create_bridge_server",
    "create_oauth_routes",
    "create_server_filtered_bridge_view",
    "create_tag_filtered_bridge_view",
    "run_bridge_server",
    "run_mcp_server",
]
