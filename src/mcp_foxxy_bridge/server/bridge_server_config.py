#
# MCP Foxxy Bridge - Bridge Server Configuration
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
"""Bridge Server Configuration Management.

This module manages global bridge server configuration including the running
port, host, and other runtime settings that need to be accessed by various
components throughout the bridge.
"""

# Global bridge server configuration
_bridge_host: str | None = None
_bridge_port: int | None = None
_bridge_base_url: str | None = None
_oauth_port: int | None = None


def set_bridge_server_config(host: str, port: int, oauth_port: int) -> None:
    """Set the bridge server configuration.

    This should be called when the bridge server starts up with the actual
    host and port it's running on.

    Args:
        host: The host the bridge is running on (e.g., "127.0.0.1")
        port: The port the bridge is running on (e.g., 8080)
        oauth_port: The dedicated OAuth port (e.g., 8090)
    """
    global _bridge_host, _bridge_port, _bridge_base_url, _oauth_port
    _bridge_host = host
    _bridge_port = port
    _bridge_base_url = f"http://{host}:{port}"
    _oauth_port = oauth_port  # Always use dedicated OAuth port


def get_bridge_server_port() -> int:
    """Get the port the bridge server is running on.

    Returns:
        The bridge server port

    Raises:
        RuntimeError: If bridge server configuration hasn't been set
    """
    if _bridge_port is None:
        raise RuntimeError("Bridge server configuration not set. Call set_bridge_server_config() first.")
    return _bridge_port


def get_bridge_server_host() -> str:
    """Get the host the bridge server is running on.

    Returns:
        The bridge server host

    Raises:
        RuntimeError: If bridge server configuration hasn't been set
    """
    if _bridge_host is None:
        raise RuntimeError("Bridge server configuration not set. Call set_bridge_server_config() first.")
    return _bridge_host


def get_bridge_base_url() -> str:
    """Get the base URL of the bridge server.

    Returns:
        The bridge server base URL (e.g., "http://127.0.0.1:8080")

    Raises:
        RuntimeError: If bridge server configuration hasn't been set
    """
    if _bridge_base_url is None:
        raise RuntimeError("Bridge server configuration not set. Call set_bridge_server_config() first.")
    return _bridge_base_url


def get_oauth_port() -> int:
    """Get the dedicated OAuth port.

    Returns:
        The dedicated OAuth port

    Raises:
        RuntimeError: If bridge server configuration hasn't been set
    """
    if _oauth_port is None:
        raise RuntimeError("Bridge server configuration not set. Call set_bridge_server_config() first.")
    return _oauth_port


def is_bridge_config_set() -> bool:
    """Check if bridge server configuration has been set.

    Returns:
        True if configuration is set, False otherwise
    """
    return _bridge_port is not None and _bridge_host is not None
