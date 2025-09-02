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
