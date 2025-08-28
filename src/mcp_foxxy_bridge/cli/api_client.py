#
# MCP Foxxy Bridge - API Client
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
"""HTTP client for communicating with the Foxxy Bridge REST API."""

import json
from typing import Any

import aiohttp
from rich.console import Console

from mcp_foxxy_bridge.config.config_loader import load_bridge_config_from_file


class BridgeAPIClient:
    """HTTP client for the Foxxy Bridge REST API."""

    def __init__(
        self,
        base_url: str = "http://localhost:9000",
        timeout: float = 30.0,
        console: Console | None = None,
    ) -> None:
        """Initialize the API client.

        Args:
            base_url: Base URL for the bridge API
            timeout: Request timeout in seconds
            console: Rich console for output (optional)
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.console = console or Console()

    async def get_status(self) -> dict[str, Any]:
        """Get global bridge status and health."""
        return await self._request("GET", "/status")

    async def list_servers(self) -> list[dict[str, Any]]:
        """List all available servers."""
        response = await self._request("GET", "/sse/servers")
        return response.get("servers", [])  # type: ignore[no-any-return]

    async def list_tags(self) -> dict[str, list[str]]:
        """List all available tags and their servers."""
        return await self._request("GET", "/sse/tags")

    async def get_server_status(self, server_name: str) -> dict[str, Any]:
        """Get individual server status and health."""
        return await self._request("GET", f"/sse/mcp/{server_name}/status")

    async def list_all_tools(self) -> list[dict[str, Any]]:
        """List all tools from all servers."""
        response = await self._request("GET", "/sse/list_tools")
        return response.get("tools", [])  # type: ignore[no-any-return]

    async def list_server_tools(self, server_name: str) -> list[dict[str, Any]]:
        """List tools for a specific server."""
        response = await self._request("GET", f"/sse/mcp/{server_name}/list_tools")
        return response.get("tools", [])  # type: ignore[no-any-return]

    async def list_tools_by_tag(self, tags: str, _union: bool = False) -> list[dict[str, Any]]:
        """List tools by tag(s).

        Args:
            tags: Tag string (single tag, + for AND, , for OR)
            _union: Reserved for future use (union/OR logic)
        """
        endpoint = f"/sse/tag/{tags}/list_tools"
        response = await self._request("GET", endpoint)
        return response.get("tools", [])  # type: ignore[no-any-return]

    async def reconnect_server(self, server_name: str) -> dict[str, Any]:
        """Force server reconnection."""
        return await self._request("POST", f"/sse/mcp/{server_name}/reconnect")

    async def rescan_tools(self) -> dict[str, Any]:
        """Refresh all server capabilities."""
        return await self._request("POST", "/sse/tools/rescan")

    async def get_oauth_status(self, server_name: str) -> dict[str, Any]:
        """Get OAuth authentication status for a server."""
        return await self._request("GET", f"/oauth/{server_name}/status")

    async def call_tool(
        self, server_name: str, tool_name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Call a tool on a specific server.

        Args:
            server_name: Name of the server
            tool_name: Name of the tool to call
            arguments: Tool arguments as dictionary

        Returns:
            Tool execution result
        """
        payload = {"name": tool_name, "arguments": arguments or {}}
        return await self._request("POST", f"/sse/mcp/{server_name}/call_tool", json_data=payload)

    async def _request(
        self, method: str, endpoint: str, json_data: dict[str, Any] | None = None, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make an HTTP request to the API.

        Args:
            method: HTTP method
            endpoint: API endpoint (without base URL)
            json_data: JSON data for request body
            params: Query parameters

        Returns:
            Response data as dictionary

        Raises:
            aiohttp.ClientError: For HTTP errors
            asyncio.TimeoutError: For timeout errors
        """
        url = f"{self.base_url}{endpoint}"

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            try:
                async with session.request(method, url, json=json_data, params=params) as response:
                    # Check for HTTP errors
                    if response.status >= 400:
                        error_text = await response.text()
                        raise aiohttp.ClientResponseError(
                            request_info=response.request_info,
                            history=response.history,
                            status=response.status,
                            message=f"HTTP {response.status}: {error_text}",
                        )

                    # Parse JSON response
                    try:
                        return await response.json()  # type: ignore[no-any-return]
                    except json.JSONDecodeError:
                        text = await response.text()
                        return {"raw_response": text}

            except aiohttp.ClientConnectionError as e:
                raise aiohttp.ClientConnectionError(
                    f"Failed to connect to bridge at {self.base_url}. Is the bridge running? Error: {e}"
                ) from e
            except TimeoutError as e:
                raise TimeoutError(f"Request to {url} timed out after {self.timeout.total}s") from e


def get_api_client_from_config(config_path: str, console: Console | None = None) -> BridgeAPIClient:
    """Create API client using configuration file settings.

    Args:
        config_path: Path to bridge configuration file
        console: Rich console for output

    Returns:
        Configured API client instance
    """
    try:
        bridge_config = load_bridge_config_from_file(config_path, {})

        # Extract host and port from bridge config
        host = "127.0.0.1"
        port = 9000

        if bridge_config.bridge:
            host = bridge_config.bridge.host or host
            port = bridge_config.bridge.port or port

        base_url = f"http://{host}:{port}"
        return BridgeAPIClient(base_url=base_url, console=console)

    except Exception as e:
        # Fallback to default if config loading fails
        if console:
            console.print(f"[yellow]Warning: Could not load config ({e}), using default URL[/yellow]")
        return BridgeAPIClient(console=console)
