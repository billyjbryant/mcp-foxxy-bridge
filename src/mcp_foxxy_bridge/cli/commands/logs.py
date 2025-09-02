#
# MCP Foxxy Bridge - Log Management Commands
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

"""Log management commands for MCP servers."""

import asyncio
import logging
from pathlib import Path
from typing import Any

from rich.console import Console

from mcp_foxxy_bridge.oauth.utils import _validate_server_name
from mcp_foxxy_bridge.utils.config_migration import get_server_logs_dir


async def handle_mcp_logs(
    args: Any, config_path: Path, config_dir: Path, console: Console, logger: logging.Logger
) -> None:
    """Handle MCP server log viewing and tailing commands.

    Args:
        args: Command line arguments containing server_name, follow, and lines options
        config_path: Path to configuration file (unused)
        config_dir: Configuration directory (unused)
        console: Rich console for output
        logger: Logger for error reporting

    Displays log entries for the specified MCP server. Supports both static viewing
    of recent entries and live tailing mode. Uses the system 'tail' command for
    efficient log following.
    """
    server_name = _validate_server_name(args.server_name)
    follow = args.follow if hasattr(args, "follow") else False
    lines = args.lines if hasattr(args, "lines") else 50

    # Get the log file path for this server
    logs_dir = get_server_logs_dir()
    log_file = logs_dir / f"{server_name}.log"

    if not log_file.exists():
        console.print(f"[red]❌ No log file found for server '[bold]{server_name}[/bold]'[/red]")
        console.print(f"[dim]Expected: {log_file}[/dim]")
        console.print("[dim]Note: Server may not have been started yet or may not exist.[/dim]")
        return

    if follow:
        console.print(
            f"[yellow]📖 Tailing logs for MCP server '[bold]{server_name}[/bold]' (press Ctrl+C to stop)[/yellow]"
        )
        console.print(f"[dim]Reading from: {log_file}[/dim]\n")

        # Use tail -f to follow the log file
        try:
            process = await asyncio.create_subprocess_exec(
                "tail", "-f", str(log_file), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            while True:
                if process.stdout is None:
                    break
                line = await process.stdout.readline()
                if not line:
                    break
                console.print(line.decode("utf-8").rstrip())

        except KeyboardInterrupt:
            console.print("\n[yellow]📖 Log tailing stopped.[/yellow]")
            if process:
                process.terminate()
                await process.wait()
        except Exception as e:
            console.print(f"[red]❌ Error tailing log file: {e}[/red]")
    else:
        console.print(
            f"[yellow]📖 Showing last {lines} log entries for MCP server '[bold]{server_name}[/bold]'[/yellow]"
        )
        console.print(f"[dim]Reading from: {log_file}[/dim]\n")

        try:
            # Use tail to get the last N lines
            process = await asyncio.create_subprocess_exec(
                "tail", "-n", str(lines), str(log_file), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                log_content = stdout.decode("utf-8").strip()
                if log_content:
                    console.print(log_content)
                else:
                    console.print(f"[dim]Log file for '{server_name}' is empty.[/dim]")
            else:
                error_msg = stderr.decode("utf-8").strip()
                console.print(f"[red]❌ Error reading log file: {error_msg}[/red]")

        except Exception as e:
            console.print(f"[red]❌ Error reading log file: {e}[/red]")
