#
# MCP Foxxy Bridge - Server Configuration Management
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
"""Server Configuration Management.

This module provides utilities for managing individual server configurations
within the MCP Foxxy Bridge system.
"""

from typing import Any

from .config_loader import BridgeServerConfig


class ServerConfigManager:
    """Manages server configurations."""

    def __init__(self) -> None:
        self.servers: dict[str, BridgeServerConfig] = {}

    def add_server(self, name: str, config: BridgeServerConfig) -> None:
        """Add a server configuration."""
        self.servers[name] = config

    def get_server(self, name: str) -> BridgeServerConfig:
        """Get a server configuration."""
        return self.servers[name]


def create_server_config(name: str, **kwargs: Any) -> BridgeServerConfig:
    """Create a server configuration with defaults."""
    return BridgeServerConfig(name=name, **kwargs)


def merge_server_configs(base: BridgeServerConfig, override: dict[str, Any]) -> BridgeServerConfig:
    """Merge server configuration with overrides."""
    # This is a simplified implementation
    # In practice, this would merge configurations more intelligently
    return base


def get_server_defaults() -> dict[str, Any]:
    """Get default server configuration values."""
    return {
        "enabled": True,
        "timeout": 60,
        "transport_type": "stdio",
        "retry_attempts": 3,
        "retry_delay": 1000,
        "priority": 100,
        "tags": [],
        "log_level": "ERROR",
        "verify_ssl": True,
    }
