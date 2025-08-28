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

"""Configuration management for MCP Foxxy Bridge.

This module provides comprehensive configuration loading, validation, and
management functionality for the MCP Foxxy Bridge, including:

- JSON configuration file parsing with environment variable expansion
- Server configuration validation and normalization
- Authentication configuration management
- Bridge settings and routing configuration
- Health check and monitoring configuration

Key Components:
    - config_loader: Main configuration loading and validation
    - server_config: Server-specific configuration management
    - auth_config: Authentication configuration handling
    - validation: Configuration validation utilities

Example:
    from mcp_foxxy_bridge.config import ConfigLoader, validate_bridge_config

    loader = ConfigLoader("config.json")
    config = await loader.load_config()

    errors = validate_bridge_config(config)
    if not errors:
        print("Configuration is valid")
"""

from .auth_config import (
    AuthConfigManager,
    create_auth_config,
    normalize_auth_config,
    validate_auth_config,
)
from .config_loader import (
    ConfigLoader,
    expand_environment_variables,
    load_bridge_config,
    normalize_server_config,
    validate_server_config,
)
from .server_config import (
    ServerConfigManager,
    create_server_config,
    get_server_defaults,
    merge_server_configs,
)
from .validation import (
    ConfigValidationError,
    get_validation_errors,
    validate_bridge_config,
    validate_config_schema,
)

__all__ = [
    # Authentication configuration
    "AuthConfigManager",
    # Core configuration loading
    "ConfigLoader",
    "ConfigValidationError",
    # Server configuration
    "ServerConfigManager",
    "create_auth_config",
    "create_server_config",
    "expand_environment_variables",
    "get_server_defaults",
    "get_validation_errors",
    "load_bridge_config",
    "merge_server_configs",
    "normalize_auth_config",
    "normalize_server_config",
    "validate_auth_config",
    # Validation utilities
    "validate_bridge_config",
    "validate_config_schema",
    "validate_server_config",
]
