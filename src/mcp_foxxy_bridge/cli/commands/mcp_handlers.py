#
# MCP Foxxy Bridge - MCP Server Management Handlers
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
"""MCP server management command handlers."""

import argparse
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiohttp
import yaml
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

from mcp_foxxy_bridge.cli.formatters import ConfigFormatter
from mcp_foxxy_bridge.config.config_loader import load_bridge_config_from_file
from mcp_foxxy_bridge.oauth.utils import _validate_server_name

from .config import _load_config_safe, _save_config


async def handle_mcp_command(
    args: argparse.Namespace,
    config_path: Path,
    config_dir: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Handle MCP server management commands."""
    # Check if no subcommand was provided (this shouldn't happen with Click)
    if not hasattr(args, "mcp_command") or args.mcp_command is None:
        console.print("[yellow]Usage: foxxy-bridge mcp <command>[/yellow]")
        console.print("Available commands: add, remove, list, show, status, restart")
        return

    if args.mcp_command == "add":
        await handle_mcp_add(args, config_path, config_dir, console, logger)
    elif args.mcp_command == "remove":
        await handle_mcp_remove(args, config_path, config_dir, console, logger)
    elif args.mcp_command == "list":
        await handle_mcp_list(args, config_path, config_dir, console, logger)
    elif args.mcp_command == "show":
        await handle_mcp_show(args, config_path, config_dir, console, logger)
    elif args.mcp_command == "status":
        await handle_mcp_status(args, config_path, config_dir, console, logger)
    elif args.mcp_command == "restart":
        await handle_mcp_restart(args, config_path, config_dir, console, logger)
    else:
        console.print(f"[red]Unknown mcp command: {args.mcp_command}[/red]")


async def _try_get_servers_from_api(config_path: Path, logger: logging.Logger) -> dict[str, Any] | None:
    """Try to get server configurations from running bridge API.

    Returns:
        Server configurations dict if API is available, None otherwise
    """
    try:
        # Load bridge config to get port
        config = load_bridge_config_from_file(str(config_path), dict(os.environ))
        if config is None or config.bridge is None:
            return None

        bridge_port = config.bridge.port

        # Try to connect to bridge API
        configured_host = config.bridge.host if config.bridge else "127.0.0.1"
        # If server binds to 0.0.0.0 (all interfaces), connect via localhost
        bridge_host = "127.0.0.1" if configured_host == "0.0.0.0" else configured_host  # noqa: S104
        timeout = aiohttp.ClientTimeout(total=3)  # Quick timeout for API check
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Get server configurations from bridge API
            url = f"http://{bridge_host}:{bridge_port}/sse/servers"
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    servers = data.get("servers", [])

                    # Load config to get actual command/URL details
                    config = load_bridge_config_from_file(str(config_path), dict(os.environ))
                    config_servers = config.servers if config else {}

                    # Convert server list to config format, merging API status with config details
                    server_configs = {}
                    for server in servers:
                        name = server.get("name", "unknown")
                        transport_type = server.get("transport", "stdio")

                        # Get config details for this server
                        server_config = config_servers.get(name)

                        server_configs[name] = {
                            "transport": transport_type,
                            "enabled": server.get("status") != "disabled",
                            "tags": server.get("tags", []),
                        }

                        # Add actual command/URL from config
                        if server_config:
                            if transport_type in ("sse", "http", "streamablehttp"):
                                server_configs[name]["url"] = getattr(server_config, "url", "Unknown")
                            else:
                                server_configs[name]["command"] = getattr(server_config, "command", "Unknown")
                                server_configs[name]["args"] = getattr(server_config, "args", [])

                            # Get OAuth config from actual config
                            oauth_config = getattr(server_config, "oauth_config", None)
                            if oauth_config and getattr(oauth_config, "enabled", False):
                                server_configs[name]["oauth_config"] = {"enabled": True}
                        # Fallback if config not found
                        elif transport_type in ("sse", "http", "streamablehttp"):
                            server_configs[name]["url"] = "Unknown"
                        else:
                            server_configs[name]["command"] = "Unknown"
                            server_configs[name]["args"] = []

                    transports = [(name, cfg.get("transport")) for name, cfg in server_configs.items()]
                    logger.debug(f"Retrieved {len(server_configs)} servers from bridge API, transports: {transports}")
                    return server_configs
                logger.debug(f"Bridge API returned status {response.status}")
                return None

    except (aiohttp.ClientError, OSError) as e:
        logger.debug(f"Bridge API not available: {type(e).__name__}: {e}")
        return None
    except Exception as e:
        logger.debug(f"Failed to get servers from bridge API: {e}")
        return None


async def handle_mcp_add(
    args: Any,
    config_path: Path,
    config_dir: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Add a new MCP server to the configuration.

    Args:
        args: Command line arguments containing server configuration
        config_path: Path to the configuration file
        config_dir: Configuration directory (unused)
        console: Rich console for output
        logger: Logger for error reporting

    Prompts for confirmation if server already exists, unless force flag is used.
    """
    try:
        # Load existing configuration
        config = _load_config_safe(config_path, logger)

        # Normalize server name for consistency
        from mcp_foxxy_bridge.oauth.utils import _validate_server_name  # noqa: PLC0415

        normalized_name = _validate_server_name(args.name)

        if normalized_name != args.name:
            logger.debug(f"Normalized server name '{args.name}' -> '{normalized_name}'")

        # Check if server already exists (case-insensitive)
        servers = config.get("mcpServers", {})
        if normalized_name in servers:
            try:
                if not Confirm.ask(f"Server '{args.name}' already exists. Overwrite?"):
                    console.print("[yellow]Operation cancelled[/yellow]")
                    return
            except EOFError:
                console.print(
                    f"[red]Server '{args.name}' already exists. Use --force to overwrite in non-interactive mode.[/red]"
                )
                return

        # Build server configuration based on transport type
        if args.transport in ("sse", "http", "streamablehttp"):
            if not args.url:
                console.print(f"[red]--url is required for {args.transport} transport[/red]")
                return

            server_config = {
                "transport": args.transport,
                "url": args.url,
            }
        else:
            # stdio transport
            server_config = {
                "transport": "stdio",
                "command": args.server_command,
            }

            if args.server_args:
                server_config["args"] = args.server_args

        # Add common configuration
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

        # Additional server configuration options
        if hasattr(args, "enabled") and args.enabled is not None:
            server_config["enabled"] = args.enabled

        if hasattr(args, "timeout") and args.timeout is not None:
            server_config["timeout"] = args.timeout

        if hasattr(args, "retry_attempts") and args.retry_attempts is not None:
            server_config["retryAttempts"] = args.retry_attempts

        if hasattr(args, "retry_delay") and args.retry_delay is not None:
            server_config["retryDelay"] = args.retry_delay

        if hasattr(args, "health_check") and args.health_check is not None:
            server_config["healthCheck"] = {"enabled": args.health_check}

        if hasattr(args, "tool_namespace") and args.tool_namespace is not None:
            server_config["toolNamespace"] = args.tool_namespace

        if hasattr(args, "resource_namespace") and args.resource_namespace is not None:
            server_config["resourceNamespace"] = args.resource_namespace

        if hasattr(args, "priority") and args.priority is not None:
            server_config["priority"] = args.priority

        if hasattr(args, "log_level") and args.log_level is not None:
            server_config["log_level"] = args.log_level

        # Headers for HTTP/SSE transports
        if hasattr(args, "headers") and args.headers and args.transport in ("sse", "http", "streamablehttp"):
            server_config["headers"] = dict(args.headers)

        # Security configuration
        security_config = {}

        # Read-only mode override
        if hasattr(args, "read_only") and args.read_only is not None:
            security_config["read_only_mode"] = args.read_only

        # Tool security configuration
        tool_security_config = {}
        has_tool_security = False

        if hasattr(args, "allow_patterns") and args.allow_patterns:
            tool_security_config["allow_patterns"] = args.allow_patterns
            has_tool_security = True

        if hasattr(args, "block_patterns") and args.block_patterns:
            tool_security_config["block_patterns"] = args.block_patterns
            has_tool_security = True

        if hasattr(args, "allow_tools") and args.allow_tools:
            tool_security_config["allow_tools"] = args.allow_tools
            has_tool_security = True

        if hasattr(args, "block_tools") and args.block_tools:
            tool_security_config["block_tools"] = args.block_tools
            has_tool_security = True

        if hasattr(args, "classify_tools") and args.classify_tools:
            classification_overrides = {}
            for tool_name, tool_type in args.classify_tools:
                # Input sanitization for tool classifications
                clean_tool_name = str(tool_name).strip()
                clean_tool_type = str(tool_type).strip().lower()
                if clean_tool_name and clean_tool_type in ["read", "write", "unknown"]:
                    classification_overrides[clean_tool_name] = clean_tool_type
            if classification_overrides:
                tool_security_config["classification_overrides"] = classification_overrides
                has_tool_security = True

        if has_tool_security:
            security_config["tool_security"] = tool_security_config

        if security_config:
            server_config["security"] = security_config

        # Add server to configuration
        servers[normalized_name] = server_config
        config["mcpServers"] = servers

        # Save configuration
        _save_config(config, config_path, console, logger)

        console.print(f"[green]✓[/green] Added MCP server '[cyan]{normalized_name}[/cyan]'")
        if normalized_name != args.name:
            console.print(f"[dim]Server name normalized from '{args.name}' to '{normalized_name}'[/dim]")
        logger.info(f"Added MCP server '{normalized_name}' with transport '{args.transport}'")

    except Exception as e:
        console.print(f"[red]Error adding MCP server: {e}[/red]")
        logger.exception("Failed to add MCP server configuration")


async def handle_mcp_remove(
    args: Any,
    config_path: Path,
    config_dir: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Remove an MCP server from the configuration.

    Args:
        args: Command line arguments containing server name and options
        config_path: Path to the configuration file
        config_dir: Configuration directory (unused)
        console: Rich console for output
        logger: Logger for error reporting

    Prompts for confirmation unless force flag is used.
    """
    """Remove an MCP server from configuration."""
    try:
        # Load existing configuration
        config = _load_config_safe(config_path, logger)
        servers = config.get("mcpServers", {})

        if args.name not in servers:
            console.print(f"[red]MCP server '{args.name}' not found[/red]")
            return

        # Confirm removal
        if not args.force:
            try:
                if not Confirm.ask(f"Remove MCP server '[cyan]{args.name}[/cyan]'?"):
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

        console.print(f"[green]✓[/green] Removed MCP server '[cyan]{args.name}[/cyan]'")
        logger.info(f"Removed MCP server '{args.name}' from configuration")

    except Exception as e:
        console.print(f"[red]Error removing MCP server: {e}[/red]")
        logger.exception("Failed to remove MCP server configuration")


async def handle_mcp_list(
    args: Any,
    config_path: Path,
    config_dir: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """List all configured MCP servers.

    Args:
        args: Command line arguments containing format option
        config_path: Path to the configuration file
        config_dir: Configuration directory (unused)
        console: Rich console for output
        logger: Logger for error reporting

    Supports table, JSON, and YAML output formats.
    """
    """List configured MCP servers."""
    # First try to get server list from running bridge API
    servers = await _try_get_servers_from_api(config_path, logger)

    # Fall back to config file if bridge API is not available
    if servers is None:
        logger.debug("Bridge API unavailable, reading from config file")
        try:
            config = _load_config_safe(config_path, logger)
            servers = config.get("mcpServers", {})
        except Exception as e:
            console.print(f"[red]Error loading config file: {e}[/red]")
            logger.exception("Failed to load server configurations from config file")
            return

    if args.format == "json":
        console.print(json.dumps(servers, indent=2))
    elif args.format == "yaml":
        console.print(yaml.dump(servers, default_flow_style=False))  # type: ignore[no-untyped-call]
    else:
        ConfigFormatter.format_servers_table(servers, console)


async def handle_mcp_show(
    args: Any,
    config_path: Path,
    config_dir: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Show detailed configuration for a specific MCP server.

    Args:
        args: Command line arguments containing server name and format
        config_path: Path to the configuration file
        config_dir: Configuration directory (unused)
        console: Rich console for output
        logger: Logger for error reporting

    Supports JSON and YAML output formats for detailed server configuration.
    """
    """Show MCP server configuration details."""
    try:
        config = _load_config_safe(config_path, logger)

        if args.name:
            # Show specific server
            servers = config.get("mcpServers", {})
            if args.name not in servers:
                console.print(f"[red]MCP server '{args.name}' not found[/red]")
                return

            server_config = {args.name: servers[args.name]}
        else:
            # Show all MCP servers
            server_config = {"mcpServers": config.get("mcpServers", {})}

        if args.format == "json":
            ConfigFormatter.format_config_json(server_config, console)
        else:
            ConfigFormatter.format_config_yaml(server_config, console)

    except Exception as e:
        console.print(f"[red]Error showing MCP server configuration: {e}[/red]")
        logger.exception("Failed to show MCP server configuration")


async def handle_config_show(
    args: Any,
    config_path: Path,
    config_dir: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Show the complete bridge configuration.

    Args:
        args: Command line arguments containing format option
        config_path: Path to the configuration file
        config_dir: Configuration directory (unused)
        console: Rich console for output
        logger: Logger for error reporting

    Shows the full bridge configuration including all servers and bridge settings.
    """
    """Show bridge configuration (excluding MCP servers)."""
    try:
        config = _load_config_safe(config_path, logger)

        # Show only bridge configuration, not MCP servers
        bridge_config = {k: v for k, v in config.items() if k != "mcpServers"}

        if args.format == "json":
            ConfigFormatter.format_config_json(bridge_config, console)
        else:
            ConfigFormatter.format_config_yaml(bridge_config, console)

    except Exception as e:
        console.print(f"[red]Error showing bridge configuration: {e}[/red]")
        logger.exception("Failed to show bridge configuration")


async def handle_config_validate(
    args: Any,
    config_path: Path,
    config_dir: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Validate the bridge configuration file.

    Args:
        args: Command line arguments (unused for basic validation)
        config_path: Path to the configuration file
        config_dir: Configuration directory (unused)
        console: Rich console for output
        logger: Logger for error reporting

    Attempts to load and parse the configuration file, reporting any errors.
    Shows a summary of configured servers if validation succeeds.
    """
    """Validate configuration file."""
    try:
        # Try to load configuration
        bridge_config = load_bridge_config_from_file(str(config_path), {})

        console.print("[green]✓[/green] Configuration is valid")

        # Show summary
        servers = bridge_config.servers
        console.print(f"Found {len(servers)} MCP server(s) configured")

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
            console.print("[yellow]Auto-fix not yet implemented[/yellow]")


async def handle_config_init(
    args: Any,
    config_path: Path,
    config_dir: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Initialize a new bridge configuration file with default settings.

    Args:
        args: Command line arguments containing force flag
        config_path: Path where the configuration file will be created
        config_dir: Configuration directory for schema reference
        console: Rich console for output
        logger: Logger for error reporting

    Creates a default configuration with a filesystem server example.
    Prompts for confirmation if file already exists unless force flag is used.
    """
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

        # Create default configuration
        default_config = {
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


async def handle_mcp_restart(
    args: Any,
    config_path: Path,
    config_dir: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Restart a specific MCP server connection.

    Args:
        args: Command line arguments containing server name
        config_path: Path to the configuration file
        config_dir: Configuration directory (unused)
        console: Rich console for output
        logger: Logger for error reporting

    Note: This is a placeholder implementation. Full server restart
    functionality requires bridge API integration.
    """
    try:
        # Load configuration to get bridge port
        config = load_bridge_config_from_file(str(config_path), dict(os.environ))
        if config is None or config.bridge is None:
            console.print("[red]Error: Invalid or missing bridge configuration[/red]")
            return
        bridge_port = config.bridge.port

        # Normalize server name for case-insensitive matching
        server_name = _validate_server_name(args.server_name)

        # Make API call to restart the server (config-agnostic)
        configured_host = config.bridge.host if config.bridge else "127.0.0.1"
        bridge_host = "127.0.0.1" if configured_host == "0.0.0.0" else configured_host  # noqa: S104
        url = f"http://{bridge_host}:{bridge_port}/sse/mcp/{server_name}/reconnect"

        console.print(f"[blue]Restarting MCP server '[cyan]{server_name}[/cyan]'...[/blue]")

        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session, session.post(url) as response:
                if response.status == 200:
                    result = await response.json()
                    console.print(f"[green]✓[/green] {result.get('message', 'Server restart initiated')}")
                    console.print(f"Server status: [cyan]{result.get('status', 'unknown')}[/cyan]")
                elif response.status == 404:
                    # Try to get list of running servers for better error message
                    try:
                        servers_url = f"http://{bridge_host}:{bridge_port}/sse/servers"
                        async with session.get(servers_url) as servers_response:
                            if servers_response.status == 200:
                                servers_data = await servers_response.json()
                                available_servers = [s.get("name", "unknown") for s in servers_data.get("servers", [])]
                                if available_servers:
                                    console.print(f"[red]Error: Server '{server_name}' not found or not running[/red]")
                                    console.print(f"Available running servers: {', '.join(available_servers)}")
                                else:
                                    console.print(f"[red]Error: Server '{server_name}' not found[/red]")
                                    console.print("[yellow]No servers are currently running[/yellow]")
                            else:
                                console.print(f"[red]Error: Server '{server_name}' not found or not running[/red]")
                    except Exception:
                        console.print(f"[red]Error: Server '{server_name}' not found or not running[/red]")
                else:
                    error_text = await response.text()
                    console.print(f"[red]Error restarting server: HTTP {response.status}[/red]")
                    console.print(f"[red]{error_text}[/red]")

        except aiohttp.ClientError as e:
            console.print(f"[red]Error connecting to bridge server on port {bridge_port}: {e}[/red]")
            console.print("[yellow]Make sure the bridge server is running[/yellow]")
        except Exception as e:
            console.print(f"[red]Unexpected error during server restart: {e}[/red]")
            logger.exception("Failed to restart MCP server")

    except Exception as e:
        console.print(f"[red]Error restarting MCP server: {e}[/red]")
        logger.exception("Failed to restart MCP server")


async def handle_mcp_status(
    args: Any,
    config_path: Path,
    config_dir: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Show MCP server status, connection state, and discovered tools.

    Args:
        args: Command line arguments containing optional server name and format
        config_path: Path to the configuration file
        config_dir: Configuration directory (unused)
        console: Rich console for output
        logger: Logger for error reporting

    Shows detailed status information including connection state, tool counts,
    and security information about suppressed tools.
    """
    try:
        # Load configuration to get bridge port
        config = load_bridge_config_from_file(str(config_path), dict(os.environ))
        if config is None or config.bridge is None:
            console.print("[red]Error: Invalid or missing bridge configuration[/red]")
            return
        bridge_port = config.bridge.port

        # Normalize server name if provided
        server_name = _validate_server_name(args.name) if args.name else None

        # Get server status from bridge API
        configured_host = config.bridge.host if config.bridge else "127.0.0.1"
        bridge_host = "127.0.0.1" if configured_host == "0.0.0.0" else configured_host  # noqa: S104
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Get servers list
            servers_url = f"http://{bridge_host}:{bridge_port}/sse/servers"
            try:
                async with session.get(servers_url) as response:
                    if response.status != 200:
                        console.print(f"[red]Error getting server status: HTTP {response.status}[/red]")
                        return
                    servers_data = await response.json()

            except aiohttp.ClientError as e:
                console.print(f"[red]Error connecting to bridge server on port {bridge_port}: {e}[/red]")
                console.print("[yellow]Make sure the bridge server is running[/yellow]")
                return

            servers = servers_data.get("servers", [])

            # Filter by server name if specified
            if server_name:
                servers = [s for s in servers if s.get("name") == server_name]
                if not servers:
                    console.print(f"[red]Server '{server_name}' not found or not running[/red]")
                    available_servers = [s.get("name", "unknown") for s in servers_data.get("servers", [])]
                    if available_servers:
                        console.print(f"Available servers: {', '.join(available_servers)}")
                    return

            if not servers:
                console.print("[yellow]No servers are currently running[/yellow]")
                return

            # Get detailed information for each server
            detailed_servers = []
            for server in servers:
                name = server.get("name", "unknown")
                transport = server.get("transport", "stdio")
                try:
                    # Get tools list for this server
                    tools_url = f"http://{bridge_host}:{bridge_port}/sse/mcp/{name}/list_tools"
                    async with session.get(tools_url) as tools_response:
                        if tools_response.status == 200:
                            tools_data = await tools_response.json()
                            tools = tools_data.get("tools", [])
                            tool_count = len(tools)
                            tool_names = [t.get("name", "") for t in tools]
                        else:
                            tool_count = 0
                            tool_names = []

                    # Get server health status
                    status_url = f"http://{bridge_host}:{bridge_port}/sse/mcp/{name}/status"
                    async with session.get(status_url) as status_response:
                        if status_response.status == 200:
                            status_data = await status_response.json()
                            connection_state = status_data.get("status", "unknown")
                            last_seen = status_data.get("last_seen")
                            if last_seen:
                                dt = datetime.fromtimestamp(last_seen, tz=UTC)
                                last_connected = dt.strftime("%Y-%m-%d %H:%M:%S")
                            else:
                                last_connected = "never"
                            error_count = status_data.get("failure_count", 0)
                            tool_count = status_data.get("tools_count", tool_count)
                        else:
                            connection_state = "error"
                            last_connected = "unknown"
                            error_count = 0

                    detailed_servers.append(
                        {
                            "name": name,
                            "connection_state": connection_state,
                            "last_connected": last_connected,
                            "error_count": error_count,
                            "tool_count": tool_count,
                            "tools": tool_names,
                            "tags": server.get("tags", []),
                            "transport": transport,
                        }
                    )

                except Exception as e:
                    logger.debug(f"Error getting details for server {name}: {e}")
                    detailed_servers.append(
                        {
                            "name": name,
                            "connection_state": "error",
                            "last_connected": "unknown",
                            "error_count": 0,
                            "tool_count": 0,
                            "tools": [],
                            "tags": server.get("tags", []),
                            "transport": server.get("transport", "stdio"),
                        }
                    )

            # Output the results
            if args.format == "json":
                console.print(json.dumps(detailed_servers, indent=2))
            elif args.format == "yaml":
                console.print(yaml.dump(detailed_servers, default_flow_style=False))  # type: ignore[no-untyped-call]
            else:
                # Table format
                table = Table(title="MCP Server Status")
                table.add_column("Server", style="cyan")
                table.add_column("State", style="green")
                table.add_column("Transport", style="blue")
                table.add_column("Tools", justify="right", style="yellow")
                table.add_column("Errors", justify="right", style="red")
                table.add_column("Last Connected", style="dim")

                for server in detailed_servers:
                    state_style = "green" if server["connection_state"] == "connected" else "red"
                    state = f"[{state_style}]{server['connection_state']}[/{state_style}]"

                    error_style = "red" if server["error_count"] > 0 else "dim"
                    errors = f"[{error_style}]{server['error_count']}[/{error_style}]"

                    table.add_row(
                        server["name"],
                        state,
                        server["transport"],
                        str(server["tool_count"]),
                        errors,
                        server["last_connected"],
                    )

                console.print(table)

                # Show tool details if single server
                if len(detailed_servers) == 1:
                    server = detailed_servers[0]
                    if server["tools"]:
                        console.print(f"\n[cyan]Available tools for {server['name']}:[/cyan]")
                        for tool in server["tools"]:
                            console.print(f"  • {tool}")

                    if server["tags"]:
                        console.print(f"\n[blue]Tags:[/blue] {', '.join(server['tags'])}")

    except Exception as e:
        console.print(f"[red]Error getting MCP server status: {e}[/red]")
        logger.exception("Failed to get MCP server status")
