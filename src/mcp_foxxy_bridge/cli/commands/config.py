#
# MCP Foxxy Bridge - Configuration Management Commands
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
"""Configuration management CLI commands."""

import argparse
import json
import logging
import shutil
from pathlib import Path
from typing import Any, cast

import yaml
from rich.console import Console
from rich.prompt import Confirm

from mcp_foxxy_bridge.cli.formatters import ConfigFormatter
from mcp_foxxy_bridge.config.config_loader import load_bridge_config_from_file
from mcp_foxxy_bridge.utils.config_migration import get_config_dir
from mcp_foxxy_bridge.utils.path_security import validate_config_path
from mcp_foxxy_bridge.utils.server_names import find_server_key


async def handle_config_command(
    args: argparse.Namespace,
    config_path: Path,
    config_dir: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Handle configuration management commands."""
    # Check if no subcommand was provided
    if not hasattr(args, "config_command") or args.config_command is None:
        console.print("[yellow]Usage: foxxy-bridge config <command>[/yellow]")
        console.print("Available commands: add, remove, list, show, validate, init, get, set")
        return

    if args.config_command == "add":
        await _config_add(args, config_path, console, logger)
    elif args.config_command == "remove":
        await _config_remove(args, config_path, console, logger)
    elif args.config_command == "list":
        await _config_list(args, config_path, console, logger)
    elif args.config_command == "show":
        await _config_show(args, config_path, console, logger)
    elif args.config_command == "validate":
        await _config_validate(args, config_path, console, logger)
    elif args.config_command == "init":
        await _config_init(args, config_path, console, logger)
    elif args.config_command == "get":
        await _config_get(args, config_path, console, logger)
    elif args.config_command == "set":
        await _config_set(args, config_path, console, logger)
    else:
        console.print(f"[red]Unknown config command: {args.config_command}[/red]")


async def _config_add(
    args: argparse.Namespace,
    config_path: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Add a new MCP server to configuration."""
    try:
        # Load existing configuration
        config = _load_config_safe(config_path, logger)

        # Check if server already exists
        servers = config.get("mcpServers", {})
        if args.name in servers:
            try:
                if not Confirm.ask(f"Server '{args.name}' already exists. Overwrite?"):
                    console.print("[yellow]Operation cancelled[/yellow]")
                    return
            except EOFError:
                console.print(
                    f"[red]Server '{args.name}' already exists. Use --force to overwrite in non-interactive mode.[/red]"
                )
                return

        # Build server configuration
        server_config = {
            "transport": "stdio",
            "command": args.server_command,
        }

        if args.server_args:
            server_config["args"] = args.server_args

        if args.env:
            server_config["env"] = dict(args.env)

        if args.cwd:
            server_config["cwd"] = args.cwd

        if args.tags:
            server_config["tags"] = args.tags

        # OAuth configuration
        if args.oauth:
            oauth_config = {"enabled": True}
            if args.oauth_issuer:
                oauth_config["issuer"] = args.oauth_issuer
            server_config["oauth_config"] = oauth_config

        # Add server to configuration
        servers[args.name] = server_config
        config["mcpServers"] = servers

        # Save configuration
        _save_config(config, config_path, console, logger)

        console.print(f"[green]✓[/green] Added server '[cyan]{args.name}[/cyan]'")
        logger.info(f"Added server '{args.name}' with command '{args.server_command}'")

    except Exception as e:
        console.print(f"[red]Error adding server: {e}[/red]")
        logger.exception("Failed to add server configuration")


async def _config_remove(
    args: argparse.Namespace,
    config_path: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Remove an MCP server from configuration."""
    try:
        # Load existing configuration
        config = _load_config_safe(config_path, logger)
        servers = config.get("mcpServers", {})

        if args.name not in servers:
            console.print(f"[red]Server '{args.name}' not found[/red]")
            return

        # Confirm removal
        if not args.force:
            try:
                if not Confirm.ask(f"Remove server '[cyan]{args.name}[/cyan]'?"):
                    console.print("[yellow]Operation cancelled[/yellow]")
                    return
            except EOFError:
                console.print("[red]Use --force to remove in non-interactive mode[/red]")
                return

        # Remove server
        del servers[args.name]
        config["mcpServers"] = servers

        # Save configuration
        _save_config(config, config_path, console, logger)

        console.print(f"[green]✓[/green] Removed server '[cyan]{args.name}[/cyan]'")
        logger.info(f"Removed server '{args.name}' from configuration")

    except Exception as e:
        console.print(f"[red]Error removing server: {e}[/red]")
        logger.exception("Failed to remove server configuration")


async def _config_list(
    args: argparse.Namespace,
    config_path: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """List configured servers."""
    try:
        config = _load_config_safe(config_path, logger)
        servers = config.get("mcpServers", {})

        if args.format == "json":
            console.print(json.dumps(servers, indent=2))
        elif args.format == "yaml":
            console.print(yaml.dump(servers, default_flow_style=False))  # type: ignore[no-untyped-call]
        else:
            ConfigFormatter.format_servers_table(servers, console)

    except Exception as e:
        console.print(f"[red]Error listing servers: {e}[/red]")
        logger.exception("Failed to list server configurations")


async def _config_show(
    args: argparse.Namespace,
    config_path: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Show configuration details."""
    try:
        config = _load_config_safe(config_path, logger)

        if args.name:
            # Show specific server
            servers = config.get("mcpServers", {})
            if args.name not in servers:
                console.print(f"[red]Server '{args.name}' not found[/red]")
                return

            server_config = {args.name: servers[args.name]}
        else:
            # Show entire configuration
            server_config = config

        if args.format == "json":
            ConfigFormatter.format_config_json(server_config, console)
        else:
            ConfigFormatter.format_config_yaml(server_config, console)

    except Exception as e:
        console.print(f"[red]Error showing configuration: {e}[/red]")
        logger.exception("Failed to show configuration")


async def _config_validate(
    args: argparse.Namespace,
    config_path: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Validate configuration file."""
    try:
        # Try to load configuration
        bridge_config = load_bridge_config_from_file(str(config_path), {})

        console.print("[green]✓[/green] Configuration is valid")

        # Show summary
        servers = bridge_config.servers
        console.print(f"Found {len(servers)} server(s) configured")

        for name, server_config in servers.items():
            status_icon = (
                "🔐"
                if hasattr(server_config, "oauth_config")
                and server_config.oauth_config
                and getattr(server_config.oauth_config, "enabled", False)
                else "🔓"
            )
            transport_type = getattr(server_config, "transport_type", "stdio")
            console.print(f"  {status_icon} {name} ({transport_type})")

    except Exception as e:
        console.print(f"[red]✗[/red] Configuration validation failed: {e}")

        if args.fix:
            console.print("[yellow]Attempting to fix configuration...[/yellow]")
            # TODO: Implement basic fixes like adding missing required fields


async def _config_init(
    args: argparse.Namespace,
    config_path: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Initialize configuration with defaults."""
    try:
        if config_path.exists() and not args.force:
            try:
                if not Confirm.ask("Configuration already exists. Overwrite?"):
                    console.print("[yellow]Operation cancelled[/yellow]")
                    return
            except EOFError:
                console.print(
                    "[red]Configuration already exists. Use --force to overwrite in non-interactive mode[/red]"
                )
                return

        # Create default configuration with absolute schema path
        config_dir = get_config_dir()
        schema_path = config_dir / "bridge_config_schema.json"

        default_config = {
            "$schema": str(schema_path),
            "mcpServers": {
                "filesystem": {
                    "transport": "stdio",
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem", "./"],
                    "tags": ["local", "development"],
                }
            },
            "bridge": {
                "conflictResolution": "namespace",
                "defaultNamespace": True,
                "aggregation": {"tools": True, "resources": True, "prompts": True},
                "host": "127.0.0.1",
                "port": 9000,
            },
        }

        # Ensure config directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Save configuration
        _save_config(default_config, config_path, console, logger)

        console.print(f"[green]✓[/green] Initialized configuration at [cyan]{config_path}[/cyan]")
        console.print("Edit the configuration file to add your MCP servers.")

    except Exception as e:
        console.print(f"[red]Error initializing configuration: {e}[/red]")
        logger.exception("Failed to initialize configuration")


def _load_config_safe(config_path: Path, logger: logging.Logger) -> dict[str, Any]:
    """Load configuration file with error handling."""
    if not config_path.exists():
        logger.info("Configuration file does not exist, creating empty config")
        return {"mcpServers": {}}

    try:
        with config_path.open("r", encoding="utf-8") as f:
            return cast("dict[str, Any]", json.load(f))
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in configuration file: {e}") from e
    except Exception as e:
        raise ValueError(f"Failed to read configuration file: {e}") from e


def _save_config(
    config: dict[str, Any],
    config_path: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Save configuration file with backup."""
    # Create backup if file exists
    if config_path.exists():
        backup_path = config_path.with_suffix(".json.backup")
        try:
            shutil.copy2(config_path, backup_path)
            logger.debug("Created configuration backup")
        except Exception as e:
            logger.warning(f"Failed to create backup: {e}")

    # Ensure directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Write configuration
    try:
        validated_path = validate_config_path(config_path)
        with validated_path.open("w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        # Set secure permissions
        validated_path.chmod(0o600)

    except Exception as e:
        raise ValueError(f"Failed to save configuration: {e}") from e


async def _config_get(
    args: argparse.Namespace,
    config_path: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Get a configuration value by key path."""
    try:
        config = _load_config_safe(config_path, logger)
        value = _get_config_value(config, args.key)

        if value is None:
            console.print(f"[yellow]Configuration key '{args.key}' not found[/yellow]")
        elif isinstance(value, (dict, list)):
            console.print(json.dumps(value, indent=2))
        else:
            console.print(str(value))

    except Exception as e:
        console.print(f"[red]Error getting config value: {e}[/red]")
        logger.exception("Failed to get config value")


async def _config_set(
    args: argparse.Namespace,
    config_path: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Set a configuration value by key path (assumes bridge prefix)."""
    try:
        config = _load_config_safe(config_path, logger)

        # Get key and value from CLI args
        key = args.key
        value = args.value

        # Assume bridge prefix unless key starts with "mcpServers" or other root-level keys
        bridge_key = _normalize_bridge_config_key(key)

        old_value = _get_config_value(config, bridge_key)
        parsed_value = _parse_config_value(value)

        # Set the value
        _set_config_value(config, bridge_key, parsed_value)

        # Save configuration
        _save_config(config, config_path, console, logger)

        console.print(f"[green]✓[/green] Set [bold]{bridge_key}[/bold] = [cyan]{parsed_value}[/cyan]")
        if old_value is not None and old_value != parsed_value:
            console.print(f"[dim]Previous value: {old_value}[/dim]")

    except Exception as e:
        console.print(f"[red]Error setting config value: {e}[/red]")
        logger.exception("Failed to set config value")


async def _config_unset(
    args: argparse.Namespace,
    config_path: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Unset a configuration value by key path (assumes bridge prefix)."""
    try:
        config = _load_config_safe(config_path, logger)

        # Get key from CLI args
        key = args.key

        # Assume bridge prefix unless key starts with "mcpServers" or other root-level keys
        bridge_key = _normalize_bridge_config_key(key)

        old_value = _get_config_value(config, bridge_key)
        if old_value is None:
            console.print(f"[yellow]Key [bold]{bridge_key}[/bold] is not set[/yellow]")
            return

        # Unset the value
        _unset_config_value(config, bridge_key)

        # Save configuration
        _save_config(config, config_path, console, logger)

        console.print(f"[green]✓[/green] Unset [bold]{bridge_key}[/bold]")
        console.print(f"[dim]Previous value: {old_value}[/dim]")

    except Exception as e:
        console.print(f"[red]Error unsetting config value: {e}[/red]")
        logger.exception("Failed to unset config value")


def _normalize_bridge_config_key(key: str) -> str:
    """Normalize a configuration key by adding 'bridge.' prefix for non-root keys.

    Args:
        key: The configuration key to normalize

    Returns:
        The normalized key with 'bridge.' prefix if needed

    Example:
        >>> _normalize_bridge_config_key('port')
        'bridge.port'
        >>> _normalize_bridge_config_key('mcpServers.test')
        'mcpServers.test'
    """
    # Root-level keys that should not be prefixed with "bridge."
    root_keys = {"mcpServers"}

    # If key starts with a root-level key, don't add bridge prefix
    first_part = key.split(".")[0]
    if first_part in root_keys:
        return key

    # If key already starts with "bridge.", don't add prefix
    if key.startswith("bridge."):
        return key

    # Otherwise, assume bridge prefix
    return f"bridge.{key}"


def _get_config_value(config: dict[str, Any], key: str) -> Any:
    """Get a configuration value using dot-notation key path.

    Args:
        config: The configuration dictionary
        key: Dot-notation key path (e.g. 'bridge.read_only_mode')

    Returns:
        The value at the specified key path, or None if not found

    Example:
        >>> config = {'bridge': {'port': 9000}}
        >>> _get_config_value(config, 'bridge.port')
        9000
    """
    keys = key.split(".")
    current = config

    for k in keys:
        if isinstance(current, dict) and k in current:
            current = current[k]
        else:
            return None

    return current


def _set_config_value(config: dict[str, Any], key: str, value: Any) -> None:
    """Set a configuration value using dot-notation key path.

    Args:
        config: The configuration dictionary to modify
        key: Dot-notation key path (e.g. 'bridge.port')
        value: The value to set

    Raises:
        ValueError: If trying to set nested value where parent is not a dict

    Example:
        >>> config = {}
        >>> _set_config_value(config, 'bridge.port', 9000)
        >>> config['bridge']['port']
        9000
    """
    keys = key.split(".")
    current = config

    # Navigate to the parent of the target key
    for k in keys[:-1]:
        if k not in current:
            current[k] = {}
        elif not isinstance(current[k], dict):
            raise ValueError(f"Cannot set nested value: '{k}' is not an object")
        current = current[k]

    # Set the final value
    current[keys[-1]] = value


def _unset_config_value(config: dict[str, Any], key: str) -> None:
    """Remove a configuration value using dot-notation key path.

    Args:
        config: The configuration dictionary to modify
        key: Dot-notation key path (e.g. 'bridge.port')

    Example:
        >>> config = {'bridge': {'port': 9000}}
        >>> _unset_config_value(config, 'bridge.port')
        >>> 'port' in config['bridge']
        False
    """
    keys = key.split(".")
    current = config

    # Navigate to the parent of the target key
    for k in keys[:-1]:
        if k not in current or not isinstance(current[k], dict):
            # Key doesn't exist, nothing to unset
            return
        current = current[k]

    # Remove the final key if it exists
    if keys[-1] in current:
        del current[keys[-1]]


def _parse_config_value(value: str) -> Any:
    """Parse a string value into the appropriate Python type.

    Handles automatic type conversion for:
    - Booleans: 'true'/'false'
    - None values: 'null'/'none'
    - Numbers: integers and floats
    - Arrays: JSON arrays or comma-separated values
    - Objects: JSON objects
    - Strings: fallback for unrecognized formats

    Args:
        value: The string value to parse

    Returns:
        The parsed value in the appropriate Python type

    Example:
        >>> _parse_config_value('true')
        True
        >>> _parse_config_value('9000')
        9000
        >>> _parse_config_value('a,b,c')
        ['a', 'b', 'c']
    """
    # Handle boolean values
    if value.lower() in ("true", "false"):
        return value.lower() == "true"

    # Handle null/none
    if value.lower() in ("null", "none"):
        return None

    # Handle numbers
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        pass

    # Handle arrays (comma-separated or JSON format)
    if value.startswith("[") and value.endswith("]"):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass
    elif "," in value:
        return [item.strip() for item in value.split(",")]

    # Handle objects (JSON format)
    if value.startswith("{") and value.endswith("}"):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass

    # Return as string
    return value


# MCP Server Configuration Functions


async def _mcp_config_set(
    args: argparse.Namespace,
    config_path: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Set a configuration value for a specific MCP server.

    Args:
        args: Command line arguments containing server_name, key, and value
        config_path: Path to the configuration file
        console: Rich console for output
        logger: Logger for error reporting

    Example:
        CLI usage: foxxy-bridge mcp config set filesystem timeout 120
    """
    try:
        config = _load_config_safe(config_path, logger)

        # Get server name, key, and value from CLI args
        input_server_name = args.server_name
        key = args.key
        value = args.value

        # Find actual server key using case-insensitive matching
        servers = config.get("mcpServers", {})
        actual_server_key = find_server_key(servers, input_server_name)
        if actual_server_key is None:
            console.print(f"[red]MCP server '{input_server_name}' not found[/red]")
            console.print("[dim]Use 'foxxy-bridge mcp list' to see available servers[/dim]")
            return

        # Build the full key path for mcpServers using actual server key
        full_key = f"mcpServers.{actual_server_key}.{key}"

        old_value = _get_config_value(config, full_key)
        parsed_value = _parse_config_value(value)

        # Set the value
        _set_config_value(config, full_key, parsed_value)

        # Save configuration
        _save_config(config, config_path, console, logger)

        console.print(f"[green]✓[/green] Set [bold]{actual_server_key}.{key}[/bold] = [cyan]{parsed_value}[/cyan]")
        if old_value is not None and old_value != parsed_value:
            console.print(f"[dim]Previous value: {old_value}[/dim]")

    except Exception as e:
        console.print(f"[red]Error setting MCP server config value: {e}[/red]")
        logger.exception("Failed to set MCP server config value")


async def _mcp_config_get(
    args: argparse.Namespace,
    config_path: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Get a configuration value from a specific MCP server.

    Args:
        args: Command line arguments containing server_name and key
        config_path: Path to the configuration file
        console: Rich console for output
        logger: Logger for error reporting

    Example:
        CLI usage: foxxy-bridge mcp config get filesystem timeout
    """
    try:
        config = _load_config_safe(config_path, logger)

        # Get server name and key from CLI args
        input_server_name = args.server_name
        key = args.key

        # Find actual server key using case-insensitive matching
        servers = config.get("mcpServers", {})
        actual_server_key = find_server_key(servers, input_server_name)
        if actual_server_key is None:
            console.print(f"[red]MCP server '{input_server_name}' not found[/red]")
            console.print("[dim]Use 'foxxy-bridge mcp list' to see available servers[/dim]")
            return

        # Build the full key path for mcpServers using actual server key
        full_key = f"mcpServers.{actual_server_key}.{key}"

        value = _get_config_value(config, full_key)
        if value is None:
            console.print(f"[yellow]Key [bold]{actual_server_key}.{key}[/bold] is not set[/yellow]")
        else:
            console.print(f"[bold]{actual_server_key}.{key}[/bold] = [cyan]{value}[/cyan]")

    except Exception as e:
        console.print(f"[red]Error getting MCP server config value: {e}[/red]")
        logger.exception("Failed to get MCP server config value")


async def _mcp_config_unset(
    args: argparse.Namespace,
    config_path: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Remove a configuration value from a specific MCP server.

    Args:
        args: Command line arguments containing server_name and key
        config_path: Path to the configuration file
        console: Rich console for output
        logger: Logger for error reporting

    Example:
        CLI usage: foxxy-bridge mcp config unset filesystem timeout
    """
    try:
        config = _load_config_safe(config_path, logger)

        # Get server name and key from CLI args
        input_server_name = args.server_name
        key = args.key

        # Find actual server key using case-insensitive matching
        servers = config.get("mcpServers", {})
        actual_server_key = find_server_key(servers, input_server_name)
        if actual_server_key is None:
            console.print(f"[red]MCP server '{input_server_name}' not found[/red]")
            console.print("[dim]Use 'foxxy-bridge mcp list' to see available servers[/dim]")
            return

        # Build the full key path for mcpServers using actual server key
        full_key = f"mcpServers.{actual_server_key}.{key}"

        old_value = _get_config_value(config, full_key)
        if old_value is None:
            console.print(f"[yellow]Key [bold]{actual_server_key}.{key}[/bold] is not set[/yellow]")
            return

        # Unset the value
        _unset_config_value(config, full_key)

        # Save configuration
        _save_config(config, config_path, console, logger)

        console.print(f"[green]✓[/green] Unset [bold]{actual_server_key}.{key}[/bold]")
        console.print(f"[dim]Previous value: {old_value}[/dim]")

    except Exception as e:
        console.print(f"[red]Error unsetting MCP server config value: {e}[/red]")
        logger.exception("Failed to unset MCP server config value")
