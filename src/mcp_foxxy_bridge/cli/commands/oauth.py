#
# MCP Foxxy Bridge - OAuth Management Commands
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
"""OAuth authentication management CLI commands."""

import argparse
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import aiohttp
from rich.console import Console

from mcp_foxxy_bridge.cli.api_client import get_api_client_from_config
from mcp_foxxy_bridge.cli.formatters import OAuthFormatter
from mcp_foxxy_bridge.config.config_loader import load_bridge_config_from_file


async def handle_oauth_status(
    args: Any,
    config_path: Path,
    config_dir: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Handle OAuth authentication status command from Click CLI.

    Args:
        args: Click command arguments containing server name and format options
        config_path: Path to the configuration file
        config_dir: Configuration directory (unused)
        console: Rich console for output
        logger: Logger for error reporting

    Shows OAuth authentication status for specified server or all servers.
    """
    # Convert to argparse-style namespace for compatibility
    argparse_args = argparse.Namespace(
        oauth_command="status", name=getattr(args, "name", None), format=getattr(args, "format", "table")
    )
    await _oauth_status(argparse_args, config_path, console, logger)


async def handle_oauth_command(
    args: argparse.Namespace,
    config_path: Path,
    config_dir: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Handle OAuth authentication management commands.

    Args:
        args: Command line arguments with oauth_command subcommand
        config_path: Path to the configuration file
        config_dir: Configuration directory (unused)
        console: Rich console for output
        logger: Logger for error reporting

    Routes to appropriate OAuth subcommand handler (status, login, logout).
    """
    # Check if no subcommand was provided
    if not hasattr(args, "oauth_command") or args.oauth_command is None:
        console.print("[yellow]Usage: foxxy-bridge oauth <command>[/yellow]")
        console.print("Available commands: status, login, logout")
        return

    if args.oauth_command == "status":
        await _oauth_status(args, config_path, console, logger)
    elif args.oauth_command == "login":
        await handle_oauth_login(args, config_path, config_dir, console, logger)
    elif args.oauth_command == "logout":
        await handle_oauth_logout(args, config_path, config_dir, console, logger)
    else:
        console.print(f"[red]Unknown OAuth command: {args.oauth_command}[/red]")


async def _oauth_status(
    args: argparse.Namespace,
    config_path: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Display OAuth authentication status for servers.

    Args:
        args: Command line arguments with server name and format options
        config_path: Path to the configuration file
        console: Rich console for output
        logger: Logger for error reporting

    Shows authentication status for a specific server if name provided,
    otherwise shows status for all OAuth-enabled servers.
    Supports table and JSON output formats.
    """
    """Show OAuth authentication status."""
    try:
        api_client = get_api_client_from_config(str(config_path), console)

        if args.name:
            # Show status for specific server
            try:
                oauth_data = await api_client.get_oauth_status(args.name)
                oauth_status = {args.name: oauth_data}
            except aiohttp.ClientError as e:
                console.print(f"[red]Failed to get OAuth status for '{args.name}': {e}[/red]")
                return
        else:
            # Show status for all OAuth-enabled servers
            # First get list of servers
            try:
                servers = await api_client.list_servers()
                oauth_status = {}

                for server in servers:
                    server_name = server.get("name")
                    if server_name:
                        try:
                            oauth_data = await api_client.get_oauth_status(server_name)
                            # Only include if it's actually OAuth-enabled (doesn't error)
                            oauth_status[server_name] = oauth_data
                        except aiohttp.ClientError:
                            # Skip servers that don't support OAuth
                            continue

            except aiohttp.ClientError as e:
                console.print(f"[red]Failed to get server list: {e}[/red]")
                return

        if not oauth_status:
            console.print("[yellow]No OAuth-enabled servers found[/yellow]")
            return

        if args.format == "json":
            console.print(json.dumps(oauth_status, indent=2))
        else:
            OAuthFormatter.format_oauth_status(oauth_status, console)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Failed to get OAuth status")


async def handle_oauth_login(
    args: argparse.Namespace | SimpleNamespace,
    config_path: Path,
    config_dir: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Handle OAuth login command to initiate authentication for a server."""
    try:
        # Load bridge config to get bridge URL
        bridge_config = load_bridge_config_from_file(str(config_path), {})
        if not bridge_config or not bridge_config.bridge:
            console.print("[red]Error: Invalid or missing bridge configuration[/red]")
            return

        bridge_host = bridge_config.bridge.host
        bridge_port = bridge_config.bridge.port

        # Check if server exists and has OAuth enabled
        server_config = bridge_config.servers.get(args.name)
        if not server_config:
            console.print(f"[red]Server '{args.name}' not found in configuration[/red]")
            return

        if not server_config.oauth_config or not server_config.oauth_config.enabled:
            console.print(f"[red]OAuth is not enabled for server '{args.name}'[/red]")
            return

        # Construct OAuth start URL
        if bridge_host == "0.0.0.0":  # noqa: S104
            auth_url = f"http://127.0.0.1:{bridge_port}/oauth/{args.name}/start"
        else:
            auth_url = f"http://{bridge_host}:{bridge_port}/oauth/{args.name}/start"

        console.print(f"[blue]Starting OAuth authentication for server '[cyan]{args.name}[/cyan]'...[/blue]")
        console.print("[green]Open this URL in your browser:[/green]")
        console.print(f"[bold]{auth_url}[/bold]")

        # Try to open browser automatically
        try:
            import webbrowser

            webbrowser.open(auth_url)
            console.print("[green]✓[/green] Browser opened automatically")
        except Exception:
            console.print("[yellow]Could not open browser automatically - please open the URL manually[/yellow]")

    except Exception as e:
        console.print(f"[red]Error initiating OAuth login: {e}[/red]")
        logger.exception("Failed to initiate OAuth login")


async def handle_oauth_logout(
    args: argparse.Namespace | SimpleNamespace,
    config_path: Path,
    config_dir: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Handle OAuth logout command to clear authentication tokens."""
    try:
        if args.all:
            # Clear all OAuth tokens
            from mcp_foxxy_bridge.oauth.utils import clear_all_tokens

            try:
                clear_all_tokens()
                console.print("[green]✓[/green] All OAuth tokens cleared")
            except Exception as e:
                console.print(f"[red]Error clearing all tokens: {e}[/red]")
        else:
            # Clear tokens for specific server
            from mcp_foxxy_bridge.oauth.utils import clear_tokens, get_server_url_hash

            # Load config to get server URL for token lookup
            bridge_config = load_bridge_config_from_file(str(config_path), {})
            if not bridge_config:
                console.print("[red]Error: Invalid bridge configuration[/red]")
                return

            server_config = bridge_config.servers.get(args.name)
            if not server_config:
                console.print(f"[red]Server '{args.name}' not found in configuration[/red]")
                return

            server_url = getattr(server_config, "url", "")
            if not server_url:
                console.print(f"[red]No URL found for server '{args.name}'[/red]")
                return

            # Clear tokens for this server
            server_url_hash = get_server_url_hash(server_url)
            try:
                clear_tokens(server_url_hash, args.name)
                console.print(f"[green]✓[/green] OAuth tokens cleared for server '[cyan]{args.name}[/cyan]'")
            except Exception as e:
                console.print(f"[red]Error clearing tokens for '{args.name}': {e}[/red]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Failed to handle OAuth logout")
