#
# MCP Foxxy Bridge - CLI Formatters
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
"""Rich-based formatters for pretty CLI output."""

import json
from datetime import datetime
from typing import Any

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


class StatusFormatter:
    """Format server status information."""

    @staticmethod
    def format_server_status(status_data: dict[str, Any], console: Console) -> None:
        """Format and display server status information."""
        if not status_data:
            console.print("[red]No status data available[/red]")
            return

        # Create status table
        table = Table(title="Server Status", show_header=True, header_style="bold magenta")
        table.add_column("Property", style="cyan", no_wrap=True)
        table.add_column("Value", style="white")

        # Add basic info
        table.add_row("Server Name", status_data.get("name", "Unknown"))
        table.add_row("Status", StatusFormatter._format_status(status_data.get("status", "unknown")))
        table.add_row("Transport", status_data.get("transport", "Unknown"))

        # Add uptime if available
        if "uptime" in status_data:
            table.add_row("Uptime", StatusFormatter._format_uptime(status_data["uptime"]))

        # Add health info
        if "health" in status_data:
            health = status_data["health"]
            table.add_row("Health", StatusFormatter._format_health(health.get("status", "unknown")))
            if "last_check" in health:
                table.add_row("Last Health Check", health["last_check"])

        # Add capabilities
        if "capabilities" in status_data:
            caps = status_data["capabilities"]
            tools_count = len(caps.get("tools", []))
            resources_count = len(caps.get("resources", []))
            prompts_count = len(caps.get("prompts", []))

            table.add_row("Tools", str(tools_count))
            table.add_row("Resources", str(resources_count))
            table.add_row("Prompts", str(prompts_count))

        console.print(table)

    @staticmethod
    def format_global_status(status_data: dict[str, Any], console: Console) -> None:
        """Format and display global bridge status."""
        if not status_data:
            console.print("[red]No status data available[/red]")
            return

        # Main status panel
        status_text = f"Bridge Status: {StatusFormatter._format_status(status_data.get('status', 'unknown'))}"
        console.print(Panel(status_text, title="🌉 Foxxy Bridge", expand=False))

        # Server summary table
        if "servers" in status_data:
            servers = status_data["servers"]
            table = Table(title="Server Summary", show_header=True, header_style="bold cyan")
            table.add_column("Server", style="white", no_wrap=True)
            table.add_column("Status", justify="center")
            table.add_column("Tools", justify="right", style="green")
            table.add_column("Transport", style="blue")

            for server_name, server_info in servers.items():
                status = StatusFormatter._format_status(server_info.get("status", "unknown"))
                tools_count = len(server_info.get("capabilities", {}).get("tools", []))
                transport = server_info.get("transport", "unknown")

                table.add_row(server_name, status, str(tools_count), transport)

            console.print(table)

    @staticmethod
    def _format_status(status: str) -> Text:
        """Format status with appropriate colors."""
        status_lower = status.lower()
        if status_lower in ("connected", "running", "healthy"):
            return Text(status, style="bold green")
        if status_lower in ("connecting", "starting"):
            return Text(status, style="bold yellow")
        if status_lower in ("disconnected", "failed", "error"):
            return Text(status, style="bold red")
        return Text(status, style="white")

    @staticmethod
    def _format_health(health: str) -> Text:
        """Format health status with appropriate colors."""
        health_lower = health.lower()
        if health_lower == "healthy":
            return Text(health, style="bold green")
        if health_lower == "degraded":
            return Text(health, style="bold yellow")
        if health_lower == "unhealthy":
            return Text(health, style="bold red")
        return Text(health, style="white")

    @staticmethod
    def _format_uptime(uptime_seconds: float) -> str:
        """Format uptime in human-readable format."""
        if uptime_seconds < 60:
            return f"{uptime_seconds:.1f}s"
        if uptime_seconds < 3600:
            return f"{uptime_seconds / 60:.1f}m"
        if uptime_seconds < 86400:
            return f"{uptime_seconds / 3600:.1f}h"
        return f"{uptime_seconds / 86400:.1f}d"


class ToolFormatter:
    """Format tool information."""

    @staticmethod
    def format_tools_table(tools_data: list[dict[str, Any]], console: Console) -> None:
        """Format and display tools in a table."""
        if not tools_data:
            console.print("[yellow]No tools available[/yellow]")
            return

        table = Table(title="Available Tools", show_header=True, header_style="bold magenta")
        table.add_column("Tool Name", style="cyan", no_wrap=True)
        table.add_column("Server", style="blue")
        table.add_column("Description", style="white", max_width=50)

        for tool in tools_data:
            name = tool.get("name", "Unknown")
            server = tool.get("server", "Unknown")
            description = tool.get("description", "No description")

            # Truncate long descriptions
            if len(description) > 50:
                description = description[:47] + "..."

            table.add_row(name, server, description)

        console.print(table)

    @staticmethod
    def format_tool_call_result(result: dict[str, Any], console: Console) -> None:
        """Format and display tool call result."""
        if not result:
            console.print("[red]No result data[/red]")
            return

        # Success/error status
        if result.get("isError", False):
            console.print(
                Panel(
                    f"[red]Error: {result.get('content', [{}])[0].get('text', 'Unknown error')}[/red]",
                    title="❌ Tool Call Failed",
                    border_style="red",
                )
            )
        else:
            console.print(
                Panel("[green]Tool executed successfully[/green]", title="✅ Tool Call Result", border_style="green")
            )

        # Display content
        if "content" in result:
            content = result["content"]
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            console.print("\n[bold]Output:[/bold]")
                            console.print(item.get("text", ""))
                        else:
                            console.print(f"\n[bold]Content ({item.get('type', 'unknown')}):[/bold]")
                            console.print(str(item))
            else:
                console.print(f"\n[bold]Output:[/bold]\n{content}")


class ConfigFormatter:
    """Format configuration information."""

    @staticmethod
    def format_servers_table(servers: dict[str, Any], console: Console) -> None:
        """Format and display server configurations in a table."""
        if not servers:
            console.print("[yellow]No servers configured[/yellow]")
            return

        table = Table(title="Configured Servers", show_header=True, header_style="bold magenta")
        table.add_column("Server Name", style="cyan", no_wrap=True, max_width=25)
        table.add_column("Command/URL", style="white", max_width=35)
        table.add_column("Transport", style="blue", max_width=10)
        table.add_column("Tags", style="green", max_width=25)
        table.add_column("OAuth", style="yellow", justify="center", max_width=6)

        for name, config in servers.items():
            # Handle different transport types
            transport = config.get("transport", "stdio")
            if transport in ("sse", "http", "streamablehttp"):
                command = config.get("url", "Unknown")
            else:
                command = config.get("command", "Unknown")

            tags = ", ".join(config.get("tags", []))

            # Check multiple OAuth config formats
            oauth_enabled = False
            if config.get("oauth", {}).get("enabled", False) or config.get("oauth_config", {}).get("enabled", False):
                oauth_enabled = True

            oauth_display = "✓" if oauth_enabled else "✗"

            # Truncate long commands/URLs
            if len(command) > 35:
                command = command[:32] + "..."

            table.add_row(name, command, transport, tags or "-", oauth_display)

        console.print(table)

    @staticmethod
    def format_config_yaml(config: dict[str, Any], console: Console) -> None:
        """Format and display configuration as YAML."""
        try:
            yaml_str = yaml.dump(config, default_flow_style=False, indent=2)  # type: ignore[no-untyped-call]
            console.print(yaml_str.rstrip())
        except Exception as e:
            console.print(f"[red]Error formatting YAML: {e}[/red]")
            ConfigFormatter.format_config_json(config, console)

    @staticmethod
    def format_config_json(config: dict[str, Any], console: Console) -> None:
        """Format and display configuration as JSON."""
        try:
            json_str = json.dumps(config, indent=2)
            console.print(f"```json\n{json_str}\n```")
        except Exception as e:
            console.print(f"[red]Error formatting JSON: {e}[/red]")


class DaemonFormatter:
    """Format daemon status and management information."""

    @staticmethod
    def format_daemon_status(status: dict[str, Any], console: Console) -> None:
        """Format and display daemon status."""
        if not status:
            console.print("[red]Daemon is not running[/red]")
            return

        # Main status panel
        status_text = f"Daemon Status: {StatusFormatter._format_status(status.get('status', 'unknown'))}"  # noqa: SLF001
        console.print(Panel(status_text, title="🔧 Bridge Daemon", expand=False))

        # Details table
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Property", style="white", no_wrap=True)
        table.add_column("Value", style="cyan")

        table.add_row("PID", str(status.get("pid", "Unknown")))
        table.add_row("Host", status.get("host", "Unknown"))
        table.add_row("Port", str(status.get("port", "Unknown")))

        if "start_time" in status:
            start_time = datetime.fromisoformat(status["start_time"])
            table.add_row("Started", start_time.strftime("%Y-%m-%d %H:%M:%S"))

        if "uptime" in status:
            table.add_row("Uptime", StatusFormatter._format_uptime(status["uptime"]))  # noqa: SLF001

        console.print(table)


class OAuthFormatter:
    """Format OAuth authentication information."""

    @staticmethod
    def format_oauth_status(oauth_data: dict[str, Any], console: Console) -> None:
        """Format and display OAuth status."""
        if not oauth_data:
            console.print("[red]No OAuth data available[/red]")
            return

        # OAuth status table
        table = Table(title="OAuth Status", show_header=True, header_style="bold magenta")
        table.add_column("Server", style="cyan", no_wrap=True)
        table.add_column("Status", justify="center")
        table.add_column("Issuer", style="blue", max_width=30)
        table.add_column("Expires", style="yellow")

        for server_name, oauth_info in oauth_data.items():
            status = "✓ Authenticated" if oauth_info.get("status") == "authenticated" else "✗ Not authenticated"
            issuer = oauth_info.get("issuer", "Unknown")
            expires = oauth_info.get("expires_at", "Unknown")

            if len(issuer) > 30:
                issuer = issuer[:27] + "..."

            table.add_row(server_name, status, issuer, expires)

        console.print(table)
