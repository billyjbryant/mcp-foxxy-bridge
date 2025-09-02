#
# MCP Foxxy Bridge - Configuration Validation
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
"""Configuration Validation Utilities.

This module provides comprehensive validation functionality for MCP Foxxy Bridge
configurations, including schema validation, constraint checking, and
detailed error reporting.

Key Features:
    - JSON Schema validation for configuration structure
    - Business logic validation for configuration constraints
    - Detailed error reporting with suggestions
    - Validation for different configuration aspects
    - Support for custom validation rules

Example:
    Basic validation:

    >>> errors = validate_bridge_config(config_data)
    >>> if errors:
    ...     for error in errors:
    ...         print(f"Error: {error}")

    Schema validation:

    >>> try:
    ...     validate_config_schema(config_data)
    ...     print("Schema is valid")
    ... except ConfigValidationError as e:
    ...     print(f"Schema error: {e}")
"""

import re
import urllib.parse
from typing import Any

try:
    import jsonschema

    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False

from mcp_foxxy_bridge.utils.logging import get_logger

logger = get_logger(__name__, facility="CONFIG")


class ConfigValidationError(Exception):
    """Exception raised when configuration validation fails.

    This exception provides detailed information about configuration
    validation failures including the specific error, location, and
    suggested fixes.

    Attributes:
        message: Human-readable error message
        path: Path to the configuration element that failed validation
        suggestion: Optional suggestion for fixing the error

    Example:
        >>> try:
        ...     validate_config_schema(config)
        ... except ConfigValidationError as e:
        ...     print(f"Error at {e.path}: {e.message}")
        ...     if e.suggestion:
        ...         print(f"Suggestion: {e.suggestion}")
    """

    def __init__(self, message: str, path: str | None = None, suggestion: str | None = None) -> None:
        """Initialize configuration validation error.

        Args:
            message: Human-readable error message
            path: Path to the configuration element that failed
            suggestion: Optional suggestion for fixing the error
        """
        self.message = message
        self.path = path
        self.suggestion = suggestion

        full_message = message
        if path:
            full_message = f"At {path}: {message}"
        if suggestion:
            full_message += f" (Suggestion: {suggestion})"

        super().__init__(full_message)


class ValidationResult:
    """Container for validation results with errors and warnings.

    This class provides a structured way to collect and report
    validation issues with different severity levels.

    Attributes:
        errors: List of error messages
        warnings: List of warning messages
        is_valid: Whether validation passed (no errors)

    Example:
        >>> result = ValidationResult()
        >>> result.add_error("Missing required field", "servers.fs.command")
        >>> result.add_warning("Deprecated option", "servers.fs.legacy_mode")
        >>> if not result.is_valid:
        ...     print("Validation failed")
    """

    def __init__(self) -> None:
        """Initialize empty validation result."""
        self.errors: list[str] = []
        self.warnings: list[str] = []

    @property
    def is_valid(self) -> bool:
        """Check if validation passed (no errors)."""
        return len(self.errors) == 0

    def add_error(self, message: str, path: str | None = None) -> None:
        """Add an error to the validation result.

        Args:
            message: Error message
            path: Optional path to the problematic configuration element
        """
        if path:
            self.errors.append(f"At {path}: {message}")
        else:
            self.errors.append(message)

    def add_warning(self, message: str, path: str | None = None) -> None:
        """Add a warning to the validation result.

        Args:
            message: Warning message
            path: Optional path to the configuration element
        """
        if path:
            self.warnings.append(f"At {path}: {message}")
        else:
            self.warnings.append(message)

    def merge(self, other: "ValidationResult") -> None:
        """Merge another validation result into this one.

        Args:
            other: Another ValidationResult to merge
        """
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)


# Core validation functions


def validate_bridge_config(config_data: dict[str, Any]) -> list[str]:
    """Validate complete bridge configuration and return list of errors.

    Performs comprehensive validation including schema validation,
    business logic checks, and constraint validation.

    Args:
        config_data: The configuration data to validate

    Returns:
        List of error messages (empty if configuration is valid)

    Example:
        >>> config = {"mcpServers": {"fs": {"command": "npx"}}}
        >>> errors = validate_bridge_config(config)
        >>> if not errors:
        ...     print("Configuration is valid")
    """
    result = ValidationResult()

    # Schema validation
    try:
        validate_config_schema(config_data)
    except ConfigValidationError as e:
        result.add_error(e.message, e.path)

    # Business logic validation
    _validate_business_logic(config_data, result)

    # Constraint validation
    _validate_constraints(config_data, result)

    return result.errors


def validate_config_schema(config_data: dict[str, Any]) -> None:
    """Validate configuration against JSON schema.

    Args:
        config_data: The configuration data to validate

    Raises:
        ConfigValidationError: If schema validation fails

    Example:
        >>> try:
        ...     validate_config_schema(config)
        ...     print("Schema is valid")
        ... except ConfigValidationError as e:
        ...     print(f"Schema error: {e}")
    """
    if not JSONSCHEMA_AVAILABLE:
        logger.warning("jsonschema not available, skipping schema validation")
        return

    schema = _get_configuration_schema()

    try:
        jsonschema.validate(config_data, schema)  # type: ignore[no-untyped-call]
    except jsonschema.ValidationError as e:
        path = ".".join(str(p) for p in e.path) if e.path else "root"
        suggestion = _get_schema_error_suggestion(e)
        raise ConfigValidationError(message=e.message, path=path, suggestion=suggestion) from e
    except Exception as e:
        raise ConfigValidationError(
            message=f"Schema validation failed: {e}",
            suggestion="Check that your configuration file is valid JSON",
        ) from e


def get_validation_errors(config_data: dict[str, Any]) -> ValidationResult:
    """Get comprehensive validation results with errors and warnings.

    Args:
        config_data: The configuration data to validate

    Returns:
        ValidationResult with detailed error and warning information

    Example:
        >>> result = get_validation_errors(config)
        >>> for error in result.errors:
        ...     print(f"ERROR: {error}")
        >>> for warning in result.warnings:
        ...     print(f"WARNING: {warning}")
    """
    result = ValidationResult()

    # Schema validation
    try:
        validate_config_schema(config_data)
    except ConfigValidationError as e:
        result.add_error(e.message, e.path)

    # Business logic validation
    _validate_business_logic(config_data, result)

    # Constraint validation
    _validate_constraints(config_data, result)

    # Additional warnings
    _add_configuration_warnings(config_data, result)

    return result


# Internal validation functions


def _get_configuration_schema() -> dict[str, Any]:
    """Get the JSON schema for configuration validation."""
    return {
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
                            "transport": {"type": "string", "enum": ["stdio", "sse", "http"]},
                            "url": {"type": "string"},
                            "retryAttempts": {"type": "number", "minimum": 0},
                            "retryDelay": {"type": "number", "minimum": 0},
                            "priority": {"type": "number", "minimum": 0},
                            "tags": {"type": "array", "items": {"type": "string"}},
                            "toolNamespace": {"type": "string"},
                            "resourceNamespace": {"type": "string"},
                            "promptNamespace": {"type": "string"},
                            "log_level": {"type": "string"},
                            "verify_ssl": {"type": "boolean"},
                            "oauth_config": {
                                "type": "object",
                                "properties": {
                                    "enabled": {"type": ["boolean", "string"]},
                                    "type": {"type": "string"},
                                    "client_id": {"type": "string"},
                                    "client_secret": {"type": "string"},
                                },
                            },
                            "authentication": {
                                "type": "object",
                                "properties": {
                                    "type": {
                                        "type": "string",
                                        "enum": ["bearer", "api_key", "basic", "custom"],
                                    },
                                    "token": {"type": "string"},
                                    "key": {"type": "string"},
                                    "header": {"type": "string"},
                                    "username": {"type": "string"},
                                    "password": {"type": "string"},
                                    "headers": {
                                        "type": "object",
                                        "additionalProperties": {"type": "string"},
                                    },
                                },
                            },
                            "headers": {
                                "type": "object",
                                "additionalProperties": {"type": "string"},
                            },
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
                    "mcp_log_level": {"type": "string"},
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
                    "configReload": {
                        "type": "object",
                        "properties": {
                            "enabled": {"type": "boolean"},
                            "debounceMs": {"type": "number", "minimum": 100},
                            "validateOnly": {"type": "boolean"},
                        },
                    },
                },
            },
        },
        "required": ["mcpServers"],
    }


def _get_schema_error_suggestion(error: "jsonschema.ValidationError") -> str | None:
    """Get suggestion for fixing schema validation error."""
    if "is not valid under any of the given schemas" in error.message:
        return "Check that stdio servers have 'command' and sse servers have 'url'"
    if "is not one of" in error.message and isinstance(error.schema, dict):
        return f"Valid values are: {', '.join(error.schema.get('enum', []))}"
    if "is not of type" in error.message and isinstance(error.schema, dict):
        expected_type = error.schema.get("type", "unknown")
        return f"Expected type: {expected_type}"
    if "is a required property" in error.message:
        return "Add the missing required field to your configuration"
    if "does not match" in error.message:
        return "Server names must contain only letters, numbers, underscores, and hyphens"
    return None


def _validate_business_logic(config_data: dict[str, Any], result: ValidationResult) -> None:
    """Validate business logic constraints."""
    servers = config_data.get("mcpServers", {})

    # Validate server configurations
    for server_name, server_config in servers.items():
        if not isinstance(server_config, dict):
            result.add_error("Server configuration must be an object", f"mcpServers.{server_name}")
            continue

        _validate_server_business_logic(server_name, server_config, result)

    # Validate bridge configuration
    bridge_config = config_data.get("bridge", {})
    if bridge_config:
        _validate_bridge_business_logic(bridge_config, result)


def _validate_server_business_logic(server_name: str, server_config: dict[str, Any], result: ValidationResult) -> None:
    """Validate business logic for individual server configuration."""
    base_path = f"mcpServers.{server_name}"

    # Transport-specific validation
    transport_type = server_config.get("transport", "stdio")

    if transport_type == "stdio":
        if not server_config.get("command"):
            result.add_error("STDIO servers require a 'command' field", base_path)
    elif transport_type in ["sse", "http"]:
        url = server_config.get("url")
        if not url:
            result.add_error(f"{transport_type.upper()} servers require a 'url' field", base_path)
        elif not _is_valid_url(url):
            result.add_error("Invalid URL format", f"{base_path}.url")

    # Authentication validation
    auth_config = server_config.get("authentication", {})
    if auth_config:
        _validate_authentication_config(auth_config, result, f"{base_path}.authentication")

    # OAuth validation
    oauth_config = server_config.get("oauth_config", {})
    if oauth_config:
        _validate_oauth_config(oauth_config, result, f"{base_path}.oauth_config")

    # Health check validation
    health_check = server_config.get("healthCheck", {})
    if health_check:
        _validate_health_check_config(health_check, result, f"{base_path}.healthCheck")


def _validate_bridge_business_logic(bridge_config: dict[str, Any], result: ValidationResult) -> None:
    """Validate bridge-level business logic."""
    base_path = "bridge"

    # Port validation
    port = bridge_config.get("port")
    if port is not None and port < 1024 and port not in {80, 443}:
        result.add_warning(
            f"Port {port} is a privileged port and may require elevated permissions",
            f"{base_path}.port",
        )

    # Host validation
    host = bridge_config.get("host")
    if host == "0.0.0.0":  # noqa: S104
        result.add_warning(
            "Binding to 0.0.0.0 exposes the bridge to all network interfaces. "
            "Consider using 127.0.0.1 for local-only access.",
            f"{base_path}.host",
        )


def _validate_authentication_config(auth_config: dict[str, Any], result: ValidationResult, base_path: str) -> None:
    """Validate authentication configuration."""
    auth_type = auth_config.get("type")

    if not auth_type:
        result.add_error("Authentication type is required", f"{base_path}.type")
        return

    if auth_type == "bearer":
        if not auth_config.get("token"):
            result.add_error("Bearer authentication requires a 'token' field", base_path)
    elif auth_type == "api_key":
        if not auth_config.get("key"):
            result.add_error("API key authentication requires a 'key' field", base_path)
    elif auth_type == "basic":
        if not auth_config.get("username"):
            result.add_error("Basic authentication requires a 'username' field", base_path)
    elif auth_type == "custom" and not auth_config.get("headers"):
        result.add_error("Custom authentication requires a 'headers' field", base_path)


def _validate_oauth_config(oauth_config: dict[str, Any], result: ValidationResult, base_path: str) -> None:
    """Validate OAuth configuration."""
    enabled = oauth_config.get("enabled")

    if enabled:
        oauth_type = oauth_config.get("type", "proxy")

        if oauth_type == "proxy":
            # Proxy OAuth requires client configuration
            if not oauth_config.get("client_id"):
                result.add_warning("OAuth proxy mode typically requires a 'client_id'", f"{base_path}.client_id")


def _validate_health_check_config(health_check: dict[str, Any], result: ValidationResult, base_path: str) -> None:
    """Validate health check configuration."""
    operation = health_check.get("operation", "list_tools")

    # Operation-specific validation
    if operation == "call_tool" and not health_check.get("toolName"):
        result.add_error("Health check operation 'call_tool' requires 'toolName'", f"{base_path}.toolName")
    elif operation == "read_resource" and not health_check.get("resourceUri"):
        result.add_error(
            "Health check operation 'read_resource' requires 'resourceUri'",
            f"{base_path}.resourceUri",
        )
    elif operation == "get_prompt" and not health_check.get("promptName"):
        result.add_error("Health check operation 'get_prompt' requires 'promptName'", f"{base_path}.promptName")

    # Interval validation
    interval = health_check.get("interval", 30000)
    timeout = health_check.get("timeout", 5000)

    if timeout >= interval:
        result.add_warning(
            f"Health check timeout ({timeout}ms) should be less than interval ({interval}ms)",
            base_path,
        )


def _validate_constraints(config_data: dict[str, Any], result: ValidationResult) -> None:
    """Validate configuration constraints and relationships."""
    servers = config_data.get("mcpServers", {})

    # Check for duplicate server names (case-insensitive)
    server_names_lower = {}
    for server_name in servers:
        lower_name = server_name.lower()
        if lower_name in server_names_lower:
            result.add_error(
                f"Duplicate server name '{server_name}' (case-insensitive)",
                f"mcpServers.{server_name}",
            )
        server_names_lower[lower_name] = server_name

    # Check for port conflicts
    _validate_port_conflicts(servers, result)

    # Check for namespace conflicts
    _validate_namespace_conflicts(servers, result)


def _validate_port_conflicts(servers: dict[str, Any], result: ValidationResult) -> None:
    """Validate for port conflicts between servers."""
    used_ports: dict[int, str] = {}

    for server_name, server_config in servers.items():
        if not isinstance(server_config, dict):
            continue

        # Check for embedded servers that might use ports
        if server_config.get("transport") in ["sse", "http"]:
            url = server_config.get("url", "")
            port = _extract_port_from_url(url)
            if port and port in used_ports:
                result.add_warning(
                    f"Potential port conflict with server '{used_ports[port]}' on port {port}",
                    f"mcpServers.{server_name}.url",
                )
            elif port:
                used_ports[port] = server_name


def _validate_namespace_conflicts(servers: dict[str, Any], result: ValidationResult) -> None:
    """Validate for namespace conflicts between servers."""
    used_namespaces: dict[str, set[str]] = {"tool": set(), "resource": set(), "prompt": set()}

    for server_name, server_config in servers.items():
        if not isinstance(server_config, dict):
            continue

        # Check tool namespace
        tool_ns = server_config.get("toolNamespace")
        if tool_ns:
            if tool_ns in used_namespaces["tool"]:
                result.add_warning(
                    f"Tool namespace '{tool_ns}' is used by multiple servers",
                    f"mcpServers.{server_name}.toolNamespace",
                )
            used_namespaces["tool"].add(tool_ns)

        # Check resource namespace
        resource_ns = server_config.get("resourceNamespace")
        if resource_ns:
            if resource_ns in used_namespaces["resource"]:
                result.add_warning(
                    f"Resource namespace '{resource_ns}' is used by multiple servers",
                    f"mcpServers.{server_name}.resourceNamespace",
                )
            used_namespaces["resource"].add(resource_ns)

        # Check prompt namespace
        prompt_ns = server_config.get("promptNamespace")
        if prompt_ns:
            if prompt_ns in used_namespaces["prompt"]:
                result.add_warning(
                    f"Prompt namespace '{prompt_ns}' is used by multiple servers",
                    f"mcpServers.{server_name}.promptNamespace",
                )
            used_namespaces["prompt"].add(prompt_ns)


def _add_configuration_warnings(config_data: dict[str, Any], result: ValidationResult) -> None:
    """Add additional configuration warnings."""
    servers = config_data.get("mcpServers", {})

    # Warn about insecure configurations
    for server_name, server_config in servers.items():
        if not isinstance(server_config, dict):
            continue

        # SSL verification warning
        if server_config.get("verify_ssl") is False:
            result.add_warning(
                "SSL verification is disabled - this may be insecure",
                f"mcpServers.{server_name}.verify_ssl",
            )

        # Plaintext URLs warning
        url = server_config.get("url", "")
        if (
            url.startswith("http://")
            and not url.startswith("http://localhost")
            and not url.startswith("http://127.0.0.1")
        ):
            result.add_warning(
                "Using HTTP (not HTTPS) for remote server - this may be insecure",
                f"mcpServers.{server_name}.url",
            )

        # Empty environment variables warning
        env = server_config.get("env", {})
        for env_var, env_value in env.items():
            if not env_value:
                result.add_warning(
                    f"Environment variable '{env_var}' has empty value",
                    f"mcpServers.{server_name}.env.{env_var}",
                )


# Utility functions


def _is_valid_url(url: str) -> bool:
    """Check if URL is valid."""
    try:
        parsed = urllib.parse.urlparse(url)
        return all([parsed.scheme, parsed.netloc])
    except (ValueError, TypeError) as e:
        logger.debug("URL parsing error: %s", e)
        return False
    except Exception as e:
        logger.warning("Unexpected URL validation error: %s", str(e))
        return False


def _extract_port_from_url(url: str) -> int | None:
    """Extract port number from URL."""
    try:
        parsed = urllib.parse.urlparse(url)
        return parsed.port
    except (ValueError, TypeError) as e:
        logger.debug("URL port extraction error: %s", e)
        return None
    except Exception as e:
        logger.warning("Unexpected port extraction error: %s", str(e))
        return None


def _is_valid_server_name(name: str) -> bool:
    """Check if server name is valid."""
    return re.match(r"^[a-zA-Z0-9_-]+$", name) is not None
