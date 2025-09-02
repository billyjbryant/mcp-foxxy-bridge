#
# MCP Foxxy Bridge - CLI Main Entry Point
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
"""Main CLI entry point with command structure and argument parsing."""

import argparse
import asyncio
import os
import sys
from importlib.metadata import version
from pathlib import Path

from rich.console import Console

from mcp_foxxy_bridge.utils.config_migration import get_config_dir
from mcp_foxxy_bridge.utils.logging import setup_logging
from mcp_foxxy_bridge.utils.path_security import validate_config_dir, validate_config_path

from .commands.config import handle_config_command
from .commands.oauth import handle_oauth_command
from .commands.server import handle_server_command
from .commands.tool import handle_tool_command

console = Console()


def _setup_argument_parser() -> argparse.ArgumentParser:
    """Set up and return the main argument parser for the CLI."""
    try:
        package_version = version("mcp-foxxy-bridge")
    except Exception:
        try:
            version_file = Path(__file__).parent.parent.parent.parent / "VERSION"
            package_version = version_file.read_text().strip() if version_file.exists() else "unknown"
        except Exception:
            package_version = "unknown"

    parser = argparse.ArgumentParser(
        prog="foxxy-bridge",
        description="CLI for managing MCP Foxxy Bridge configuration and operations",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {package_version}",
        help="Show the version and exit",
    )

    parser.add_argument(
        "--config-dir",
        type=str,
        default=None,
        metavar="DIRECTORY_PATH",
        help="Configuration directory path (default: ~/.config/foxxy-bridge/)",
    )

    parser.add_argument(
        "--config",
        type=str,
        default=os.environ.get("FOXXY_BRIDGE_CONFIG"),
        metavar="CONFIG_PATH",
        help="Configuration file path (default: {config_dir}/config.json, env: FOXXY_BRIDGE_CONFIG)",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output",
    )

    # Create subcommand parsers
    subparsers = parser.add_subparsers(
        title="Commands",
        dest="command",
        help="Available commands",
        metavar="COMMAND",
        required=False,  # Allow no subcommand for help display
    )

    # Configuration management commands (bridge settings)
    _setup_config_commands(subparsers)

    # MCP server management commands
    _setup_mcp_commands(subparsers)

    # Server management commands
    _setup_server_commands(subparsers)

    # Tool commands
    _setup_tool_commands(subparsers)

    # Daemon management commands
    _setup_daemon_commands(subparsers)

    # OAuth management commands
    _setup_oauth_commands(subparsers)

    return parser


def _setup_config_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Set up bridge configuration management subcommands."""
    config_parser = subparsers.add_parser(
        "config",
        help="Bridge configuration management",
        description="Manage bridge settings and configuration",
    )

    config_subparsers = config_parser.add_subparsers(
        dest="config_command",
        help="Configuration commands",
        metavar="ACTION",
        required=False,
    )

    # config show
    show_parser = config_subparsers.add_parser("show", help="Show bridge configuration")
    show_parser.add_argument("--format", choices=["json", "yaml"], default="yaml", help="Output format")

    # config set
    set_parser = config_subparsers.add_parser("set", help="Set bridge configuration options")
    set_parser.add_argument("key", help="Configuration key (e.g., bridge.port, bridge.host)")
    set_parser.add_argument("value", help="Configuration value")

    # config get
    get_parser = config_subparsers.add_parser("get", help="Get bridge configuration value")
    get_parser.add_argument("key", help="Configuration key (e.g., bridge.port)")

    # config validate
    validate_parser = config_subparsers.add_parser("validate", help="Validate configuration")
    validate_parser.add_argument("--fix", action="store_true", help="Attempt to fix validation issues")

    # config init
    init_parser = config_subparsers.add_parser("init", help="Initialize configuration with defaults")
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing configuration")


def _setup_mcp_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Set up MCP server management subcommands."""
    mcp_parser = subparsers.add_parser(
        "mcp",
        help="MCP server management",
        description="Manage MCP server configurations",
    )

    mcp_subparsers = mcp_parser.add_subparsers(
        dest="mcp_command",
        help="MCP server commands",
        metavar="ACTION",
        required=False,
    )

    # mcp add
    add_parser = mcp_subparsers.add_parser("add", help="Add new MCP server")
    add_parser.add_argument("name", help="Server name")
    add_parser.add_argument("server_command", help="Server command")
    add_parser.add_argument("server_args", nargs="*", help="Server arguments")
    add_parser.add_argument(
        "--env", nargs=2, action="append", metavar=("KEY", "VALUE"), help="Environment variables", default=[]
    )
    add_parser.add_argument("--cwd", help="Working directory")
    add_parser.add_argument("--tags", nargs="+", help="Server tags", default=[])
    add_parser.add_argument("--oauth", action="store_true", help="Enable OAuth")
    add_parser.add_argument("--oauth-issuer", help="OAuth issuer URL")
    add_parser.add_argument(
        "--transport", choices=["stdio", "sse", "http"], default="stdio", help="Server transport type"
    )
    add_parser.add_argument("--url", help="Server URL (for SSE/HTTP transports)")

    # mcp remove
    remove_parser = mcp_subparsers.add_parser("remove", help="Remove MCP server")
    remove_parser.add_argument("name", help="Server name to remove")
    remove_parser.add_argument("--force", action="store_true", help="Force removal without confirmation")

    # mcp list
    list_parser = mcp_subparsers.add_parser("list", help="List configured MCP servers")
    list_parser.add_argument("--format", choices=["table", "json", "yaml"], default="table", help="Output format")

    # mcp show
    show_parser = mcp_subparsers.add_parser("show", help="Show MCP server details")
    show_parser.add_argument("name", nargs="?", help="Server name (show all if not specified)")
    show_parser.add_argument("--format", choices=["json", "yaml"], default="yaml", help="Output format")

    # mcp enable/disable
    enable_parser = mcp_subparsers.add_parser("enable", help="Enable MCP server")
    enable_parser.add_argument("name", help="Server name")

    disable_parser = mcp_subparsers.add_parser("disable", help="Disable MCP server")
    disable_parser.add_argument("name", help="Server name")


def _setup_server_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Set up server management subcommands."""
    server_parser = subparsers.add_parser(
        "server",
        help="Server management and monitoring",
        description="Monitor and manage MCP servers",
    )

    server_subparsers = server_parser.add_subparsers(
        dest="server_command",
        help="Server commands",
        metavar="ACTION",
    )

    # server status
    status_parser = server_subparsers.add_parser("status", help="Show server status")
    status_parser.add_argument("name", nargs="?", help="Server name (show all if not specified)")
    status_parser.add_argument("--format", choices=["table", "json"], default="table", help="Output format")
    status_parser.add_argument("--watch", "-w", action="store_true", help="Watch for status changes")

    # server logs
    logs_parser = server_subparsers.add_parser("logs", help="View server logs")
    logs_parser.add_argument("name", help="Server name")
    logs_parser.add_argument("--follow", "-f", action="store_true", help="Follow log output")
    logs_parser.add_argument("--lines", "-n", type=int, default=50, help="Number of lines to show")
    logs_parser.add_argument("--level", choices=["debug", "info", "warning", "error"], help="Filter by log level")

    # server restart
    restart_parser = server_subparsers.add_parser("restart", help="Restart server")
    restart_parser.add_argument("name", help="Server name")
    restart_parser.add_argument("--force", action="store_true", help="Force restart")

    # server health
    health_parser = server_subparsers.add_parser("health", help="Show health status")
    health_parser.add_argument("--format", choices=["table", "json"], default="table", help="Output format")

    # server reconnect
    reconnect_parser = server_subparsers.add_parser("reconnect", help="Force reconnection")
    reconnect_parser.add_argument("name", help="Server name")


def _setup_tool_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Set up tool discovery and testing subcommands."""
    tool_parser = subparsers.add_parser(
        "tool",
        help="Tool discovery and testing",
        description="Discover, test, and execute MCP tools",
    )

    tool_subparsers = tool_parser.add_subparsers(
        dest="tool_command",
        help="Tool commands",
        metavar="ACTION",
    )

    # tool list
    list_parser = tool_subparsers.add_parser("list", help="List available tools")
    list_parser.add_argument("server", nargs="?", help="Server name (show all if not specified)")
    list_parser.add_argument("--format", choices=["table", "json"], default="table", help="Output format")
    list_parser.add_argument("--tag", help="Filter by server tag")

    # tool test
    test_parser = tool_subparsers.add_parser("test", help="Test tool functionality")
    test_parser.add_argument("name", help="Tool name")
    test_parser.add_argument("--server", help="Specific server to test on")
    test_parser.add_argument("--dry-run", action="store_true", help="Show what would be called without executing")

    # tool call
    call_parser = tool_subparsers.add_parser("call", help="Execute tool")
    call_parser.add_argument("name", help="Tool name")
    call_parser.add_argument("--server", help="Specific server to call on")
    call_parser.add_argument("--args", help="Tool arguments as JSON string")
    call_parser.add_argument("--input-file", help="Read arguments from JSON file")

    # tool search
    search_parser = tool_subparsers.add_parser("search", help="Search tools")
    search_parser.add_argument("pattern", help="Search pattern")
    search_parser.add_argument("--server", help="Search within specific server")
    search_parser.add_argument("--description", action="store_true", help="Search in descriptions too")


def _setup_daemon_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Set up daemon management subcommands."""
    daemon_parser = subparsers.add_parser(
        "daemon",
        help="Bridge daemon control",
        description="Start, stop, and manage the bridge daemon",
    )

    daemon_subparsers = daemon_parser.add_subparsers(
        dest="daemon_command",
        help="Daemon commands",
        metavar="ACTION",
    )

    # daemon start
    start_parser = daemon_subparsers.add_parser("start", help="Start bridge daemon")
    start_parser.add_argument("--config", help="Configuration file path")
    start_parser.add_argument("--port", type=int, help="Server port")
    start_parser.add_argument("--host", help="Server host")
    start_parser.add_argument("--detach", action="store_true", help="Run in background")

    # daemon stop
    stop_parser = daemon_subparsers.add_parser("stop", help="Stop bridge daemon")
    stop_parser.add_argument("--force", action="store_true", help="Force stop")

    # daemon status
    status_parser = daemon_subparsers.add_parser("status", help="Show daemon status")
    status_parser.add_argument("--format", choices=["table", "json"], default="table", help="Output format")

    # daemon restart
    restart_parser = daemon_subparsers.add_parser("restart", help="Restart daemon")
    restart_parser.add_argument("--force", action="store_true", help="Force restart")

    # daemon logs
    logs_parser = daemon_subparsers.add_parser("logs", help="View daemon logs")
    logs_parser.add_argument("--follow", "-f", action="store_true", help="Follow log output")
    logs_parser.add_argument("--lines", "-n", type=int, default=50, help="Number of lines to show")


def _setup_oauth_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Set up OAuth management subcommands."""
    oauth_parser = subparsers.add_parser(
        "oauth",
        help="OAuth authentication management",
        description="Manage OAuth authentication for MCP servers",
    )

    oauth_subparsers = oauth_parser.add_subparsers(
        dest="oauth_command",
        help="OAuth commands",
        metavar="ACTION",
    )

    # oauth status
    status_parser = oauth_subparsers.add_parser("status", help="Show OAuth status")
    status_parser.add_argument("name", nargs="?", help="Server name (show all if not specified)")
    status_parser.add_argument("--format", choices=["table", "json"], default="table", help="Output format")

    # oauth login
    login_parser = oauth_subparsers.add_parser("login", help="Trigger OAuth login")
    login_parser.add_argument("name", help="Server name")
    login_parser.add_argument("--force", action="store_true", help="Force re-authentication")

    # oauth logout
    logout_parser = oauth_subparsers.add_parser("logout", help="Clear OAuth tokens")
    logout_parser.add_argument("name", help="Server name")
    logout_parser.add_argument("--all", action="store_true", help="Clear all OAuth tokens")


async def main() -> None:
    """Main CLI entry point."""
    parser = _setup_argument_parser()
    args = parser.parse_args()

    # Configure console and logging
    if args.no_color:
        console._color_system = None  # noqa: SLF001

    logger = setup_logging(debug=args.debug)

    # Get config directory and config path
    if args.config_dir:
        try:
            config_dir = validate_config_dir(args.config_dir)
        except Exception as e:
            console.print(f"[red]Error: Invalid config directory: {e}[/red]")
            sys.exit(1)
    else:
        config_dir = get_config_dir()

    # Determine config file path with priority: CLI arg > ENV var > default
    if args.config:
        try:
            config_path = validate_config_path(args.config)
        except Exception as e:
            console.print(f"[red]Error: Invalid config file path: {e}[/red]")
            sys.exit(1)
    else:
        config_path = config_dir / "config.json"

    # Handle no command specified
    if not args.command:
        parser.print_help()
        return

    try:
        # Import and dispatch to command handlers
        if args.command == "config":
            await handle_config_command(args, config_path, config_dir, console, logger)
        elif args.command == "server":
            await handle_server_command(args, config_path, config_dir, console, logger)
        elif args.command == "tool":
            await handle_tool_command(args, config_path, config_dir, console, logger)
        elif args.command == "daemon":
            # TODO: Daemon commands are not yet implemented
            console.print("[red]Error: Daemon commands are not yet implemented[/red]")
            return
        elif args.command == "oauth":
            await handle_oauth_command(args, config_path, config_dir, console, logger)
        else:
            console.print(f"[red]Unknown command: {args.command}[/red]")
            sys.exit(1)

    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled[/yellow]")
        sys.exit(1)
    except Exception as e:
        if args.debug:
            logger.exception("CLI error")
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


def cli_main() -> None:
    """Synchronous wrapper for the main CLI function."""
    asyncio.run(main())


if __name__ == "__main__":
    cli_main()
