#
# MCP Foxxy Bridge - Server Management Commands
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
"""Server management and monitoring CLI commands."""

import argparse
import asyncio
import json
import logging
from io import StringIO
from pathlib import Path
from typing import Any

import aiohttp
from rich.console import Console
from rich.console import Console as TempConsole
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

from mcp_foxxy_bridge.cli.api_client import get_api_client_from_config
from mcp_foxxy_bridge.cli.daemon_manager import DaemonManager
from mcp_foxxy_bridge.cli.formatters import StatusFormatter


async def handle_server_start(
    args: Any,
    config_path: Path,
    config_dir: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Handle server start command from Click CLI."""
    # Determine daemon name
    daemon_name = args.name
    config_file = getattr(args, "config", None)

    if not daemon_name and config_file:
        # Auto-generate daemon name from config file
        daemon_name = DaemonManager.generate_daemon_name(config_file)

    daemon_manager = DaemonManager(config_dir, console, daemon_name)

    # Convert to argparse-style namespace for compatibility
    argparse_args = argparse.Namespace(
        daemon_command="start",
        config=getattr(args, "config", None),
        port=getattr(args, "port", None),
        host=getattr(args, "host", None),
        detach=getattr(args, "detach", False),
        debug=getattr(args, "debug", False),
    )
    await _daemon_start(argparse_args, config_path, daemon_manager, console, logger)


async def handle_server_stop(
    args: Any,
    config_path: Path,
    config_dir: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Handle server stop command from Click CLI."""
    daemon_name = getattr(args, "name", None)

    if daemon_name:
        # Stop specific named daemon
        daemon_manager = DaemonManager(config_dir, console, daemon_name)
        argparse_args = argparse.Namespace(daemon_command="stop", force=getattr(args, "force", False))
        await _daemon_stop(argparse_args, daemon_manager, console, logger)
    else:
        # Stop all daemons if no name specified
        daemons = DaemonManager.list_daemons(config_dir)
        if not daemons:
            console.print("No running daemons found")
            return

        for daemon_info in daemons:
            if daemon_info.get("status") == "running":
                daemon_name = daemon_info.get("name", "default")
                console.print(f"Stopping daemon: {daemon_name}")
                daemon_manager = DaemonManager(config_dir, console, daemon_name if daemon_name != "default" else None)
                argparse_args = argparse.Namespace(daemon_command="stop", force=getattr(args, "force", False))
                await _daemon_stop(argparse_args, daemon_manager, console, logger)


async def handle_server_restart(
    args: Any,
    config_path: Path,
    config_dir: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Handle server restart command from Click CLI."""
    daemon_name = getattr(args, "name", None)
    config_file = getattr(args, "config", None)

    # If name not provided but config file is, generate name from config
    if not daemon_name and config_file:
        daemon_name = DaemonManager.generate_daemon_name(config_file)

    daemon_manager = DaemonManager(config_dir, console, daemon_name)

    # Convert to argparse-style namespace for compatibility
    argparse_args = argparse.Namespace(
        daemon_command="restart",
        force=getattr(args, "force", False),
        config=config_file,
        port=getattr(args, "port", None),
        host=getattr(args, "host", None),
    )
    await _daemon_restart(argparse_args, daemon_manager, console, logger)


async def handle_server_list(
    args: Any,
    config_path: Path,
    config_dir: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Handle server list command from Click CLI."""
    try:
        daemons = DaemonManager.list_daemons(config_dir)

        if args.format == "json":
            console.print(json.dumps(daemons, indent=2))
        else:
            # Table format
            if not daemons:
                console.print("No bridge instances found")
                return

            table = Table(title="Bridge Instances")
            table.add_column("Name", style="cyan")
            table.add_column("PID", style="green")
            table.add_column("Status", style="bold")
            table.add_column("Config File", style="dim")
            table.add_column("Port", style="blue")
            table.add_column("Started", style="dim")

            for daemon in daemons:
                status_color = "green" if daemon.get("status") == "running" else "red"
                config_file = daemon.get("config_file", "N/A")
                if config_file and len(config_file) > 50:
                    config_file = "..." + config_file[-47:]

                # Add type indicator to PID column
                pid_with_type = str(daemon.get("pid", "N/A"))
                daemon_type = daemon.get("type", "daemon")
                type_indicator = "[D]" if daemon_type == "daemon" else "[F]"
                pid_display = f"{pid_with_type} {type_indicator}"

                table.add_row(
                    daemon.get("name", "unknown"),
                    pid_display,
                    f"[{status_color}]{daemon.get('status', 'unknown')}[/{status_color}]",
                    config_file,
                    str(daemon.get("port", "N/A")),
                    daemon.get("started_at", "N/A"),
                )

            console.print(table)

    except Exception as e:
        console.print(f"[red]Error listing daemons: {e}[/red]")
        logger.exception("Failed to list daemons")


async def handle_server_status(
    args: Any,
    config_path: Path,
    config_dir: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Handle server status command from Click CLI."""
    # Default to daemon-only status (fast) unless full API status is explicitly requested
    full_api_status = getattr(args, "api", False) or getattr(args, "watch", False)
    if not full_api_status:
        await _daemon_status(args, config_dir, console, logger)
        return

    # Convert to argparse-style namespace for compatibility
    argparse_args = argparse.Namespace(
        server_command="status",
        name=getattr(args, "name", None),
        format=getattr(args, "format", "table"),
        watch=getattr(args, "watch", False),
    )
    await _server_status(argparse_args, config_path, console, logger)


async def handle_server_command(
    args: argparse.Namespace,
    config_path: Path,
    config_dir: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Handle server management commands."""
    # Check if no subcommand was provided
    if not hasattr(args, "server_command") or args.server_command is None:
        console.print("[yellow]Usage: foxxy-bridge server <command>[/yellow]")
        console.print("Available commands: status, logs, restart, health, reconnect")
        return

    if args.server_command == "status":
        await _server_status(args, config_path, console, logger)
    elif args.server_command == "logs":
        await _server_logs(args, config_path, console, logger)
    elif args.server_command == "restart":
        await _server_restart(args, config_path, console, logger)
    elif args.server_command == "health":
        await _server_health(args, config_path, console, logger)
    elif args.server_command == "reconnect":
        await _server_reconnect(args, config_path, console, logger)
    else:
        console.print(f"[red]Unknown server command: {args.server_command}[/red]")


async def _server_status(
    args: argparse.Namespace,
    config_path: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Display detailed server status information via API.

    Args:
        args: Command line arguments with server name, format, and watch options
        config_path: Path to configuration file
        console: Rich console for output
        logger: Logger for error reporting

    Shows comprehensive server status including connection state, capabilities,
    and health metrics. Supports live watching mode for real-time updates.
    """
    try:
        api_client = get_api_client_from_config(str(config_path), console)

        if args.watch:
            await _server_status_watch(api_client, args, console)
            return

        if args.name:
            # Show specific server status
            try:
                status_data = await api_client.get_server_status(args.name)

                if args.format == "json":
                    console.print(json.dumps(status_data, indent=2))
                else:
                    StatusFormatter.format_server_status(status_data, console)

            except aiohttp.ClientError as e:
                console.print(f"[red]Failed to get server status: {e}[/red]")

        else:
            # Show global status
            try:
                status_data = await api_client.get_status()

                if args.format == "json":
                    console.print(json.dumps(status_data, indent=2))
                else:
                    StatusFormatter.format_global_status(status_data, console)

            except aiohttp.ClientError as e:
                console.print(f"[red]Failed to get global status: {e}[/red]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Failed to get server status")


async def _server_status_watch(
    api_client: Any,
    args: argparse.Namespace,
    console: Console,
) -> None:
    """Display real-time server status updates.

    Continuously polls the API and updates the display with current server status.
    Updates every 2 seconds and handles connection errors gracefully.

    Args:
        api_client: API client for bridge communication
        args: Command line arguments with name filter
        console: Rich console for live output

    Exits on KeyboardInterrupt (Ctrl+C).
    """

    async def update_status() -> dict[str, Any]:
        """Fetch current status from API client.

        Returns:
            Dictionary containing status data or error information
        """
        try:
            if args.name:
                return await api_client.get_server_status(args.name)  # type: ignore[no-any-return]
            return await api_client.get_status()  # type: ignore[no-any-return]
        except Exception as e:
            return {"error": str(e)}

    with Live(console=console, refresh_per_second=1) as live:
        while True:
            try:
                status_data = await update_status()

                if "error" in status_data:
                    panel = Panel(
                        f"[red]Error: {status_data['error']}[/red]", title="❌ Connection Error", border_style="red"
                    )
                    live.update(panel)
                else:
                    # Create a fresh console for capturing output
                    temp_output = StringIO()
                    temp_console = TempConsole(file=temp_output, width=console.size.width)

                    if args.name:
                        StatusFormatter.format_server_status(status_data, temp_console)
                    else:
                        StatusFormatter.format_global_status(status_data, temp_console)

                    # Update the live display
                    live.update(Panel(temp_output.getvalue(), title="🔄 Live Status"))

                await asyncio.sleep(2)  # Update every 2 seconds

            except KeyboardInterrupt:
                break
            except Exception as e:
                panel = Panel(f"[red]Update failed: {e}[/red]", title="❌ Update Error", border_style="red")
                live.update(panel)
                await asyncio.sleep(5)  # Wait longer on error


async def _server_logs(
    args: argparse.Namespace,
    config_path: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Display logs from an MCP server.

    Args:
        args: Command line arguments with server name, lines count, follow mode, and level filter
        config_path: Path to configuration file
        console: Rich console for output
        logger: Logger for error reporting

    Note:
        Currently shows placeholder output. Full log viewing implementation
        is pending API endpoint availability.
    """
    console.print("[yellow]Note: Log viewing is not yet implemented via API[/yellow]")
    console.print(f"Server: {args.name}")
    console.print(f"Lines: {args.lines}")
    console.print(f"Follow: {args.follow}")
    if args.level:
        console.print(f"Level filter: {args.level}")

    # TODO: Implement log viewing once API endpoint is available
    # This would typically involve:
    # 1. Reading from centralized log files
    # 2. Filtering by server name and log level
    # 3. Implementing follow mode with tail-like functionality


async def _server_restart(
    args: argparse.Namespace,
    config_path: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Restart a specific MCP server connection.

    Args:
        args: Command line arguments with server name and force option
        config_path: Path to configuration file
        console: Rich console for output
        logger: Logger for error reporting

    Prompts for confirmation unless force is specified.
    """
    try:
        api_client = get_api_client_from_config(str(config_path), console)

        if not args.force:
            if not Confirm.ask(f"Restart server '[cyan]{args.name}[/cyan]'?"):
                console.print("[yellow]Operation cancelled[/yellow]")
                return

        # First try to reconnect (soft restart)
        with console.status(f"Restarting server {args.name}..."):
            try:
                result = await api_client.reconnect_server(args.name)
                console.print(f"[green]✓[/green] Server '[cyan]{args.name}[/cyan]' restarted")

                if "message" in result:
                    console.print(f"Message: {result['message']}")

            except aiohttp.ClientError as e:
                console.print(f"[red]Failed to restart server: {e}[/red]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Failed to restart server")


async def _server_health(
    args: argparse.Namespace,
    config_path: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Display health status information for all MCP servers.

    Args:
        args: Command line arguments with format option
        config_path: Path to configuration file
        console: Rich console for output
        logger: Logger for error reporting

    Shows overall health metrics and last check timestamps.
    """
    try:
        api_client = get_api_client_from_config(str(config_path), console)

        # Get global status which includes health info
        status_data = await api_client.get_status()

        if args.format == "json":
            console.print(json.dumps(status_data, indent=2))
        else:
            # Display health-focused status
            StatusFormatter.format_global_status(status_data, console)

            # Additional health details if available
            if "health" in status_data:
                health = status_data["health"]
                console.print(f"\n[bold]Overall Health:[/bold] {health.get('status', 'unknown')}")
                if "last_check" in health:
                    console.print(f"Last Check: {health['last_check']}")

    except aiohttp.ClientError as e:
        console.print(f"[red]Failed to get health status: {e}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Failed to get health status")


async def _server_reconnect(
    args: argparse.Namespace,
    config_path: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Force reconnection to a specific MCP server.

    Args:
        args: Command line arguments with server name
        config_path: Path to configuration file
        console: Rich console for output
        logger: Logger for error reporting

    Useful for recovering from connection issues or applying configuration changes.
    """
    try:
        api_client = get_api_client_from_config(str(config_path), console)

        with console.status(f"Reconnecting server {args.name}..."):
            try:
                result = await api_client.reconnect_server(args.name)
                console.print(f"[green]✓[/green] Server '[cyan]{args.name}[/cyan]' reconnection initiated")

                if "message" in result:
                    console.print(f"Message: {result['message']}")

            except aiohttp.ClientError as e:
                console.print(f"[red]Failed to reconnect server: {e}[/red]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Failed to reconnect server")


async def _daemon_start(
    args: argparse.Namespace,
    config_path: Path,
    daemon_manager: DaemonManager,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Start the bridge daemon process.

    Args:
        args: Command line arguments with start options (detach, config, host, port)
        config_path: Default path to configuration file
        daemon_manager: Manager for daemon operations
        console: Rich console for output
        logger: Logger for error reporting

    Handles both foreground and detached (background) daemon startup.
    """
    try:
        # Check if already running
        if await daemon_manager.is_running():
            console.print("[yellow]Bridge daemon is already running[/yellow]")
            status = await daemon_manager.get_daemon_status()
            console.print(f"PID: {status.get('pid')}")
            if status.get("port"):
                console.print(f"Port: {status.get('port')}")
            return

        # Build start parameters
        start_kwargs = {"detach": args.detach}

        if args.config:
            start_kwargs["config_file"] = args.config
        else:
            # Use the config_path that was passed to CLI
            start_kwargs["config_file"] = str(config_path)

        if args.host:
            start_kwargs["host"] = args.host

        if args.port:
            start_kwargs["port"] = args.port

        if hasattr(args, "debug") and args.debug:
            start_kwargs["debug"] = args.debug

        # Start daemon
        if args.detach:
            # For detached mode, don't use status spinner as it interferes with background process
            success = await daemon_manager.start_daemon(**start_kwargs)
        else:
            # For foreground mode, start directly without spinner since it's a blocking process
            console.print("Starting bridge server...")
            success = await daemon_manager.start_daemon(**start_kwargs)

        if success:
            if args.detach:
                # For detached mode, just show basic success info and exit quickly
                console.print("[green]✓[/green] Bridge daemon started successfully")
                console.print(f"Logs: {daemon_manager.log_file}")
                console.print(f"PID file: {daemon_manager.pid_file}")
            else:
                console.print("[green]✓[/green] Bridge daemon finished")
        else:
            console.print("[red]✗[/red] Failed to start bridge daemon")
            if daemon_manager.log_file.exists():
                console.print(f"Check logs: {daemon_manager.log_file}")

    except Exception as e:
        console.print(f"[red]Error starting daemon: {e}[/red]")
        logger.exception("Failed to start daemon")


async def _daemon_stop(
    args: argparse.Namespace,
    daemon_manager: DaemonManager,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Stop a running bridge daemon process.

    Args:
        args: Command line arguments with stop options (force)
        daemon_manager: Manager for daemon operations
        console: Rich console for output
        logger: Logger for error reporting

    Gracefully stops the daemon unless force is specified.
    """
    try:
        if not await daemon_manager.is_running():
            console.print("[yellow]Bridge daemon is not running[/yellow]")
            return

        status = await daemon_manager.get_daemon_status()
        with console.status("Stopping bridge daemon..."):
            success = await daemon_manager.stop_daemon(force=args.force)

        if success:
            console.print(f"[green]✓[/green] Stopped daemon (PID: {status.get('pid')})")
            console.print("[green]✓[/green] Bridge daemon stopped")
        else:
            console.print("[red]✗[/red] Failed to stop bridge daemon")

    except Exception as e:
        console.print(f"[red]Error stopping daemon: {e}[/red]")
        logger.exception("Failed to stop daemon")


async def _daemon_restart(
    args: argparse.Namespace,
    daemon_manager: DaemonManager,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Restart a bridge daemon process with optional new configuration.

    Args:
        args: Command line arguments with restart options (config, host, port, force)
        daemon_manager: Manager for daemon operations
        console: Rich console for output
        logger: Logger for error reporting

    Stops the current daemon and starts a new one with updated settings.
    """
    try:
        start_kwargs = {}

        if args.config:
            start_kwargs["config_file"] = args.config

        if args.host:
            start_kwargs["host"] = args.host

        if args.port:
            start_kwargs["port"] = args.port

        with console.status("Restarting bridge daemon..."):
            success = await daemon_manager.restart_daemon(force=args.force, **start_kwargs)

        if success:
            console.print("[green]✓[/green] Bridge daemon restarted")
            status = await daemon_manager.get_daemon_status()
            console.print(f"PID: {status.get('pid')}")
            if status.get("port"):
                console.print(f"Port: {status.get('port')}")
        else:
            console.print("[red]✗[/red] Failed to restart bridge daemon")

    except Exception as e:
        console.print(f"[red]Error restarting daemon: {e}[/red]")
        logger.exception("Failed to restart daemon")


async def _daemon_status(
    args: Any,
    config_dir: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Display bridge daemon status information.

    Shows lightweight daemon status without requiring configuration file access.
    Can display status for a specific daemon or all daemons.

    Args:
        args: Command line arguments with name and format options
        config_dir: Directory containing daemon metadata
        console: Rich console for output
        logger: Logger for error reporting

    Supports both table and JSON output formats.
    """
    try:
        daemon_name = getattr(args, "name", None)

        if daemon_name:
            # Show specific daemon status
            daemon_info = DaemonManager.get_daemon_info_by_name(config_dir, daemon_name)
            if not daemon_info:
                console.print(f"[red]Daemon '{daemon_name}' not found[/red]")
                return

            if args.format == "json":
                console.print(json.dumps(daemon_info, indent=2))
            else:
                # Show formatted daemon info
                status_color = "green" if daemon_info.get("status") == "running" else "red"
                console.print(f"Daemon: [cyan]{daemon_info.get('name', 'unknown')}[/cyan]")
                console.print(f"Status: [{status_color}]{daemon_info.get('status', 'unknown')}[/{status_color}]")
                pid = daemon_info.get("pid", "N/A")
                daemon_type = daemon_info.get("type", "daemon")
                type_indicator = "[D]" if daemon_type == "daemon" else "[F]"
                console.print(f"PID: {pid} {type_indicator}")

                if daemon_info.get("config_file"):
                    console.print(f"Config: {daemon_info['config_file']}")
                if daemon_info.get("port"):
                    console.print(f"Port: {daemon_info['port']}")
                if daemon_info.get("host"):
                    console.print(f"Host: {daemon_info['host']}")
                if daemon_info.get("started_at"):
                    console.print(f"Started: {daemon_info['started_at']}")
                if daemon_info.get("log_file"):
                    console.print(f"Logs: {daemon_info['log_file']}")

        else:
            # Show all daemons status or suggest specifying by name if multiple
            daemons = DaemonManager.list_daemons(config_dir)
            if not daemons:
                console.print("No bridge instances found")
                return

            if args.format == "json":
                console.print(json.dumps(daemons, indent=2))
            elif len(daemons) == 1:
                # Show detailed status for single daemon
                daemon = daemons[0]
                status_color = "green" if daemon.get("status") == "running" else "red"
                console.print(f"Daemon: [cyan]{daemon.get('name', 'unknown')}[/cyan]")
                console.print(f"Status: [{status_color}]{daemon.get('status', 'unknown')}[/{status_color}]")
                console.print(f"PID: {daemon.get('pid', 'N/A')}")

                if daemon.get("config_file"):
                    console.print(f"Config: {daemon['config_file']}")
                if daemon.get("port"):
                    console.print(f"Port: {daemon['port']}")
                if daemon.get("host"):
                    console.print(f"Host: {daemon['host']}")
                if daemon.get("started_at"):
                    console.print(f"Started: {daemon['started_at']}")
                if daemon.get("log_file"):
                    console.print(f"Logs: {daemon['log_file']}")
            else:
                # Multiple daemons - show list and advise to specify by name
                console.print(
                    f"[yellow]Found {len(daemons)} bridge daemons. Please specify a daemon by name:[/yellow]\n"
                )

                table = Table(show_header=True, header_style="bold cyan")
                table.add_column("Name", style="cyan")
                table.add_column("Status", style="bold")
                table.add_column("PID", style="green")
                table.add_column("Port", style="blue")

                for daemon in daemons:
                    status_color = "green" if daemon.get("status") == "running" else "red"
                    table.add_row(
                        daemon.get("name", "unknown"),
                        f"[{status_color}]{daemon.get('status', 'unknown')}[/{status_color}]",
                        str(daemon.get("pid", "N/A")),
                        str(daemon.get("port", "N/A")),
                    )

                console.print(table)
                console.print("\n[dim]Use: foxxy-bridge server status --name <daemon_name>[/dim]")

    except Exception as e:
        console.print(f"[red]Error getting daemon status: {e}[/red]")
        logger.exception("Failed to get daemon status")
