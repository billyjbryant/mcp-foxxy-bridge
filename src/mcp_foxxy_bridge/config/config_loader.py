#
# MCP Foxxy Bridge - Configuration Loader
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
"""Configuration Loading and Management for MCP Foxzy Bridge.

This module provides comprehensive configuration loading, validation, and
management functionality for the MCP Foxxy Bridge system, including:

- JSON configuration file parsing with environment variable expansion
- Command substitution with security validation
- Server configuration validation and normalization
- Bridge settings management
- Schema validation with detailed error reporting

Key Features:
    - Environment variable expansion with ${VAR_NAME:default} syntax
    - Secure command substitution with $(command) syntax
    - Comprehensive configuration validation
    - Support for multiple transport types (STDIO, SSE)
    - Health check configuration management
    - OAuth and authentication configuration
    - Detailed error reporting and logging

Example:
    Basic configuration loading:

    >>> loader = ConfigLoader("config.json")
    >>> config = await loader.load_config()
    >>> print(f"Loaded {len(config.servers)} servers")

    Environment variable expansion:

    >>> # In config.json: {"api_key": "${API_KEY:default-key}"}
    >>> config = load_bridge_config("config.json", {})
    >>> # api_key will be expanded from environment

    Command substitution:

    >>> # In config.json: {"token": "$(vault read -field=token secret/api)"}
    >>> config = load_bridge_config("config.json", {})
    >>> # token will be retrieved from vault command
"""

import json
import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp_foxxy_bridge.security.config import BridgeSecurityConfig, ServerSecurityConfig

from mcp.client.stdio import StdioServerParameters

from mcp_foxxy_bridge.utils.config_migration import get_config_dir

try:
    import jsonschema

    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False

from mcp_foxxy_bridge.utils.logging import get_logger

logger = get_logger(__name__, facility="CONFIG")

# Security constants for command validation
MAX_COMMAND_LENGTH = 1000  # Maximum allowed command string length
MAX_ARG_LENGTH = 500  # Maximum allowed individual argument length
COMMAND_TIMEOUT = 30  # Timeout in seconds for command execution


def _sanitize_command_for_logging(command: str) -> str:
    """Sanitize command string for safe logging by removing/escaping potentially dangerous characters."""
    # Remove or escape characters that could be interpreted by shells or log viewers
    # Replace backticks, dollar signs, semicolons, pipes, and other shell metacharacters
    sanitized = re.sub(r"[`$;|&<>(){}[\]*?~]", "?", command)

    # Limit length to prevent log spam
    if len(sanitized) > 100:
        sanitized = sanitized[:97] + "..."

    # Escape any remaining quotes to prevent log injection
    return sanitized.replace('"', '\\"').replace("'", "\\'")


def _migrate_oauth_fields(config_data: dict[str, Any]) -> bool:
    """Migrate legacy 'oauth' field to 'oauth_config' in server configurations.

    This handles backward compatibility where older configs or CLI commands
    may have used 'oauth' instead of the expected 'oauth_config' field name.

    Args:
        config_data: The parsed configuration data

    Returns:
        True if any migrations were performed, False otherwise
    """
    migrated = False

    try:
        servers = config_data.get("mcpServers", {})

        for server_name, server_config in servers.items():
            if isinstance(server_config, dict):
                # Check if server has 'oauth' but not 'oauth_config'
                if "oauth" in server_config and "oauth_config" not in server_config:
                    # Migrate oauth to oauth_config
                    server_config["oauth_config"] = server_config.pop("oauth")
                    logger.debug(f"Migrated 'oauth' to 'oauth_config' for server '{server_name}'")
                    migrated = True
                elif "oauth" in server_config and "oauth_config" in server_config:
                    # Both exist - prefer oauth_config and remove oauth
                    server_config.pop("oauth")
                    logger.debug(f"Removed duplicate 'oauth' field for server '{server_name}' (keeping 'oauth_config')")
                    migrated = True

    except Exception as e:
        logger.debug(f"Error during oauth field migration: {e}")

    return migrated


def _write_config_to_disk(config_path: str, config_data: dict[str, Any]) -> None:
    """Write configuration data back to disk with backup.

    Args:
        config_path: Path to the configuration file
        config_data: The configuration data to write
    """
    try:
        config_file_path = Path(config_path)

        # Create backup
        backup_path = config_file_path.with_suffix(".json.backup")
        try:
            shutil.copy2(config_file_path, backup_path)
            logger.debug("Created configuration backup")
        except Exception as e:
            logger.debug(f"Could not create backup: {e}")

        # Write updated config
        with config_file_path.open("w") as f:
            json.dump(config_data, f, indent=2)

        logger.info("Updated configuration file with migrations")

    except Exception as e:
        logger.debug(f"Failed to write config to disk: {e}")


def _ensure_schema_reference(config_path: str, config_data: dict[str, Any]) -> bool:
    """Ensure the config file has a $schema reference for IDE support.

    Args:
        config_path: Path to the configuration file
        config_data: The parsed configuration data

    Returns:
        True if the schema reference was added and file was updated, False otherwise
    """
    try:
        # Check if schema reference already exists and is correct
        current_schema = config_data.get("$schema", "")

        # Get the config directory and build absolute path to schema
        config_dir = get_config_dir()
        schema_path = config_dir / "bridge_config_schema.json"
        correct_schema = str(schema_path)

        if current_schema == correct_schema:
            logger.debug("Config already has correct schema reference")
            return False

        # Add or update schema reference, ensuring it's first in the JSON
        # Create new ordered dict with schema first
        updated_config = {"$schema": correct_schema}

        # Add all other keys (except existing $schema if present)
        updated_config.update({key: value for key, value in config_data.items() if key != "$schema"})

        # Write the updated config back to file
        config_file_path = Path(config_path)

        # Create backup
        backup_path = config_file_path.with_suffix(".json.backup")
        try:
            shutil.copy2(config_file_path, backup_path)
            logger.debug("Created configuration backup")
        except Exception as e:
            logger.debug(f"Could not create backup: {e}")

        # Write updated config
        with config_file_path.open("w") as f:
            json.dump(updated_config, f, indent=2)

        if current_schema:
            logger.info("Updated schema reference in configuration file for IDE support")
        else:
            logger.info("Added schema reference to configuration file for IDE support")
        return True

    except Exception as e:
        logger.debug(f"Failed to add schema reference to config: {e}")
        return False


def _ensure_config_schema() -> None:
    """Copy the JSON schema to the config directory if it doesn't exist or is outdated.

    This ensures users always have access to the current schema for IDE auto-completion
    and validation, matching the exact version of the bridge they're running.
    """
    try:
        # Get the config directory and schema paths
        config_dir = get_config_dir()
        config_schema_path = config_dir / "bridge_config_schema.json"

        # Find the schema file in the package directory
        # This works whether we're installed via pip or running from source
        current_file_dir = Path(__file__).parent.parent.parent.parent
        source_schema_path = current_file_dir / "bridge_config_schema.json"

        if not source_schema_path.exists():
            logger.debug("Schema file not found in source directory, skipping schema copy")
            return

        # Check if we need to copy the schema
        should_copy = False

        if not config_schema_path.exists():
            logger.debug("Config schema not found, will copy from source")
            should_copy = True
        else:
            # Check if the source is newer
            try:
                source_mtime = source_schema_path.stat().st_mtime
                config_mtime = config_schema_path.stat().st_mtime

                if source_mtime > config_mtime:
                    logger.debug("Source schema is newer, will update config schema")
                    should_copy = True

            except OSError:
                logger.debug("Could not compare schema file times, will copy to be safe")
                should_copy = True

        if should_copy:
            logger.info("Copying JSON schema to config directory for IDE support")
            shutil.copy2(source_schema_path, config_schema_path)
            logger.debug(f"Schema copied to: {config_schema_path}")

    except Exception as e:
        # Don't fail configuration loading if schema copy fails
        logger.debug(f"Failed to copy schema file: {e}")


class ConfigLoader:
    """Comprehensive configuration loader with validation and expansion.

    This class provides a high-level interface for loading MCP Foxxy Bridge
    configurations from JSON files with support for environment variable
    expansion, command substitution, and comprehensive validation.

    Attributes:
        config_file_path: Path to the configuration file
        base_env: Base environment variables for server processes

    Example:
        >>> loader = ConfigLoader("config.json")
        >>> config = await loader.load_config()
        >>>
        >>> # With custom environment
        >>> loader = ConfigLoader("config.json", {"DEBUG": "1"})
        >>> config = await loader.load_config()
    """

    def __init__(self, config_file_path: str, base_env: dict[str, str] | None = None) -> None:
        """Initialize configuration loader.

        Args:
            config_file_path: Path to the JSON configuration file
            base_env: Base environment variables (defaults to empty dict)
        """
        self.config_file_path = Path(config_file_path)
        self.base_env = base_env or {}

        logger.debug(f"Initialized ConfigLoader for: {config_file_path}")

    def load_config(self) -> "BridgeConfiguration":
        """Load and validate configuration from file.

        Returns:
            BridgeConfiguration object with all settings

        Raises:
            FileNotFoundError: If configuration file doesn't exist
            ValueError: If configuration is invalid

        Example:
            >>> loader = ConfigLoader("config.json")
            >>> config = loader.load_config()
            >>> print(f"Bridge listening on {config.bridge.host}:{config.bridge.port}")
        """
        return load_bridge_config_from_file(str(self.config_file_path), self.base_env)

    def validate_config(self) -> list[str]:
        """Validate configuration file and return any errors.

        Returns:
            List of validation error messages (empty if valid)

        Example:
            >>> loader = ConfigLoader("config.json")
            >>> errors = loader.validate_config()
            >>> if errors:
            ...     print("Configuration errors:", errors)
        """
        try:
            self.load_config()
            return []
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
            return [str(e)]
        except Exception as e:
            logger.warning("Unexpected configuration validation error: %s", str(e))
            return [f"Unexpected configuration error: {e!s}"]


# Configuration data classes


@dataclass
class OAuthConfig:
    """OAuth configuration for MCP servers.

    Attributes:
        enabled: Whether OAuth is enabled for this server
        issuer: OAuth issuer URL
        verify_ssl: Whether to verify SSL/TLS certificates
        keep_alive_interval: Keep-alive ping interval for OAuth servers in milliseconds
        token_refresh_interval: Proactive token refresh interval in milliseconds
        connection_check_interval: Connection health check interval in milliseconds
    """

    enabled: bool = False
    issuer: str | None = None
    verify_ssl: bool = True
    keep_alive_interval: int = 20000  # 20 seconds - more frequent for OAuth
    token_refresh_interval: int = 1800000  # 30 minutes - proactive token refresh
    connection_check_interval: int = 10000  # 10 seconds - frequent connection checks

    # Additional fields for backward compatibility with existing configurations
    client_id: str | None = None
    authorization_url: str | None = None
    token_url: str | None = None
    type: str | None = None

    def __getitem__(self, key: str) -> Any:
        """Allow dictionary-style access for backward compatibility."""
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        """Allow dictionary-style get method for backward compatibility."""
        return getattr(self, key, default)

    def __contains__(self, key: str) -> bool:
        """Allow 'key in oauth_config' checks."""
        return hasattr(self, key)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for backward compatibility with legacy APIs."""
        return {field_name: field_value for field_name, field_value in self.__dict__.items() if field_value is not None}


@dataclass
class HealthCheckConfig:
    """Configuration for server health checks and monitoring.

    This class defines comprehensive health check settings including
    operation types, intervals, timeouts, and recovery behavior.

    Attributes:
        enabled: Whether health checks are enabled
        interval: Health check interval in milliseconds
        timeout: Health check timeout in milliseconds
        keep_alive_interval: Keep-alive ping interval in milliseconds
        keep_alive_timeout: Keep-alive ping timeout in milliseconds
        max_consecutive_failures: Maximum failures before marking server as failed
        auto_restart: Whether to automatically restart failed servers
        restart_delay: Delay before restart attempt in milliseconds
        max_restart_attempts: Maximum restart attempts before giving up
        operation: MCP operation to use for health checks
        tool_name: Specific tool name if operation is "call_tool"
        tool_arguments: Arguments for tool calls
        resource_uri: Resource URI if operation is "read_resource"
        prompt_name: Prompt name if operation is "get_prompt"
        prompt_arguments: Arguments for prompt calls
        http_path: Custom HTTP path for health checks
        http_method: HTTP method for health checks
        expected_status: Expected HTTP status code
        expected_content: Expected content substring
    """

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
    """Enhanced configuration for a single MCP server in the bridge.

    This class represents the complete configuration for an individual
    MCP server including connection details, authentication, health checks,
    and namespace settings.

    Attributes:
        name: Server name (must be unique)
        enabled: Whether the server is enabled
        command: Command to execute for STDIO servers
        args: Command-line arguments
        env: Environment variables for the server process
        timeout: Server startup timeout in seconds
        transport_type: Transport protocol ("stdio" or "sse")
        url: URL for SSE transport servers
        retry_attempts: Number of connection retry attempts
        retry_delay: Delay between retries in milliseconds
        health_check: Health check configuration
        tool_namespace: Namespace prefix for tools
        resource_namespace: Namespace prefix for resources
        prompt_namespace: Namespace prefix for prompts
        priority: Server priority for conflict resolution
        tags: Server tags for filtering and grouping
        log_level: Logging level for this server
        oauth_config: OAuth configuration dictionary
        authentication: General authentication configuration
        headers: Custom HTTP headers
        verify_ssl: Whether to verify SSL/TLS certificates
        working_directory: Working directory for server process

    Example:
        >>> config = BridgeServerConfig(
        ...     name="filesystem",
        ...     command="npx",
        ...     args=["-y", "@modelcontextprotocol/server-filesystem", "./"],
        ...     transport_type="stdio"
        ... )
        >>> print(f"Server enabled: {config.enabled}")
    """

    name: str
    enabled: bool = True
    command: str = ""
    args: list[str] | None = None
    env: dict[str, str] | None = None
    timeout: int = 60
    transport_type: str = "stdio"
    url: str | None = None  # URL for SSE transport
    retry_attempts: int = 3
    retry_delay: int = 1000  # milliseconds
    health_check: HealthCheckConfig | None = None
    tool_namespace: str | None = None
    resource_namespace: str | None = None
    prompt_namespace: str | None = None
    priority: int = 100
    tags: list[str] | None = None
    log_level: str = "ERROR"  # Default to quiet (only errors)
    oauth_config: OAuthConfig | None = None  # OAuth configuration
    authentication: dict[str, Any] | None = None  # General authentication config
    headers: dict[str, str] | None = None  # Custom headers for HTTP requests
    verify_ssl: bool = True  # SSL/TLS verification for HTTPS connections
    working_directory: str | None = None  # Working directory for server process
    security: "ServerSecurityConfig | None" = None  # Security configuration for this server

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

    def is_oauth_enabled(self) -> bool:
        """Check if OAuth is enabled for this server.

        Returns:
            True if OAuth is enabled, False otherwise

        Example:
            >>> if server.is_oauth_enabled():
            ...     print("OAuth authentication required")
        """
        if self.oauth_config is None:
            return False

        return self.oauth_config.enabled

    def needs_oauth_proxy(self) -> bool:
        """Check if this server needs OAuth proxy routes (not passthrough).

        Returns:
            True if OAuth proxy is needed, False otherwise

        Example:
            >>> if server.needs_oauth_proxy():
            ...     print("Setting up OAuth proxy routes")
        """
        if not self.is_oauth_enabled():
            return False

        # Passthrough OAuth means the server handles its own OAuth flow
        if not self.oauth_config:
            return False
        oauth_type = self.oauth_config.get("type", "proxy")
        result: bool = oauth_type != "passthrough"
        return result


@dataclass
class AggregationConfig:
    """Configuration for capability aggregation.

    Controls which types of capabilities are aggregated from
    multiple servers into the main bridge endpoint.
    """

    tools: bool = True
    resources: bool = True
    prompts: bool = True


@dataclass
class FailoverConfig:
    """Configuration for server failover behavior.

    Controls how the bridge handles server failures and
    recovery operations.
    """

    enabled: bool = True
    max_failures: int = 3
    recovery_interval: int = 60000  # milliseconds


@dataclass
class ConfigReloadConfig:
    """Configuration for dynamic config file reloading.

    Controls whether and how configuration files are
    monitored for changes and reloaded automatically.
    """

    enabled: bool = True
    debounce_ms: int = 1000  # milliseconds
    validate_only: bool = False  # if true, only validate but don't apply changes


@dataclass
class BridgeConfig:
    """Configuration for bridge-specific behavior.

    This class contains all bridge-level settings including
    networking, aggregation, failover, and operational behavior.

    Attributes:
        conflict_resolution: How to handle conflicts between servers
        default_namespace: Whether to use default namespacing
        aggregation: Capability aggregation configuration
        failover: Server failover configuration
        config_reload: Configuration reloading settings
        host: Host address to bind to
        port: Port number to listen on
        mcp_log_level: Default log level for MCP servers
    """

    conflict_resolution: str = "namespace"  # priority, namespace, first, error
    default_namespace: bool = True
    aggregation: AggregationConfig | None = None
    failover: FailoverConfig | None = None
    config_reload: ConfigReloadConfig | None = None
    host: str = "127.0.0.1"  # Default to localhost for security
    port: int = 8080  # Default port
    oauth_port: int = 8090  # Dedicated OAuth port (always consistent, independent of bridge port)
    mcp_log_level: str = "ERROR"  # Default log level for all MCP servers
    allow_command_substitution: bool = False  # Enable command substitution in configuration
    allowed_commands: list[str] | None = None  # Whitelist of allowed commands for substitution
    allow_dangerous_commands: bool = False  # UNSAFE: Allow any command without validation
    read_only_mode: bool = True  # Block write operations when True (defaults to True for security)
    security: "BridgeSecurityConfig | None" = None  # Security configuration for the bridge

    def __post_init__(self) -> None:
        """Initialize default values for bridge configuration."""
        if self.aggregation is None:
            self.aggregation = AggregationConfig()
        if self.failover is None:
            self.failover = FailoverConfig()
        if self.config_reload is None:
            self.config_reload = ConfigReloadConfig()


@dataclass
class BridgeConfiguration:
    """Complete bridge configuration including all servers and bridge settings.

    This is the top-level configuration object that contains all
    server configurations and bridge-level settings.

    Attributes:
        servers: Dictionary of server configurations by name
        bridge: Bridge-level configuration settings

    Example:
        >>> config = BridgeConfiguration(
        ...     servers={"fs": filesystem_config},
        ...     bridge=BridgeConfig(port=8080)
        ... )
        >>> print(f"Bridge has {len(config.servers)} servers")
    """

    servers: dict[str, BridgeServerConfig]
    bridge: BridgeConfig | None = None

    def __post_init__(self) -> None:
        """Initialize default bridge configuration."""
        if self.bridge is None:
            self.bridge = BridgeConfig()


# Utility functions for configuration processing


def normalize_server_name(server_name: str) -> str:
    """Normalize server name for URL-safe usage.

    Converts server names to lowercase, replaces spaces and special characters
    with underscores, and ensures the name is URL-safe for use in endpoints.

    Args:
        server_name: The original server name from configuration

    Returns:
        Normalized server name suitable for URLs

    Example:
        >>> normalize_server_name("File System")
        'file_system'
        >>> normalize_server_name("Example API")
        'example_api'
        >>> normalize_server_name("My_Special Server!")
        'my_special_server'
    """
    # Convert to lowercase
    normalized = server_name.lower()

    # Replace spaces, hyphens, and other non-alphanumeric chars with underscores
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)

    # Remove leading/trailing underscores
    normalized = normalized.strip("_")

    # Ensure we don't have empty string or just underscores
    if not normalized or normalized == "_":
        normalized = "unnamed_server"

    return normalized


def expand_environment_variables(value: Any) -> Any:
    """Recursively expand environment variables and command substitutions.

    Supports both ${VAR_NAME:default} syntax for environment variables
    and $(command) syntax for secure command substitution.

    Args:
        value: The configuration value to expand (str, dict, list, or other)

    Returns:
        The value with environment variables and command substitutions expanded

    Example:
        >>> os.environ["API_KEY"] = "secret123"
        >>> expand_environment_variables("${API_KEY}")
        'secret123'
        >>> expand_environment_variables("${MISSING:default}")
        'default'
        >>> expand_environment_variables("$(echo hello)")
        'hello'
    """
    return expand_env_vars(value)


# Command substitution with security validation


def get_default_allowed_commands() -> set[str]:
    """Get the default set of allowed commands for command substitution.

    Returns:
        Set of command names that are considered safe for read-only operations
    """
    return {
        # Basic safe output commands
        "echo",
        "printf",
        # Date/time (read-only)
        "date",
        # Environment info (read-only)
        "whoami",
        "hostname",
        "pwd",
        "uname",
        # Secret management tools (read-only operations only)
        "op",  # 1Password CLI
        "vault",  # HashiCorp Vault
        # Base64 encoding/decoding
        "base64",
        # JSON processing (safe)
        "jq",
        # Environment variable expansion
        "printenv",
        # Git operations (read-only)
        "git",
        # GitHub CLI (read-only operations)
        "gh",
        # Text processing (read-only)
        "grep",
        "cat",
        "head",
        "tail",
        # Network tools (read-only)
        "curl",
        "wget",
    }


def validate_command_security(
    cmd_parts: list[str], allowed_commands: set[str] | None = None, allow_dangerous: bool | None = None
) -> None:
    """Validate command using an allow list approach for maximum security.

    Only explicitly allowed commands can be executed in command substitution.
    This prevents accidental execution of dangerous operations.

    Args:
        cmd_parts: List of command parts from shlex.split()
        allowed_commands: Set of allowed commands, defaults to safe read-only commands
        allow_dangerous: If True, skip all security validation (UNSAFE!)

    Raises:
        ValueError: If command is not in the allow list

    Example:
        >>> validate_command_security(["echo", "hello"])  # OK
        >>> validate_command_security(["rm", "-rf", "/"])  # Raises ValueError
    """
    if not cmd_parts:
        return

    # Validate command length to prevent resource exhaustion
    full_command_string = " ".join(cmd_parts)
    if len(full_command_string) > MAX_COMMAND_LENGTH:
        raise ValueError("Command too long")

    # Validate individual argument lengths
    for arg in cmd_parts:
        if len(arg) > MAX_ARG_LENGTH:
            raise ValueError("Command validation failed")

    # Check for dangerous commands bypass (UNSAFE MODE)
    if allow_dangerous is None:
        allow_dangerous = os.getenv("MCP_ALLOW_DANGEROUS_COMMANDS", "false").lower() in ("true", "1", "yes", "on")

    if allow_dangerous:
        logger.warning(f"UNSAFE MODE: Allowing potentially dangerous command without validation: {' '.join(cmd_parts)}")
        return  # Skip all validation!

    command = cmd_parts[0].lower()

    # Use provided allowed commands or get default safe commands
    if allowed_commands is None:
        allowed_commands = get_default_allowed_commands()
    else:
        # Convert to lowercase for comparison
        allowed_commands = {cmd.lower() for cmd in allowed_commands}

    # Also check environment variable for additional commands
    env_commands = os.getenv("MCP_ALLOWED_COMMANDS", "")
    if env_commands:
        # Add environment variable commands to the allowed set
        additional_commands = {cmd.strip().lower() for cmd in env_commands.split(",") if cmd.strip()}
        allowed_commands = allowed_commands.union(additional_commands)

    if command not in allowed_commands:
        raise ValueError(f"Command '{command}' not in allow list")

    # Enhanced validation: check for dangerous arguments
    if command in ["vault", "op"]:
        # Validate that these commands are used in read-only mode
        if "write" in " ".join(cmd_parts).lower() or "delete" in " ".join(cmd_parts).lower():
            raise ValueError(f"Write operations not allowed for {command}")

    full_command_string = " ".join(cmd_parts)

    dangerous_patterns = ["|", "||", "&", "&&", ";", "`", ">", ">>", "<", "$()"]
    fork_bomb_patterns = [
        ":()",
        ":bomb:",
        "while true",
        "for((;;))",
        "while(1)",
        "while :;",
        "while :",
        "exec",
        "ulimit -u unlimited",
    ]
    resource_exhaustion_patterns = [
        "dd if=/dev/zero",
        "dd if=/dev/urandom",
        "yes",
        "cat /dev/zero",
        ">/dev/random",
        "mkfifo",
        "nohup",
        "disown",
        "setsid",
        "tail -f /dev/null",
    ]

    for pattern in dangerous_patterns:
        if pattern in full_command_string:
            raise ValueError("Command validation failed")

    for pattern in fork_bomb_patterns:
        if pattern.lower() in full_command_string.lower():
            raise ValueError("Command validation failed")

    for pattern in resource_exhaustion_patterns:
        if pattern.lower() in full_command_string.lower():
            raise ValueError("Command validation failed")

    suspicious_exact = ["sudo", "su", "chmod", "chown"]
    suspicious_substring = ["/bin/", "/usr/bin/", "$(", "`", "/dev/zero", "/dev/random", ">/tmp/", ">>/tmp/"]

    for arg in cmd_parts:
        if arg.lower() in suspicious_exact:
            raise ValueError("Command validation failed")
        for suspicious in suspicious_substring:
            if suspicious in arg.lower():
                raise ValueError("Command validation failed")

    # Validate specific commands for read-only operations
    _validate_command_args(command, cmd_parts)


def _validate_command_args(command: str, cmd_parts: list[str]) -> None:
    """Validate command arguments to ensure read-only operations.

    Args:
        command: The base command (already lowercased)
        cmd_parts: Full command parts including the command itself

    Raises:
        ValueError: If command contains write/destructive operations
    """
    args = [arg.lower() for arg in cmd_parts[1:]]  # Skip the command itself
    args_str = " ".join(args)

    if command == "git":
        # Only allow safe read-only git operations
        allowed_git_ops = {
            "status",
            "log",
            "show",
            "diff",
            "branch",
            "tag",
            "remote",
            "config",
            "rev-parse",
            "ls-files",
            "ls-tree",
            "cat-file",
            "describe",
            "blame",
            "shortlog",
            "reflog",
            "symbolic-ref",
        }

        if args:
            git_subcommand = args[0]
            if git_subcommand not in allowed_git_ops:
                raise ValueError(
                    f"SECURITY: Git operation '{git_subcommand}' blocked - only read-only git "
                    f"operations allowed to prevent repository modification. "
                    f"Allowed: {', '.join(sorted(allowed_git_ops))}"
                )

        # Check for dangerous flags even in allowed operations
        dangerous_git_flags = ["--force", "-f", "--delete", "-d"]
        for flag in dangerous_git_flags:
            if flag in args:
                raise ValueError(f"Dangerous git flag '{flag}' not allowed")

    elif command == "vault":
        # Only allow read operations
        if not args or args[0] not in ["read", "kv", "list", "auth", "status", "version"]:
            raise ValueError("Only vault read operations allowed (read, kv get, list, auth, status, version)")

        # Additional validation for kv operations
        if len(args) >= 2 and args[0] == "kv" and args[1] not in ["get", "list", "metadata"]:
            raise ValueError("Only vault kv read operations allowed (get, list, metadata)")

        # Check for write/delete flags
        write_flags = ["put", "delete", "destroy", "undelete", "patch"]
        if any(flag in args_str for flag in write_flags):
            raise ValueError("Vault write/delete operations not allowed")

    elif command == "op":
        # 1Password CLI - only allow read operations
        if not args or args[0] not in ["read", "get", "list", "whoami", "signin", "signout"]:
            raise ValueError(
                "SECURITY: 1Password operation blocked - only read-only operations "
                "allowed to prevent credential modification. Allowed: read, get, list, whoami, signin, signout"
            )

        # Check for dangerous op flags
        write_flags = ["create", "edit", "delete", "archive", "restore"]
        if any(flag in args for flag in write_flags):
            raise ValueError(
                "SECURITY: 1Password write operation blocked - command substitution only allows "
                "credential reading, not modification"
            )

    elif command == "gh":
        # GitHub CLI - only allow read operations
        if not args:
            return  # `gh` by itself is fine

        read_only_gh_ops = {
            "repo",
            "issue",
            "pr",
            "release",
            "gist",
            "auth",
            "config",
            "status",
            "browse",
            "search",
            "api",
            "alias",
            "completion",
        }

        gh_subcommand = args[0]
        if gh_subcommand not in read_only_gh_ops:
            raise ValueError(
                f"SECURITY: GitHub CLI operation '{gh_subcommand}' blocked - only read-only "
                f"operations allowed to prevent repository/issue modification. "
                f"Allowed: {', '.join(sorted(read_only_gh_ops))}"
            )

        # Check for write flags even in allowed operations
        if len(args) > 1:
            write_flags = ["create", "edit", "delete", "close", "merge", "reopen"]
            if any(flag in args[1:] for flag in write_flags):
                raise ValueError(
                    "SECURITY: GitHub CLI write operation blocked - command substitution only allows "
                    "reading repository/issue data, not modification"
                )

    elif command in {"curl", "wget"}:
        # Network tools - check for upload/POST operations
        if any(flag in args for flag in ["-X", "--request", "--data", "--upload-file", "-T", "--form", "-F"]):
            raise ValueError(
                f"SECURITY: {command.title()} upload/POST operation blocked - command substitution "
                "only allows safe data retrieval, not data transmission"
            )

    elif command == "cat":
        # Ensure we're not trying to write (though cat typically can't write)
        if ">" in args_str or ">>" in args_str:
            raise ValueError("File write operations not allowed with cat")


def execute_command_substitution(
    command: str, allow_substitution: bool | None = None, allowed_commands: set[str] | None = None
) -> str:
    """Execute a command and return its output for command substitution.

    Args:
        command: The command to execute
        allow_substitution: Override to allow/disallow substitution, if None uses env var
        allowed_commands: Set of allowed commands for security validation

    Returns:
        The command output with trailing whitespace stripped

    Raises:
        ValueError: If command execution fails or contains dangerous operations

    Example:
        >>> execute_command_substitution("echo hello")
        'hello'
        >>> execute_command_substitution("date +%Y")
        '2024'
    """
    # Check if command substitution is allowed
    if allow_substitution is None:
        # Fall back to environment variable
        env_substitution = os.getenv("MCP_ALLOW_COMMAND_SUBSTITUTION", "false").lower()
        substitution_allowed = env_substitution in ("true", "1", "yes", "on")
    else:
        substitution_allowed = allow_substitution

    if not substitution_allowed:
        raise ValueError(
            "Command substitution is disabled by default for security. "
            "Set MCP_ALLOW_COMMAND_SUBSTITUTION=true to enable."
        )

    try:
        # Validate command length before parsing
        if len(command) > MAX_COMMAND_LENGTH:
            raise ValueError("Command too long")

        # Parse command safely using shlex
        cmd_parts = shlex.split(command)
        if not cmd_parts:
            raise ValueError("Empty command in substitution")

        # Validate command for security issues
        validate_command_security(cmd_parts, allowed_commands)

        # Execute command with security considerations
        # S603: subprocess call with shell=False is safe with validated commands
        # S602: shell=False prevents shell injection, cmd_parts are validated above
        result = subprocess.run(  # noqa: S603
            cmd_parts,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT,  # 30 second timeout
            check=True,
            shell=False,  # Explicitly disable shell for security
            env=os.environ.copy(),  # Inherit current environment
        )

        # Return output with trailing whitespace stripped
        output = result.stdout.rstrip()
        logger.debug(
            "Command substitution '%s' completed successfully (%d chars)",
            _sanitize_command_for_logging(command),
            len(output),
        )
        return output

    except subprocess.TimeoutExpired as e:
        error_msg = f"Command substitution timed out: {_sanitize_command_for_logging(command)}"
        logger.exception("Command substitution timed out: %s", _sanitize_command_for_logging(command))
        raise ValueError(error_msg) from e
    except subprocess.CalledProcessError as e:
        error_msg = f"Command substitution failed: {_sanitize_command_for_logging(command)} (exit code {e.returncode})"
        if e.stderr:
            logger.debug("Command substitution stderr available (%d chars)", len(e.stderr.strip()))
        logger.exception("Command substitution failed: %s", _sanitize_command_for_logging(command))
        raise ValueError(error_msg) from e
    except (OSError, ValueError) as e:
        error_msg = f"Invalid command substitution: {_sanitize_command_for_logging(command)} - {e}"
        logger.exception("Invalid command substitution: %s", _sanitize_command_for_logging(command))
        raise ValueError(error_msg) from e


def expand_env_vars(
    value: Any, allow_command_substitution: bool | None = None, allowed_commands: set[str] | None = None
) -> Any:
    """Recursively expand environment variables and command substitutions in configuration values.

    Supports:
    - ${VAR_NAME} syntax with optional defaults: ${VAR_NAME:default_value}
    - $(command) syntax for command substitution (bash-style)

    Args:
        value: The configuration value to expand (can be str, dict, list, or other)
        allow_command_substitution: Override to allow/disallow command substitution
        allowed_commands: Set of allowed commands for security validation

    Returns:
        The value with environment variables and command substitutions expanded
    """
    if isinstance(value, str):
        # First expand command substitutions $(command)
        cmd_pattern = r"\$\(([^)]+)\)"

        def replace_command(match: re.Match[str]) -> str:
            command = match.group(1).strip()
            original_match = match.group(0)  # Full original match including $()
            logger.debug(f"Executing command substitution: {command}")
            try:
                return execute_command_substitution(command, allow_command_substitution, allowed_commands)
            except ValueError as e:
                # Log the error but return the original substitution pattern unchanged
                # This allows the bridge to continue running with non-critical command failures
                logger.warning(
                    f"Command substitution failed for '{command}': {e}. "
                    "Leaving pattern unchanged to allow bridge to continue."
                )
                # Return the original pattern so users can see what failed
                return original_match
            except Exception:
                # Handle any unexpected errors
                logger.exception(
                    f"Unexpected error in command substitution for '{command}'. "
                    "Leaving pattern unchanged to allow bridge to continue."
                )
                return original_match

        # Apply command substitutions first
        value = re.sub(cmd_pattern, replace_command, value)

        # Then expand environment variables ${VAR_NAME} or ${VAR_NAME:default}
        env_pattern = r"\$\{([^}:]+)(?::([^}]*))?\}"

        def replace_env_var(match: re.Match[str]) -> str:
            var_name = match.group(1)
            default_value = match.group(2) if match.group(2) is not None else ""
            env_value = os.getenv(var_name, default_value)

            if env_value == "" and match.group(2) is None:
                logger.warning(f"Environment variable '{var_name}' not found and no default provided")

            return env_value

        return re.sub(env_pattern, replace_env_var, value)

    if isinstance(value, dict):
        return {k: expand_env_vars(v, allow_command_substitution, allowed_commands) for k, v in value.items()}

    if isinstance(value, list):
        return [expand_env_vars(item, allow_command_substitution, allowed_commands) for item in value]

    return value


# Configuration validation functions


def validate_server_config(name: str, server_config: dict[str, Any]) -> list[str]:
    """Validate individual server configuration and return list of warnings.

    Args:
        name: The server name
        server_config: The server configuration to validate

    Returns:
        List of warning messages

    Example:
        >>> config = {"command": "python", "args": ["server.py"]}
        >>> warnings = validate_server_config("test", config)
        >>> if not warnings:
        ...     print("Configuration is valid")
    """
    warnings = []

    # Check required fields based on transport type
    transport_type = server_config.get("transport", "stdio")

    if transport_type == "stdio":
        if not server_config.get("command"):
            warnings.append(f"Server '{name}' missing required 'command' field for stdio transport")
    elif transport_type in ["sse", "http"] and not server_config.get("url"):
        warnings.append(f"Server '{name}' missing required 'url' field for {transport_type} transport")

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
        warnings.append(f"Server '{name}' has invalid 'retryAttempts' value (must be non-negative integer)")

    retry_delay = server_config.get("retryDelay", 1000)
    if not isinstance(retry_delay, (int, float)) or retry_delay < 0:
        warnings.append(f"Server '{name}' has invalid 'retryDelay' value (must be non-negative number)")

    # Check priority
    priority = server_config.get("priority", 100)
    if not isinstance(priority, (int, float)) or priority < 0:
        warnings.append(f"Server '{name}' has invalid 'priority' value (must be non-negative number)")

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
            warnings.append(f"Server '{name}' has invalid '{namespace_field}' value (must be string)")
        elif namespace is not None and not namespace.strip():
            warnings.append(f"Server '{name}' has empty '{namespace_field}' value")

    # Validate health check configuration
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
                warnings.append(f"Server '{name}' has invalid healthCheck.{field} value (must be >= {min_val})")

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
                f"Server '{name}' has invalid healthCheck.operation '{operation}' (must be one of {valid_operations})"
            )

        # Validate operation-specific requirements
        if operation == "call_tool" and not health_check.get("toolName"):
            warnings.append(f"Server '{name}' healthCheck operation 'call_tool' requires 'toolName'")
        elif operation == "read_resource" and not health_check.get("resourceUri"):
            warnings.append(f"Server '{name}' healthCheck operation 'read_resource' requires 'resourceUri'")
        elif operation == "get_prompt" and not health_check.get("promptName"):
            warnings.append(f"Server '{name}' healthCheck operation 'get_prompt' requires 'promptName'")

        # Validate HTTP-specific fields
        http_method = health_check.get("httpMethod", "GET")
        if http_method not in ["GET", "POST", "PUT", "HEAD"]:
            warnings.append(f"Server '{name}' has invalid healthCheck.httpMethod '{http_method}'")

        expected_status = health_check.get("expectedStatus", 200)
        if expected_status is not None and (expected_status < 100 or expected_status > 599):
            warnings.append(
                f"Server '{name}' has invalid healthCheck.expectedStatus '{expected_status}' (must be 100-599)"
            )

    return warnings


def normalize_server_config(server_config: dict[str, Any]) -> dict[str, Any]:
    """Normalize server configuration with default values.

    Args:
        server_config: Raw server configuration

    Returns:
        Normalized server configuration with defaults applied

    Example:
        >>> config = {"command": "python"}
        >>> normalized = normalize_server_config(config)
        >>> print(normalized["enabled"])  # True (default)
    """
    normalized = server_config.copy()

    # Apply defaults
    normalized.setdefault("enabled", True)
    normalized.setdefault("args", [])
    normalized.setdefault("env", {})
    normalized.setdefault("timeout", 60)
    normalized.setdefault("transport_type", "stdio")
    normalized.setdefault("retry_attempts", 3)
    normalized.setdefault("retry_delay", 1000)
    normalized.setdefault("priority", 100)
    normalized.setdefault("tags", [])
    normalized.setdefault("log_level", "ERROR")
    normalized.setdefault("verify_ssl", True)

    return normalized


# Main configuration loading functions


def load_bridge_config(
    config_file_path: str, base_env: dict[str, str] | None = None, allow_command_substitution: bool | None = None
) -> BridgeConfiguration:
    """Load bridge configuration from file.

    Convenience function for loading configuration without creating a ConfigLoader instance.

    Args:
        config_file_path: Path to the JSON configuration file
        base_env: Base environment variables (defaults to empty dict)
        allow_command_substitution: Whether to allow command substitution (overrides config file setting)

    Returns:
        BridgeConfiguration object with all settings

    Example:
        >>> config = load_bridge_config("config.json")
        >>> print(f"Loaded {len(config.servers)} servers")
    """
    return load_bridge_config_from_file(config_file_path, base_env or {}, allow_command_substitution)


def load_bridge_config_from_file(
    config_file_path: str, base_env: dict[str, str], allow_command_substitution: bool | None = None
) -> BridgeConfiguration:
    """Load enhanced bridge configuration from a JSON file.

    This is the main configuration loading function that handles file parsing,
    environment variable expansion, validation, and object creation.

    Args:
        config_file_path: Path to the JSON configuration file
        base_env: The base environment dictionary to be inherited by servers
        allow_command_substitution: Override for command substitution setting

    Returns:
        A BridgeConfiguration object with all server and bridge settings

    Raises:
        FileNotFoundError: If the config file is not found
        json.JSONDecodeError: If the config file contains invalid JSON
        ValueError: If the config file format is invalid

    Example:
        >>> config = load_bridge_config_from_file("config.json", {"DEBUG": "1"})
        >>> for name, server in config.servers.items():
        ...     print(f"Server: {name}, Enabled: {server.enabled}")
    """
    logger.info(f"Loading bridge configuration from: {config_file_path}")

    # Ensure schema is available in config directory for IDE support
    _ensure_config_schema()

    # Load and parse JSON file
    try:
        with Path(config_file_path).open() as f:
            config_data = json.load(f)
    except FileNotFoundError:
        logger.exception(f"Configuration file not found: {config_file_path}")
        raise
    except json.JSONDecodeError:
        logger.exception(f"Error decoding JSON from configuration file: {config_file_path}")
        raise
    except Exception as e:
        logger.exception(f"Unexpected error opening or reading configuration file {config_file_path}")
        error_message = f"Could not read configuration file: {e}"
        raise ValueError(error_message) from e

    if not isinstance(config_data, dict) or "mcpServers" not in config_data:
        msg = f"Invalid config file format in {config_file_path}. Missing 'mcpServers' key."
        logger.error(msg)
        raise ValueError(msg)

    # Ensure config has schema reference for IDE support
    schema_updated = _ensure_schema_reference(config_file_path, config_data)

    # Migrate legacy oauth field names
    oauth_migrated = _migrate_oauth_fields(config_data)

    # If either migration happened, reload to get the current state and apply all changes
    if schema_updated or oauth_migrated:
        # Reload to get schema reference that was written to disk
        try:
            with Path(config_file_path).open() as f:
                temp_config = json.load(f)

            # Apply oauth migration to the reloaded config (in case schema was updated)
            if oauth_migrated:
                _migrate_oauth_fields(temp_config)

            # Write the complete updated config
            _write_config_to_disk(config_file_path, temp_config)
            config_data = temp_config
        except Exception as e:
            logger.warning(f"Failed to consolidate migrations: {e}")

    # Reload config from disk if it was modified to ensure we have the updated version
    config_needs_reload = schema_updated or oauth_migrated
    if config_needs_reload:
        logger.debug("Reloading config from disk after migrations to prevent expansion persistence bug")
        try:
            with Path(config_file_path).open() as f:
                config_data = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to reload config after migrations: {e}")

    # CRITICAL: Preserve original config data to prevent expansions from being persisted to disk
    original_config_data = json.loads(json.dumps(config_data))

    # Load bridge configuration settings
    bridge_config = _load_bridge_settings(config_data, allow_command_substitution)
    logger.debug(f"Bridge config loaded: substitution={bridge_config.allow_command_substitution}")

    # Expand environment variables for internal use only
    logger.debug("Expanding environment variables in server configurations")
    default_allowed_commands = get_default_allowed_commands()
    expanded_config_data = expand_env_vars(
        config_data, bridge_config.allow_command_substitution, default_allowed_commands
    )

    # Validate configuration against schema
    try:
        validate_bridge_config(expanded_config_data)
    except ValueError:
        logger.exception(f"Configuration validation failed for {config_file_path}")
        raise

    # Load server configurations with expanded variables
    servers, config_updated, name_mappings = _load_server_configurations(
        expanded_config_data, config_file_path, base_env
    )

    # Save normalized config if server names were updated (use original data to preserve expansions)
    if config_updated:
        _apply_server_name_mappings(original_config_data, name_mappings)
        _save_normalized_config(original_config_data, config_file_path)

    # Show warning if dangerous commands are enabled via config
    if bridge_config.allow_dangerous_commands:
        logger.warning("DANGER: UNSAFE MODE ENABLED via configuration!")
        logger.warning("'allow_dangerous_commands: true' found in bridge config")
        logger.warning("Command substitution validation is DISABLED!")
        logger.warning("Any command can execute including rm, curl uploads, etc.")
        logger.warning("Only use this for testing/development environments!")

    return BridgeConfiguration(servers=servers, bridge=bridge_config)


def _load_bridge_settings(config_data: dict[str, Any], allow_command_substitution: bool | None = None) -> BridgeConfig:
    """Load bridge configuration settings from config data.

    Args:
        config_data: The full configuration dictionary
        allow_command_substitution: CLI override for command substitution setting

    Returns:
        BridgeConfig object with all bridge settings
    """
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

    # Parse config reload config
    config_reload_data = bridge_data.get("configReload", {})
    config_reload = ConfigReloadConfig(
        enabled=config_reload_data.get("enabled", False),
        debounce_ms=config_reload_data.get("debounceMs", 1000),
        validate_only=config_reload_data.get("validateOnly", False),
    )

    # Get command substitution setting - CLI parameter overrides config file, then env var, then default False
    config_allow_substitution = bridge_data.get("allow_command_substitution", False)

    if allow_command_substitution is not None:
        # CLI parameter takes highest priority
        effective_allow_substitution = allow_command_substitution
    elif config_allow_substitution:
        # Config file setting takes second priority
        effective_allow_substitution = config_allow_substitution
    else:
        # Fall back to environment variable as third priority
        env_substitution = os.getenv("MCP_ALLOW_COMMAND_SUBSTITUTION", "false").lower()
        effective_allow_substitution = env_substitution in ("true", "1", "yes", "on")

    return BridgeConfig(
        conflict_resolution=bridge_data.get("conflictResolution", "namespace"),
        default_namespace=bridge_data.get("defaultNamespace", True),
        aggregation=aggregation,
        failover=failover,
        config_reload=config_reload,
        host=bridge_data.get("host", "127.0.0.1"),
        port=bridge_data.get("port", 8080),
        oauth_port=bridge_data.get("oauth_port", bridge_data.get("port", 8080)),
        mcp_log_level=bridge_data.get("mcp_log_level", "ERROR"),
        allow_command_substitution=effective_allow_substitution,
        allowed_commands=bridge_data.get("allowed_commands"),
        allow_dangerous_commands=bridge_data.get("allow_dangerous_commands", False),
        read_only_mode=bridge_data.get("read_only_mode", True),
        security=_load_bridge_security_config(bridge_data.get("security", {})),
    )


def _load_bridge_security_config(security_data: dict[str, Any]) -> "BridgeSecurityConfig | None":
    """Load bridge security configuration from config data.

    Args:
        security_data: Security configuration dictionary

    Returns:
        BridgeSecurityConfig object or None if no security config
    """
    if not security_data:
        return None

    from mcp_foxxy_bridge.security.config import BridgeSecurityConfig, ToolSecurityConfig  # noqa: PLC0415

    # Load tool security config if present
    tool_config = None
    if "tool_security" in security_data:
        tool_data = security_data["tool_security"]
        tool_config = ToolSecurityConfig(
            allow_patterns=tool_data.get("allow_patterns", []),
            block_patterns=tool_data.get("block_patterns", []),
            allow_tools=tool_data.get("allow_tools", []),
            block_tools=tool_data.get("block_tools", []),
            classification_overrides=tool_data.get("classification_overrides", {}),
        )

    return BridgeSecurityConfig(
        read_only_mode=security_data.get("read_only_mode", True),
        tools=tool_config,
    )


def _load_server_configurations(
    config_data: dict[str, Any], config_file_path: str, base_env: dict[str, str]
) -> tuple[dict[str, BridgeServerConfig], bool, dict[str, str]]:
    """Load and parse server configurations from config data.

    Args:
        config_data: The full configuration dictionary with expanded variables
        config_file_path: Path to config file for error reporting
        base_env: Base environment variables for servers

    Returns:
        Tuple of (server configs dict, config_updated flag, name_mappings dict)
    """
    servers = {}
    config_updated = False
    mcp_servers = config_data.get("mcpServers", {})
    normalized_servers = {}
    name_mappings = {}  # Track original_name -> normalized_name mappings

    for name, server_config in mcp_servers.items():
        if not isinstance(server_config, dict):
            logger.warning(
                f"Skipping invalid server config for '{name}' in {config_file_path}. Entry is not a dictionary."
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

        # Normalize server name for consistency with OAuth token storage
        from mcp_foxxy_bridge.oauth.utils import _validate_server_name  # noqa: PLC0415

        normalized_name = _validate_server_name(name)

        # Track if server name was normalized (changed)
        if normalized_name != name:
            config_updated = True
            logger.debug(f"Normalized server name '{name}' -> '{normalized_name}'")
            name_mappings[name] = normalized_name

        # Store normalized server config for potential config file update
        normalized_servers[normalized_name] = server_config

        # Create OAuth configuration
        oauth_data = server_config.get("oauth_config", {})
        oauth_config = None
        if oauth_data:
            oauth_config = OAuthConfig(
                enabled=oauth_data.get("enabled", False),
                issuer=oauth_data.get("issuer"),
                verify_ssl=oauth_data.get("verify_ssl", True),
                keep_alive_interval=oauth_data.get("keepAliveInterval", 20000),
                token_refresh_interval=oauth_data.get("tokenRefreshInterval", 1800000),
                connection_check_interval=oauth_data.get("connectionCheckInterval", 10000),
                client_id=oauth_data.get("client_id"),
                authorization_url=oauth_data.get("authorization_url"),
                token_url=oauth_data.get("token_url"),
                type=oauth_data.get("type"),
            )

        # Create server configuration
        server = BridgeServerConfig(
            name=normalized_name,
            enabled=server_config.get("enabled", True),
            command=server_config.get("command", ""),
            args=server_config.get("args", []),
            env=server_env,
            timeout=server_config.get("timeout", 60),
            transport_type=server_config.get("transport", "stdio"),
            url=server_config.get("url"),
            retry_attempts=server_config.get("retryAttempts", 3),
            retry_delay=server_config.get("retryDelay", 1000),
            health_check=health_check,
            tool_namespace=server_config.get("toolNamespace"),
            resource_namespace=server_config.get("resourceNamespace"),
            prompt_namespace=server_config.get("promptNamespace"),
            priority=server_config.get("priority", 100),
            tags=server_config.get("tags", []),
            log_level=server_config.get("log_level", "ERROR"),
            oauth_config=oauth_config,
            authentication=server_config.get("authentication"),
            headers=server_config.get("headers"),
            verify_ssl=server_config.get("verify_ssl", True),
            working_directory=server_config.get("working_directory") or server_config.get("cwd"),
        )

        # Validate required fields based on transport type
        if server.transport_type in ["sse", "http"]:
            if not server.url:
                logger.warning(
                    f"{server.transport_type.upper()} server '{name}' from config is missing 'url'. Skipping."
                )
                continue
        # Default to stdio - requires command
        elif server.transport_type == "stdio" and not server.command:
            logger.warning(f"STDIO server '{name}' from config is missing 'command'. Skipping.")
            continue

        if not isinstance(server.args, list):
            logger.warning(f"Named server '{name}' from config has invalid 'args' (must be a list). Skipping.")
            continue

        servers[normalized_name] = server
        logger.debug(f'MCP Server configured: {name} - "{server.command}" {" ".join(server.args)}')

    return servers, config_updated, name_mappings


def _apply_server_name_mappings(config_data: dict[str, Any], name_mappings: dict[str, str]) -> None:
    """Apply server name normalizations to config data.

    Args:
        config_data: The configuration data to modify
        name_mappings: Dictionary mapping original_name -> normalized_name
    """
    if not name_mappings:
        return

    mcp_servers = config_data.get("mcpServers", {})
    new_mcp_servers = {}

    for original_name, server_config in mcp_servers.items():
        # Use normalized name if available, otherwise keep original
        normalized_name = name_mappings.get(original_name, original_name)
        new_mcp_servers[normalized_name] = server_config

    config_data["mcpServers"] = new_mcp_servers


def _save_normalized_config(config_data: dict[str, Any], config_file_path: str) -> None:
    """Save the config file with normalized server names.

    Args:
        config_data: Updated configuration data with normalized server names
        config_file_path: Path to the config file to update
    """
    try:
        config_path = Path(config_file_path)

        # Create backup of original config
        backup_path = config_path.with_suffix(config_path.suffix + ".backup")
        if config_path.exists() and not backup_path.exists():
            shutil.copy2(config_path, backup_path)
            logger.debug(f"Created backup: {backup_path}")

        # Write normalized config
        with config_path.open("w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)

        # Set secure permissions
        config_path.chmod(0o600)
        logger.debug("Updated config file with normalized server names.")

    except Exception as e:
        logger.warning(f"Failed to save normalized config: {e}")


def validate_bridge_config(config_data: dict[str, Any]) -> None:
    """Validate bridge configuration against JSON schema.

    Args:
        config_data: The configuration data to validate

    Raises:
        ValueError: If the configuration is invalid

    Example:
        >>> config = {"mcpServers": {"fs": {"command": "npx"}}}
        >>> validate_bridge_config(config)  # No exception = valid
    """
    if not JSONSCHEMA_AVAILABLE:
        logger.warning("jsonschema not available, skipping configuration validation")
        return

    # JSON Schema for configuration validation
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
                            "env": {
                                "type": "object",
                                "additionalProperties": {"type": "string"},
                            },
                            "timeout": {"type": "number", "minimum": 1},
                            "transport": {
                                "type": "string",
                                "enum": ["stdio", "sse", "http"],
                            },
                            "url": {"type": "string", "format": "uri"},
                            "retryAttempts": {"type": "number", "minimum": 0},
                            "retryDelay": {"type": "number", "minimum": 0},
                            "priority": {"type": "number", "minimum": 0},
                            "tags": {"type": "array", "items": {"type": "string"}},
                            "headers": {
                                "type": "object",
                                "additionalProperties": {"type": "string"},
                            },
                            "working_directory": {"type": ["string", "null"]},
                        },
                        "anyOf": [
                            {
                                "properties": {"transport": {"const": "stdio"}},
                                "required": ["command"],
                            },
                            {
                                "properties": {"transport": {"const": "sse"}},
                                "required": ["url"],
                            },
                            {
                                "properties": {"transport": {"const": "http"}},
                                "required": ["url"],
                            },
                        ],
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
                    "host": {"type": "string"},
                    "port": {"type": "number", "minimum": 1, "maximum": 65535},
                    "oauth_port": {"type": "number", "minimum": 1, "maximum": 65535},
                    "mcp_log_level": {"type": "string"},
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


# Legacy compatibility functions


def load_named_server_configs_from_file(
    config_file_path: str,
    base_env: dict[str, str],
) -> dict[str, StdioServerParameters]:
    """Load named server configurations in legacy format.

    This function provides compatibility with the original stdio-only
    configuration format for backwards compatibility.

    Args:
        config_file_path: Path to the JSON configuration file
        base_env: The base environment dictionary to be inherited by servers

    Returns:
        A dictionary of named server parameters

    Raises:
        FileNotFoundError: If the config file is not found
        json.JSONDecodeError: If the config file contains invalid JSON
        ValueError: If the config file format is invalid
    """
    # Load the full bridge configuration
    bridge_config = load_bridge_config_from_file(config_file_path, base_env)

    # Convert to legacy format
    return bridge_config_to_stdio_params(bridge_config)


def bridge_config_to_stdio_params(
    bridge_config: BridgeConfiguration,
) -> dict[str, StdioServerParameters]:
    """Convert BridgeConfiguration to the legacy StdioServerParameters format.

    Args:
        bridge_config: The bridge configuration to convert

    Returns:
        A dictionary of named server parameters compatible with existing code

    Example:
        >>> config = load_bridge_config("config.json")
        >>> stdio_params = bridge_config_to_stdio_params(config)
        >>> for name, params in stdio_params.items():
        ...     print(f"Server: {name}, Command: {params.command}")
    """
    stdio_params = {}

    for name, server in bridge_config.servers.items():
        if not server.enabled:
            logger.info(f"Named server '{name}' is disabled. Skipping.")
            continue

        # Only include STDIO servers in legacy format
        if server.transport_type == "stdio":
            stdio_params[name] = StdioServerParameters(
                command=server.command,
                args=server.args or [],
                env=server.env or {},
                cwd=None,
            )

    return stdio_params
