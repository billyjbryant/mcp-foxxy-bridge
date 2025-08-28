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

import logging
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.prompt import Confirm

from ...config.config_loader import load_bridge_config_from_file
from ..formatters import ConfigFormatter
from .config import _load_config_safe, _save_config


async def handle_mcp_add(
    args: Any,
    config_path: Path,
    config_dir: Path,
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
            server_config["env"] = {key: value for key, value in args.env}

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
            server_config["headers"] = {key: value for key, value in args.headers}

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
        servers[args.name] = server_config
        config["mcpServers"] = servers

        # Save configuration
        _save_config(config, config_path, console, logger)

        console.print(f"[green]✓[/green] Added MCP server '[cyan]{args.name}[/cyan]'")
        logger.info(f"Added MCP server '{args.name}' with transport '{args.transport}'")

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
    """List configured MCP servers."""
    try:
        config = _load_config_safe(config_path, logger)
        servers = config.get("mcpServers", {})

        if args.format == "json":
            import json

            console.print(json.dumps(servers, indent=2))
        elif args.format == "yaml":
            import yaml

            console.print(yaml.dump(servers, default_flow_style=False))  # type: ignore[no-untyped-call]
        else:
            ConfigFormatter.format_servers_table(servers, console)

    except Exception as e:
        console.print(f"[red]Error listing MCP servers: {e}[/red]")
        logger.exception("Failed to list MCP server configurations")


async def handle_mcp_show(
    args: Any,
    config_path: Path,
    config_dir: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
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
    """Handle MCP server restart/reconnect command."""
    try:
        # Load configuration to get bridge port
        import os

        import aiohttp

        config = load_bridge_config_from_file(str(config_path), dict(os.environ))
        if config is None or config.bridge is None:
            console.print("[red]Error: Invalid or missing bridge configuration[/red]")
            return
        bridge_port = config.bridge.port

        server_name = args.server_name

        # Check if server exists in configuration
        if server_name not in config.servers:
            console.print(f"[red]Error: Server '{server_name}' not found in configuration[/red]")
            console.print(f"Available servers: {', '.join(config.servers.keys())}")
            return

        # Make API call to restart the server
        url = f"http://127.0.0.1:{bridge_port}/sse/mcp/{server_name}/reconnect"

        console.print(f"[blue]Restarting MCP server '[cyan]{server_name}[/cyan]'...[/blue]")

        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url) as response:
                    if response.status == 200:
                        result = await response.json()
                        console.print(f"[green]✓[/green] {result.get('message', 'Server restart initiated')}")
                        console.print(f"Server status: [cyan]{result.get('status', 'unknown')}[/cyan]")
                    elif response.status == 404:
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
