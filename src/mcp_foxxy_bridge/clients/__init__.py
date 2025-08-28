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

"""Client wrapper modules for MCP Foxxy Bridge.

This module provides client wrapper implementations for different MCP
transport protocols and connection types, including:

- SSE (Server-Sent Events) client wrapper with authentication
- STDIO client wrapper for local process communication
- WebSocket client wrapper for real-time connections
- HTTP client wrapper for request-response patterns

Key Components:
    - sse_client_wrapper: SSE client with OAuth and error handling
    - stdio_client_wrapper: Local process MCP client wrapper
    - websocket_client_wrapper: WebSocket MCP client wrapper
    - http_client_wrapper: HTTP request-response MCP client wrapper

Example:
    from mcp_foxxy_bridge.clients import SSEClientWrapper, STDIOClientWrapper

    sse_client = SSEClientWrapper(server_url="https://api.example.com/v1/sse")
    stdio_client = STDIOClientWrapper(command="python", args=["server.py"])
"""

from .sse_client_wrapper import SSEClientWrapper
from .stdio_client_wrapper import STDIOClientWrapper

__all__ = [
    "SSEClientWrapper",
    "STDIOClientWrapper",
]
