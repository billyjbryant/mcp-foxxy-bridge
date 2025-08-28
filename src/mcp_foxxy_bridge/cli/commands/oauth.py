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
import shutil
from pathlib import Path
from typing import Any

import aiohttp
from rich.console import Console
from rich.prompt import Confirm

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
        from mcp_foxxy_bridge.cli.main import _setup_argument_parser

        parser = _setup_argument_parser()
        if parser._subparsers is None:  # noqa: SLF001
            console.print("[yellow]Usage: foxxy-bridge oauth <command>[/yellow]")
            console.print("Available commands: status, login, logout")
            return
        for action in parser._subparsers._actions:  # noqa: SLF001
            if hasattr(action, "choices") and action.choices and "oauth" in action.choices:
                action.choices["oauth"].print_help()  # type: ignore[index]
                return
        console.print("[yellow]Usage: foxxy-bridge oauth <command>[/yellow]")
        console.print("Available commands: status, login, logout")
        return

    if args.oauth_command == "status":
        await _oauth_status(args, config_path, console, logger)
    elif args.oauth_command == "login":
        await _oauth_login(args, config_path, console, logger)
    elif args.oauth_command == "logout":
        await _oauth_logout(args, config_path, config_dir, console, logger)
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
                    if server_name and server.get("oauth_enabled", False):
                        try:
                            oauth_data = await api_client.get_oauth_status(server_name)
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


async def _oauth_login(
    args: argparse.Namespace,
    config_path: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Initiate OAuth authentication flow for a server.

    Args:
        args: Command line arguments containing server name
        config_path: Path to the configuration file
        console: Rich console for output
        logger: Logger for error reporting

    Note: This is a placeholder implementation. Full OAuth login
    functionality requires integration with the OAuth authentication system.
    """
    """Trigger OAuth login flow."""
    try:
        # Check if server is configured for OAuth
        try:
            bridge_config = load_bridge_config_from_file(str(config_path), {})
            server_config = bridge_config.servers.get(args.name)

            if not server_config:
                console.print(f"[red]Server '{args.name}' not found in configuration[/red]")
                return

            if not server_config.oauth_config or not server_config.oauth_config.get("enabled", False):
                console.print(f"[red]OAuth is not enabled for server '{args.name}'[/red]")
                console.print("Enable OAuth in your configuration file first.")
                return

        except Exception as e:
            console.print(f"[red]Failed to load configuration: {e}[/red]")
            return

        # Check current OAuth status
        api_client = get_api_client_from_config(str(config_path), console)

        try:
            current_status = await api_client.get_oauth_status(args.name)

            if current_status.get("authenticated", False) and not args.force:
                console.print(f"[yellow]Server '{args.name}' is already authenticated[/yellow]")
                if not Confirm.ask("Re-authenticate anyway?"):
                    console.print("[yellow]Operation cancelled[/yellow]")
                    return

        except aiohttp.ClientError:
            # Server might not be running, continue with login attempt
            pass

        console.print(f"[cyan]Starting OAuth login for server '[white]{args.name}[/white]'[/cyan]")
        console.print("[dim]This will open your browser to complete authentication[/dim]")

        # For now, provide instructions since we don't have direct API endpoints for login
        console.print("\n[bold]To authenticate:[/bold]")
        console.print("1. Ensure the bridge daemon is running")
        console.print(f"2. The OAuth flow will be triggered when the server '{args.name}' first connects")
        console.print("3. Follow the browser prompts to complete authentication")

        # TODO: Implement direct OAuth flow triggering via API
        # This would require adding an endpoint to trigger OAuth flow on demand

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Failed to trigger OAuth login")


async def _oauth_logout(
    args: argparse.Namespace,
    config_path: Path,
    config_dir: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Revoke OAuth authentication for a server.

    Args:
        args: Command line arguments containing server name
        config_path: Path to the configuration file
        config_dir: Configuration directory for OAuth token storage
        console: Rich console for output
        logger: Logger for error reporting

    Note: This is a placeholder implementation. Full OAuth logout
    functionality requires integration with the OAuth authentication system.
    """
    try:
        auth_dir = config_dir / "auth"

        if args.all:
            # Clear all OAuth tokens
            if not Confirm.ask("Clear [red]ALL[/red] OAuth tokens?"):
                console.print("[yellow]Operation cancelled[/yellow]")
                return

            if auth_dir.exists():
                shutil.rmtree(auth_dir)
                auth_dir.mkdir(parents=True, exist_ok=True)
                console.print("[green]✓[/green] Cleared all OAuth tokens")
            else:
                console.print("[yellow]No OAuth tokens found[/yellow]")
        else:
            # Clear tokens for specific server
            if not Confirm.ask(f"Clear OAuth tokens for '[cyan]{args.name}[/cyan]'?"):
                console.print("[yellow]Operation cancelled[/yellow]")
                return

            # Look for token files for this server
            token_files = list(auth_dir.glob(f"{args.name}*")) if auth_dir.exists() else []

            if token_files:
                for token_file in token_files:
                    try:
                        token_file.unlink()
                        logger.debug(f"Removed token file: {token_file}")
                    except Exception as e:
                        logger.warning(f"Failed to remove {token_file}: {e}")

                console.print(f"[green]✓[/green] Cleared OAuth tokens for '[cyan]{args.name}[/cyan]'")
            else:
                console.print(f"[yellow]No OAuth tokens found for '[cyan]{args.name}[/cyan]'[/yellow]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Failed to clear OAuth tokens")
