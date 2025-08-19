#
# MCP Foxxy Bridge - Bridge Configuration Utilities
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
"""Bridge configuration utilities to avoid circular imports."""


def get_oauth_port() -> int:
    """Get the dedicated OAuth port.

    Returns:
        The dedicated OAuth port

    Raises:
        RuntimeError: If bridge server configuration hasn't been set
    """
    from mcp_foxxy_bridge.server.bridge_server_config import get_oauth_port as _get_oauth_port

    return _get_oauth_port()


def get_bridge_server_host() -> str:
    """Get the host the bridge server is running on.

    Returns:
        The bridge server host

    Raises:
        RuntimeError: If bridge server configuration hasn't been set
    """
    from mcp_foxxy_bridge.server.bridge_server_config import get_bridge_server_host as _get_bridge_server_host

    return _get_bridge_server_host()


def get_bridge_base_url() -> str:
    """Get the base URL of the bridge server.

    Returns:
        The bridge server base URL (e.g., "http://127.0.0.1:8080")

    Raises:
        RuntimeError: If bridge server configuration hasn't been set
    """
    from mcp_foxxy_bridge.server.bridge_server_config import get_bridge_base_url as _get_bridge_base_url

    return _get_bridge_base_url()


def get_bridge_server_port() -> int:
    """Get the port the bridge server is running on.

    Returns:
        The bridge server port

    Raises:
        RuntimeError: If bridge server configuration hasn't been set
    """
    from mcp_foxxy_bridge.server.bridge_server_config import get_bridge_server_port as _get_bridge_server_port

    return _get_bridge_server_port()


def is_bridge_config_set() -> bool:
    """Check if bridge server configuration has been set.

    Returns:
        True if configuration is set, False otherwise
    """
    from mcp_foxxy_bridge.server.bridge_server_config import is_bridge_config_set as _is_bridge_config_set

    return _is_bridge_config_set()
