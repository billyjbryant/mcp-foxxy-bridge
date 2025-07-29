#
# MCP Foxxy Bridge - Config Loader
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
"""Configuration loader for MCP Foxxy Bridge.

This module provides functionality to load named server configurations from JSON files
with enhanced bridge-specific configuration options.
"""

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp.client.stdio import StdioServerParameters

try:
    import jsonschema

    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False

logger = logging.getLogger(__name__)


def expand_env_vars(value: object) -> object:
    """Recursively expand environment variables in configuration values.

    Supports ${VAR_NAME} syntax with optional defaults: ${VAR_NAME:default_value}

    Args:
        value: The configuration value to expand (can be str, dict, list, or other)

    Returns:
        The value with environment variables expanded
    """
    if isinstance(value, str):
        # Pattern matches ${VAR_NAME} or ${VAR_NAME:default}
        pattern = r"\$\{([^}:]+)(?::([^}]*))?\}"

        def replace_env_var(match: re.Match[str]) -> str:
            var_name = match.group(1)
            default_value = match.group(2) if match.group(2) is not None else ""
            env_value = os.getenv(var_name, default_value)

            if env_value == "" and match.group(2) is None:
                logger.warning(
                    "Environment variable '%s' not found and no default provided",
                    var_name,
                )

            return env_value

        return re.sub(pattern, replace_env_var, value)

    if isinstance(value, dict):
        return {k: expand_env_vars(v) for k, v in value.items()}

    if isinstance(value, list):
        return [expand_env_vars(item) for item in value]

    return value


@dataclass
class HealthCheckConfig:
    """Configuration for server health checks."""

    enabled: bool = True
    interval: int = 30000  # milliseconds
    timeout: int = 5000  # milliseconds
    keep_alive_interval: int = 60000  # milliseconds - frequent keep-alive pings
    keep_alive_timeout: int = 10000  # milliseconds - timeout for keep-alive pings
    max_consecutive_failures: int = 3  # failures before marking server as failed
    auto_restart: bool = True  # automatically restart failed servers
    restart_delay: int = 5000  # milliseconds - delay before restart attempt
    max_restart_attempts: int = 5  # maximum restart attempts before giving up

    # Health check operation configuration
    operation: str = "list_tools"  # MCP operation to use for health checks
    tool_name: str | None = None  # Specific tool name if operation is "call_tool"
    tool_arguments: dict[str, str] | None = None  # Arguments for tool calls
    resource_uri: str | None = None  # Resource URI if operation is "read_resource"
    prompt_name: str | None = None  # Prompt name if operation is "get_prompt"
    prompt_arguments: dict[str, str] | None = None  # Arguments for prompt calls

    # HTTP-specific health check options (for remote MCP servers)
    http_path: str | None = None  # Custom HTTP path for health checks
    http_method: str = "GET"  # HTTP method for health checks
    expected_status: int = 200  # Expected HTTP status code
    expected_content: str | None = None  # Expected content substring


@dataclass
class BridgeServerConfig:
    """Enhanced configuration for a single MCP server in the bridge."""

    name: str
    enabled: bool = True
    command: str = ""
    args: list[str] | None = None
    env: dict[str, str] | None = None
    timeout: int = 60
    transport_type: str = "stdio"
    retry_attempts: int = 3
    retry_delay: int = 1000  # milliseconds
    health_check: HealthCheckConfig | None = None
    tool_namespace: str | None = None
    resource_namespace: str | None = None
    prompt_namespace: str | None = None
    priority: int = 100
    tags: list[str] | None = None

    def __post_init__(self) -> None:
        """Initialize default values for optional fields."""
        if self.args is None:
            self.args = []
        if self.env is None:
            self.env = {}
        if self.health_check is None:
            self.health_check = HealthCheckConfig()
        if self.tags is None:
            self.tags = []


@dataclass
class AggregationConfig:
    """Configuration for capability aggregation."""

    tools: bool = True
    resources: bool = True
    prompts: bool = True


@dataclass
class FailoverConfig:
    """Configuration for server failover behavior."""

    enabled: bool = True
    max_failures: int = 3
    recovery_interval: int = 60000  # milliseconds


@dataclass
class BridgeConfig:
    """Configuration for bridge-specific behavior."""

    conflict_resolution: str = "namespace"  # priority, namespace, first, error
    default_namespace: bool = True
    aggregation: AggregationConfig | None = None
    failover: FailoverConfig | None = None

    def __post_init__(self) -> None:
        """Initialize default values for bridge configuration."""
        if self.aggregation is None:
            self.aggregation = AggregationConfig()
        if self.failover is None:
            self.failover = FailoverConfig()


@dataclass
class BridgeConfiguration:
    """Complete bridge configuration including all servers and bridge settings."""

    servers: dict[str, BridgeServerConfig]
    bridge: BridgeConfig | None = None

    def __post_init__(self) -> None:
        """Initialize default bridge configuration."""
        if self.bridge is None:
            self.bridge = BridgeConfig()


def validate_bridge_config(config_data: dict[str, Any]) -> None:
    """Validate bridge configuration against JSON schema.

    Args:
        config_data: The configuration data to validate.

    Raises:
        ValueError: If the configuration is invalid.
    """
    if not JSONSCHEMA_AVAILABLE:
        logger.warning("jsonschema not available, skipping configuration validation")
        return

    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "mcpServers": {
                "type": "object",
                "patternProperties": {
                    "^[a-zA-Z0-9_-]+$": {
                        "type": "object",
                        "properties": {
                            "enabled": {"type": "boolean"},
                            "command": {"type": "string"},
                            "args": {"type": "array", "items": {"type": "string"}},
                            "env": {"type": "object", "additionalProperties": {"type": "string"}},
                            "timeout": {"type": "number", "minimum": 1},
                            "transportType": {"type": "string", "enum": ["stdio"]},
                            "retryAttempts": {"type": "number", "minimum": 0},
                            "retryDelay": {"type": "number", "minimum": 0},
                            "healthCheck": {
                                "type": "object",
                                "properties": {
                                    "enabled": {"type": "boolean"},
                                    "interval": {"type": "number", "minimum": 1000},
                                    "timeout": {"type": "number", "minimum": 1000},
                                    "keepAliveInterval": {"type": "number", "minimum": 1000},
                                    "keepAliveTimeout": {"type": "number", "minimum": 1000},
                                    "maxConsecutiveFailures": {"type": "number", "minimum": 1},
                                    "autoRestart": {"type": "boolean"},
                                    "restartDelay": {"type": "number", "minimum": 0},
                                    "maxRestartAttempts": {"type": "number", "minimum": 1},
                                    "operation": {
                                        "type": "string",
                                        "enum": [
                                            "list_tools",
                                            "list_resources",
                                            "list_prompts",
                                            "call_tool",
                                            "read_resource",
                                            "get_prompt",
                                            "ping",
                                            "health",
                                            "status",
                                        ],
                                    },
                                    "toolName": {"type": "string"},
                                    "toolArguments": {
                                        "type": "object",
                                        "additionalProperties": {"type": "string"},
                                    },
                                    "resourceUri": {"type": "string"},
                                    "promptName": {"type": "string"},
                                    "promptArguments": {
                                        "type": "object",
                                        "additionalProperties": {"type": "string"},
                                    },
                                    "httpPath": {"type": "string"},
                                    "httpMethod": {
                                        "type": "string",
                                        "enum": ["GET", "POST", "PUT", "HEAD"],
                                    },
                                    "expectedStatus": {
                                        "type": "number",
                                        "minimum": 100,
                                        "maximum": 599,
                                    },
                                    "expectedContent": {"type": "string"},
                                },
                            },
                            "toolNamespace": {"type": "string"},
                            "resourceNamespace": {"type": "string"},
                            "promptNamespace": {"type": "string"},
                            "priority": {"type": "number", "minimum": 0},
                            "tags": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["command"],
                    },
                },
            },
            "bridge": {
                "type": "object",
                "properties": {
                    "conflictResolution": {
                        "type": "string",
                        "enum": ["priority", "namespace", "first", "error"],
                    },
                    "defaultNamespace": {"type": "boolean"},
                    "aggregation": {
                        "type": "object",
                        "properties": {
                            "tools": {"type": "boolean"},
                            "resources": {"type": "boolean"},
                            "prompts": {"type": "boolean"},
                        },
                    },
                    "failover": {
                        "type": "object",
                        "properties": {
                            "enabled": {"type": "boolean"},
                            "maxFailures": {"type": "number", "minimum": 1},
                            "recoveryInterval": {"type": "number", "minimum": 1000},
                        },
                    },
                },
            },
        },
        "required": ["mcpServers"],
    }

    try:
        jsonschema.validate(config_data, schema)  # type: ignore[no-untyped-call]
    except jsonschema.ValidationError as e:
        logger.exception("Configuration validation failed")
        msg = f"Invalid configuration: {e.message}"
        raise ValueError(msg) from e
    except Exception as e:
        logger.exception("Unexpected error during configuration validation")
        msg = f"Configuration validation error: {e}"
        raise ValueError(msg) from e


def validate_server_config(name: str, server_config: dict[str, Any]) -> list[str]:
    """Validate individual server configuration and return list of warnings.

    Args:
        name: The server name.
        server_config: The server configuration to validate.

    Returns:
        List of warning messages.
    """
    warnings = []

    # Check required fields
    if not server_config.get("command"):
        warnings.append(f"Server '{name}' missing required 'command' field")

    # Check args format
    args = server_config.get("args", [])
    if not isinstance(args, list):
        warnings.append(f"Server '{name}' has invalid 'args' field (must be array)")
    elif not all(isinstance(arg, str) for arg in args):
        warnings.append(f"Server '{name}' has non-string values in 'args' array")

    # Check env format
    env = server_config.get("env", {})
    if not isinstance(env, dict):
        warnings.append(f"Server '{name}' has invalid 'env' field (must be object)")
    elif not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
        warnings.append(f"Server '{name}' has non-string keys/values in 'env' object")

    # Check timeout value
    timeout = server_config.get("timeout", 60)
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        warnings.append(f"Server '{name}' has invalid 'timeout' value (must be positive number)")

    # Check retry settings
    retry_attempts = server_config.get("retryAttempts", 3)
    if not isinstance(retry_attempts, int) or retry_attempts < 0:
        warnings.append(
            f"Server '{name}' has invalid 'retryAttempts' value (must be non-negative integer)",
        )

    retry_delay = server_config.get("retryDelay", 1000)
    if not isinstance(retry_delay, (int, float)) or retry_delay < 0:
        warnings.append(
            f"Server '{name}' has invalid 'retryDelay' value (must be non-negative number)",
        )

    # Check priority
    priority = server_config.get("priority", 100)
    if not isinstance(priority, (int, float)) or priority < 0:
        warnings.append(
            f"Server '{name}' has invalid 'priority' value (must be non-negative number)",
        )

    # Check tags
    tags = server_config.get("tags", [])
    if not isinstance(tags, list):
        warnings.append(f"Server '{name}' has invalid 'tags' field (must be array)")
    elif not all(isinstance(tag, str) for tag in tags):
        warnings.append(f"Server '{name}' has non-string values in 'tags' array")

    # Check namespace values
    for namespace_field in ["toolNamespace", "resourceNamespace", "promptNamespace"]:
        namespace = server_config.get(namespace_field)
        if namespace is not None and not isinstance(namespace, str):
            warnings.append(
                f"Server '{name}' has invalid '{namespace_field}' value (must be string)",
            )
        elif namespace is not None and not namespace.strip():
            warnings.append(f"Server '{name}' has empty '{namespace_field}' value")

    # Check health check config
    health_check = server_config.get("healthCheck", {})
    if not isinstance(health_check, dict):
        warnings.append(f"Server '{name}' has invalid 'healthCheck' field (must be object)")
    else:
        # Validate numeric fields with minimum values
        numeric_fields = [
            ("interval", 1000),
            ("timeout", 1000),
            ("keepAliveInterval", 1000),
            ("keepAliveTimeout", 1000),
            ("maxConsecutiveFailures", 1),
            ("restartDelay", 0),
            ("maxRestartAttempts", 1),
            ("expectedStatus", 100),
        ]
        for field, min_val in numeric_fields:
            value = health_check.get(field)
            if value is not None and (not isinstance(value, (int, float)) or value < min_val):
                warnings.append(
                    f"Server '{name}' has invalid healthCheck.{field} value (must be >= {min_val})",
                )

        # Validate operation field
        operation = health_check.get("operation", "list_tools")
        valid_operations = [
            "list_tools",
            "list_resources",
            "list_prompts",
            "call_tool",
            "read_resource",
            "get_prompt",
            "ping",
            "health",
            "status",
        ]
        if operation not in valid_operations:
            warnings.append(
                f"Server '{name}' has invalid healthCheck.operation '{operation}' "
                f"(must be one of {valid_operations})"
            )

        # Validate operation-specific requirements
        if operation == "call_tool" and not health_check.get("toolName"):
            warnings.append(
                f"Server '{name}' healthCheck operation 'call_tool' requires 'toolName'"
            )
        elif operation == "read_resource" and not health_check.get("resourceUri"):
            warnings.append(
                f"Server '{name}' healthCheck operation 'read_resource' requires 'resourceUri'"
            )
        elif operation == "get_prompt" and not health_check.get("promptName"):
            warnings.append(
                f"Server '{name}' healthCheck operation 'get_prompt' requires 'promptName'"
            )

        # Validate HTTP-specific fields
        http_method = health_check.get("httpMethod", "GET")
        if http_method not in ["GET", "POST", "PUT", "HEAD"]:
            warnings.append(f"Server '{name}' has invalid healthCheck.httpMethod '{http_method}'")

        expected_status = health_check.get("expectedStatus", 200)
        min_status = 100
        max_status = 599
        if expected_status is not None and (
            expected_status < min_status or expected_status > max_status
        ):
            warnings.append(
                f"Server '{name}' has invalid healthCheck.expectedStatus '{expected_status}' "
                f"(must be {min_status}-{max_status})"
            )

    return warnings


def load_named_server_configs_from_file(
    config_file_path: str,
    base_env: dict[str, str],
) -> dict[str, StdioServerParameters]:
    """Loads named server configurations from a JSON file.

    Args:
        config_file_path: Path to the JSON configuration file.
        base_env: The base environment dictionary to be inherited by servers.

    Returns:
        A dictionary of named server parameters.

    Raises:
        FileNotFoundError: If the config file is not found.
        json.JSONDecodeError: If the config file contains invalid JSON.
        ValueError: If the config file format is invalid.
    """
    named_stdio_params: dict[str, StdioServerParameters] = {}
    logger.info("Loading named server configurations from: %s", config_file_path)

    try:
        with Path(config_file_path).open() as f:
            config_data = json.load(f)
    except FileNotFoundError:
        logger.exception("Configuration file not found: %s", config_file_path)
        raise
    except json.JSONDecodeError:
        logger.exception("Error decoding JSON from configuration file: %s", config_file_path)
        raise
    except Exception as e:
        logger.exception(
            "Unexpected error opening or reading configuration file %s",
            config_file_path,
        )
        error_message = f"Could not read configuration file: {e}"
        raise ValueError(error_message) from e

    # Expand environment variables in the configuration
    logger.debug("Expanding environment variables in legacy configuration")
    config_data = expand_env_vars(config_data)

    if not isinstance(config_data, dict) or "mcpServers" not in config_data:
        msg = f"Invalid config file format in {config_file_path}. Missing 'mcpServers' key."
        logger.error(msg)
        raise ValueError(msg)

    for name, server_config in config_data.get("mcpServers", {}).items():
        if not isinstance(server_config, dict):
            logger.warning(
                "Skipping invalid server config for '%s' in %s. Entry is not a dictionary.",
                name,
                config_file_path,
            )
            continue
        if not server_config.get("enabled", True):  # Default to True if 'enabled' is not present
            logger.info("Named server '%s' from config is not enabled. Skipping.", name)
            continue

        command = server_config.get("command")
        command_args = server_config.get("args", [])
        env = server_config.get("env", {})

        if not command:
            logger.warning(
                "Named server '%s' from config is missing 'command'. Skipping.",
                name,
            )
            continue
        if not isinstance(command_args, list):
            logger.warning(
                "Named server '%s' from config has invalid 'args' (must be a list). Skipping.",
                name,
            )
            continue

        new_env = base_env.copy()
        new_env.update(env)

        named_stdio_params[name] = StdioServerParameters(
            command=command,
            args=command_args,
            env=new_env,
            cwd=None,
        )
        logger.info(
            "Configured named server '%s' from config: %s %s",
            name,
            command,
            " ".join(command_args),
        )

    return named_stdio_params


def load_bridge_config_from_file(
    config_file_path: str,
    base_env: dict[str, str],
) -> BridgeConfiguration:
    """Loads enhanced bridge configuration from a JSON file.

    Args:
        config_file_path: Path to the JSON configuration file.
        base_env: The base environment dictionary to be inherited by servers.

    Returns:
        A BridgeConfiguration object with all server and bridge settings.

    Raises:
        FileNotFoundError: If the config file is not found.
        json.JSONDecodeError: If the config file contains invalid JSON.
        ValueError: If the config file format is invalid.
    """
    logger.info("Loading bridge configuration from: %s", config_file_path)

    try:
        with Path(config_file_path).open() as f:
            config_data = json.load(f)
    except FileNotFoundError:
        logger.exception("Configuration file not found: %s", config_file_path)
        raise
    except json.JSONDecodeError:
        logger.exception("Error decoding JSON from configuration file: %s", config_file_path)
        raise
    except Exception as e:
        logger.exception(
            "Unexpected error opening or reading configuration file %s",
            config_file_path,
        )
        error_message = f"Could not read configuration file: {e}"
        raise ValueError(error_message) from e

    # Expand environment variables in the configuration
    logger.debug("Expanding environment variables in configuration")
    config_data = expand_env_vars(config_data)

    if not isinstance(config_data, dict) or "mcpServers" not in config_data:
        msg = f"Invalid config file format in {config_file_path}. Missing 'mcpServers' key."
        logger.error(msg)
        raise ValueError(msg)

    # Validate configuration against schema
    try:
        validate_bridge_config(config_data)
    except ValueError:
        logger.exception("Configuration validation failed for %s", config_file_path)
        raise

    # Parse server configurations
    servers = {}
    for name, server_config in config_data.get("mcpServers", {}).items():
        if not isinstance(server_config, dict):
            logger.warning(
                "Skipping invalid server config for '%s' in %s. Entry is not a dictionary.",
                name,
                config_file_path,
            )
            continue

        # Validate server configuration and log warnings
        warnings = validate_server_config(name, server_config)
        for warning in warnings:
            logger.warning(warning)

        # Create health check config
        health_check_data = server_config.get("healthCheck", {})
        health_check = HealthCheckConfig(
            enabled=health_check_data.get("enabled", True),
            interval=health_check_data.get("interval", 30000),
            timeout=health_check_data.get("timeout", 5000),
            keep_alive_interval=health_check_data.get("keepAliveInterval", 60000),
            keep_alive_timeout=health_check_data.get("keepAliveTimeout", 10000),
            max_consecutive_failures=health_check_data.get("maxConsecutiveFailures", 3),
            auto_restart=health_check_data.get("autoRestart", True),
            restart_delay=health_check_data.get("restartDelay", 5000),
            max_restart_attempts=health_check_data.get("maxRestartAttempts", 5),
            operation=health_check_data.get("operation", "list_tools"),
            tool_name=health_check_data.get("toolName"),
            tool_arguments=health_check_data.get("toolArguments"),
            resource_uri=health_check_data.get("resourceUri"),
            prompt_name=health_check_data.get("promptName"),
            prompt_arguments=health_check_data.get("promptArguments"),
            http_path=health_check_data.get("httpPath"),
            http_method=health_check_data.get("httpMethod", "GET"),
            expected_status=health_check_data.get("expectedStatus", 200),
            expected_content=health_check_data.get("expectedContent"),
        )

        # Create server environment
        server_env = base_env.copy()
        server_env.update(server_config.get("env", {}))

        # Create server configuration
        server = BridgeServerConfig(
            name=name,
            enabled=server_config.get("enabled", True),
            command=server_config.get("command", ""),
            args=server_config.get("args", []),
            env=server_env,
            timeout=server_config.get("timeout", 60),
            transport_type=server_config.get("transportType", "stdio"),
            retry_attempts=server_config.get("retryAttempts", 3),
            retry_delay=server_config.get("retryDelay", 1000),
            health_check=health_check,
            tool_namespace=server_config.get("toolNamespace"),
            resource_namespace=server_config.get("resourceNamespace"),
            prompt_namespace=server_config.get("promptNamespace"),
            priority=server_config.get("priority", 100),
            tags=server_config.get("tags", []),
        )

        if not server.command:
            logger.warning(
                "Named server '%s' from config is missing 'command'. Skipping.",
                name,
            )
            continue

        if not isinstance(server.args, list):
            logger.warning(
                "Named server '%s' from config has invalid 'args' (must be a list). Skipping.",
                name,
            )
            continue

        servers[name] = server
        logger.info(
            "Configured named server '%s' from config: %s %s",
            name,
            server.command,
            " ".join(server.args),
        )

    # Parse bridge configuration
    bridge_data = config_data.get("bridge", {})

    # Parse aggregation config
    aggregation_data = bridge_data.get("aggregation", {})
    aggregation = AggregationConfig(
        tools=aggregation_data.get("tools", True),
        resources=aggregation_data.get("resources", True),
        prompts=aggregation_data.get("prompts", True),
    )

    # Parse failover config
    failover_data = bridge_data.get("failover", {})
    failover = FailoverConfig(
        enabled=failover_data.get("enabled", True),
        max_failures=failover_data.get("maxFailures", 3),
        recovery_interval=failover_data.get("recoveryInterval", 60000),
    )

    # Create bridge config
    bridge = BridgeConfig(
        conflict_resolution=bridge_data.get("conflictResolution", "namespace"),
        default_namespace=bridge_data.get("defaultNamespace", True),
        aggregation=aggregation,
        failover=failover,
    )

    return BridgeConfiguration(servers=servers, bridge=bridge)


def bridge_config_to_stdio_params(
    bridge_config: BridgeConfiguration,
) -> dict[str, StdioServerParameters]:
    """Converts BridgeConfiguration to the legacy StdioServerParameters format.

    Args:
        bridge_config: The bridge configuration to convert.

    Returns:
        A dictionary of named server parameters compatible with existing code.
    """
    stdio_params = {}

    for name, server in bridge_config.servers.items():
        if not server.enabled:
            logger.info("Named server '%s' is disabled. Skipping.", name)
            continue

        stdio_params[name] = StdioServerParameters(
            command=server.command,
            args=server.args or [],
            env=server.env or {},
            cwd=None,
        )

    return stdio_params
