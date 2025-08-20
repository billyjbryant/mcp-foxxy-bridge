#
# MCP Foxxy Bridge - Authentication Configuration Management
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
"""Authentication Configuration Management.

This module provides utilities for managing authentication configurations
for MCP servers.
"""

from typing import Any


class AuthConfigManager:
    """Manages authentication configurations."""

    def __init__(self) -> None:
        self.auth_configs: dict[str, dict[str, Any]] = {}

    def add_auth_config(self, server_name: str, config: dict[str, Any]) -> None:
        """Add authentication configuration for a server."""
        self.auth_configs[server_name] = config

    def get_auth_config(self, server_name: str) -> dict[str, Any]:
        """Get authentication configuration for a server."""
        return self.auth_configs.get(server_name, {})


def validate_auth_config(config: Any) -> list[str]:
    """Validate authentication configuration."""
    errors = []

    if not isinstance(config, dict):
        errors.append("Auth config must be a dictionary")
        return errors

    auth_type = config.get("type")
    if not auth_type:
        errors.append("Authentication type is required")
        return errors

    if auth_type == "bearer" and not config.get("token"):
        errors.append("Bearer authentication requires a token")
    elif auth_type == "api_key" and not config.get("key"):
        errors.append("API key authentication requires a key")
    elif auth_type == "basic" and not config.get("username"):
        errors.append("Basic authentication requires a username")

    return errors


def normalize_auth_config(config: dict[str, Any]) -> dict[str, Any]:
    """Normalize authentication configuration."""
    normalized = config.copy()

    # Add defaults
    if "type" not in normalized:
        normalized["type"] = "none"

    return normalized


def create_auth_config(auth_type: str, **kwargs: Any) -> dict[str, Any]:
    """Create authentication configuration."""
    config = {"type": auth_type}
    config.update(kwargs)
    return config
