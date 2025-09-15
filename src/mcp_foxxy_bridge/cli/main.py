#
# MCP Foxxy Bridge - Click-based CLI
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
"""Click-based CLI for MCP Foxxy Bridge management."""

import argparse
import asyncio
import builtins
import shlex
from importlib.metadata import version
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import click
import rich_click
from rich.console import Console

from mcp_foxxy_bridge.cli.commands import config as config_commands
from mcp_foxxy_bridge.cli.commands import mcp_handlers
from mcp_foxxy_bridge.cli.commands.config import _mcp_config_get, _mcp_config_set, _mcp_config_unset
from mcp_foxxy_bridge.cli.commands.logs import handle_mcp_logs
from mcp_foxxy_bridge.cli.commands.mcp_handlers import (
    handle_mcp_add,
    handle_mcp_list,
    handle_mcp_remove,
    handle_mcp_restart,
    handle_mcp_show,
    handle_mcp_status,
)
from mcp_foxxy_bridge.cli.commands.oauth import handle_oauth_login, handle_oauth_logout, handle_oauth_status
from mcp_foxxy_bridge.cli.commands.security_handlers import handle_security_set, handle_security_show
from mcp_foxxy_bridge.cli.commands.server import (
    handle_server_list,
    handle_server_restart,
    handle_server_start,
    handle_server_status,
    handle_server_stop,
)
from mcp_foxxy_bridge.cli.commands.tool import handle_tool_list
from mcp_foxxy_bridge.oauth.utils import _validate_server_name
from mcp_foxxy_bridge.utils.config_migration import get_config_dir
from mcp_foxxy_bridge.utils.logging import setup_logging
from mcp_foxxy_bridge.utils.path_security import validate_config_dir, validate_config_path


def print_version(ctx: click.Context, param: Any, value: bool) -> None:
    """Print version callback for CLI."""
    if not value or ctx.resilient_parsing:
        return
    try:
        ver = version("mcp-foxxy-bridge")
    except ImportError:
        ver = "1.5.0"
    click.echo(f"foxxy-bridge, version {ver}")
    ctx.exit()


# Configure rich-click for better help output
rich_click.USE_RICH_MARKUP = True
rich_click.USE_MARKDOWN = True
rich_click.SHOW_ARGUMENTS = True
rich_click.GROUP_ARGUMENTS_OPTIONS = True

console = Console()


# Global options that apply to all commands
@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--config-dir",
    "-C",
    type=click.Path(exists=False, path_type=Path),
    help="Configuration directory path (default: ~/.config/foxxy-bridge/)",
)
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=False, path_type=Path),
    envvar="FOXXY_BRIDGE_CONFIG",
    help="Configuration file path (default: {config_dir}/config.json, env: FOXXY_BRIDGE_CONFIG)",
)
@click.option("--debug", "-d", is_flag=True, help="Enable debug logging")
@click.option("--no-color", is_flag=True, help="Disable colored output")
@click.option(
    "-v",
    "--version",
    is_flag=True,
    expose_value=False,
    is_eager=True,
    callback=print_version,
    help="Show version and exit",
)
@click.pass_context
def cli(ctx: click.Context, config_dir: Path | None, config: Path | None, debug: bool, no_color: bool) -> None:
    """CLI for managing MCP Foxxy Bridge configuration and operations."""
    # Configure console and logging
    if no_color:
        console._color_system = None  # noqa: SLF001

    logger = setup_logging(debug=debug)

    # Get config directory and config path
    if config_dir:
        try:
            config_dir = validate_config_dir(config_dir)
        except Exception as e:
            console.print(f"[red]Error: Invalid config directory: {e}[/red]")
            raise click.Abort from None
    else:
        config_dir = get_config_dir()

    # Determine config file path with priority: CLI arg > ENV var > default
    if config:
        try:
            config_path = validate_config_path(config)
        except Exception as e:
            console.print(f"[red]Error: Invalid config file path: {e}[/red]")
            raise click.Abort from None
    else:
        config_path = config_dir / "config.json"

    # Store in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj["config_dir"] = config_dir
    ctx.obj["config_path"] = config_path
    ctx.obj["console"] = console
    ctx.obj["logger"] = logger
    ctx.obj["debug"] = debug


# Configuration management group
@cli.group()
@click.pass_context
def config(ctx: click.Context) -> None:
    """Manage bridge configuration settings."""


@config.command()
@click.option("--output-format", "-f", type=click.Choice(["json", "yaml"]), default="yaml", help="Output format")
@click.pass_context
def config_show(ctx: click.Context, output_format: str) -> None:
    """Show bridge configuration."""
    args = SimpleNamespace(format=output_format, name=None)

    asyncio.run(
        mcp_handlers.handle_config_show(
            args, ctx.obj["config_path"], ctx.obj["config_dir"], ctx.obj["console"], ctx.obj["logger"]
        )
    )


@config.command("set-value")
@click.argument("key")
@click.argument("value")
@click.pass_context
def config_set_value(ctx: click.Context, key: str, value: str) -> None:
    """Set bridge configuration option.

    Examples:
      foxxy-bridge config set-value bridge.port 9000
      foxxy-bridge config set-value bridge.host 0.0.0.0
    """
    # Convert SimpleNamespace to argparse.Namespace for compatibility
    args = argparse.Namespace(key=key, value=value)

    asyncio.run(config_commands._config_set(args, ctx.obj["config_path"], ctx.obj["console"], ctx.obj["logger"]))  # noqa: SLF001


@config.command("get-value")
@click.argument("key")
@click.pass_context
def config_get_value(ctx: click.Context, key: str) -> None:
    """Get bridge configuration value."""
    # Convert SimpleNamespace to argparse.Namespace for compatibility
    args = argparse.Namespace(key=key)

    asyncio.run(config_commands._config_get(args, ctx.obj["config_path"], ctx.obj["console"], ctx.obj["logger"]))  # noqa: SLF001


@config.command("unset-value")
@click.argument("key")
@click.pass_context
def config_unset_value(ctx: click.Context, key: str) -> None:
    """Unset bridge configuration option.

    Examples:
      foxxy-bridge config unset-value security.tools.block_patterns
      foxxy-bridge config unset-value port
    """
    # Convert SimpleNamespace to argparse.Namespace for compatibility
    args = argparse.Namespace(key=key)

    asyncio.run(config_commands._config_unset(args, ctx.obj["config_path"], ctx.obj["console"], ctx.obj["logger"]))  # noqa: SLF001


@config.command()
@click.option("--fix", is_flag=True, help="Attempt to fix validation issues")
@click.pass_context
def validate(ctx: click.Context, fix: bool) -> None:
    """Validate configuration."""
    args = SimpleNamespace(fix=fix)

    asyncio.run(
        mcp_handlers.handle_config_validate(
            args, ctx.obj["config_path"], ctx.obj["config_dir"], ctx.obj["console"], ctx.obj["logger"]
        )
    )


@config.command()
@click.option("--force", "-F", is_flag=True, help="Overwrite existing configuration")
@click.pass_context
def init(ctx: click.Context, force: bool) -> None:
    """Initialize configuration with defaults."""
    args = SimpleNamespace(force=force)

    asyncio.run(
        mcp_handlers.handle_config_init(
            args, ctx.obj["config_path"], ctx.obj["config_dir"], ctx.obj["console"], ctx.obj["logger"]
        )
    )


@config.group()
@click.pass_context
def security(ctx: click.Context) -> None:
    """Manage bridge security configuration."""


@security.command("show")
@click.option("--format", "-f", type=click.Choice(["json", "yaml"]), default="yaml", help="Output format")
@click.pass_context
def security_show(ctx: click.Context, format: str) -> None:  # noqa: A002
    """Show bridge security configuration."""
    args = SimpleNamespace(format=format)

    asyncio.run(
        handle_security_show(args, ctx.obj["config_path"], ctx.obj["config_dir"], ctx.obj["console"], ctx.obj["logger"])
    )


@security.command("set")
@click.option("--read-only/--no-read-only", default=None, help="Set global read-only mode")
@click.option("--allow-pattern", multiple=True, help="Set allow patterns (replaces existing)")
@click.option("--block-pattern", multiple=True, help="Set block patterns (replaces existing)")
@click.option("--allow-tool", multiple=True, help="Set allow tools (replaces existing)")
@click.option("--block-tool", multiple=True, help="Set block tools (replaces existing)")
@click.option(
    "--classify-tool",
    multiple=True,
    type=(str, click.Choice(["read", "write", "unknown"])),
    metavar="TOOL_NAME TYPE",
    help="Set tool classifications (replaces existing)",
)
@click.pass_context
def security_set(
    ctx: click.Context,
    read_only: bool,
    allow_pattern: tuple[str, ...],
    block_pattern: tuple[str, ...],
    allow_tool: tuple[str, ...],
    block_tool: tuple[str, ...],
    classify_tool: tuple[tuple[str, str], ...],
) -> None:
    """Set bridge security configuration."""
    args = SimpleNamespace(
        read_only=read_only,
        allow_patterns=builtins.list(allow_pattern),
        block_patterns=builtins.list(block_pattern),
        allow_tools=builtins.list(allow_tool),
        block_tools=builtins.list(block_tool),
        classify_tools=[builtins.list(c) for c in classify_tool],
    )

    asyncio.run(
        handle_security_set(args, ctx.obj["config_path"], ctx.obj["config_dir"], ctx.obj["console"], ctx.obj["logger"])
    )


# MCP server management group
@cli.group()
@click.pass_context
def mcp(ctx: click.Context) -> None:
    """Manage MCP servers."""


@mcp.command()
@click.argument("name")
@click.argument("command", required=False)
@click.option(
    "--env",
    multiple=True,
    type=(str, str),
    metavar="KEY VALUE",
    help="Environment variables (can be used multiple times)",
)
@click.option("--cwd", help="Working directory")
@click.option("--tags", multiple=True, help="Server tags")
@click.option("--oauth", is_flag=True, help="Enable OAuth")
@click.option("--oauth-issuer", help="OAuth issuer URL")
@click.option(
    "--transport", "-t", type=click.Choice(["stdio", "sse", "http"]), default="stdio", help="Server transport type"
)
@click.option("--url", "-u", help="Server URL (for SSE/HTTP transports)")
@click.option("--enabled/--disabled", default=True, help="Enable or disable the server")
@click.option("--timeout", type=int, help="Server timeout in seconds")
@click.option("--retry-attempts", type=int, help="Number of retry attempts on failure")
@click.option("--retry-delay", type=int, help="Delay between retry attempts in milliseconds")
@click.option("--health-check/--no-health-check", default=None, help="Enable or disable health checks")
@click.option("--tool-namespace", help="Namespace for server tools")
@click.option("--resource-namespace", help="Namespace for server resources")
@click.option("--priority", type=int, help="Server priority (higher = more priority)")
@click.option("--log-level", type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "QUIET"]), help="Server log level")
@click.option(
    "--header",
    multiple=True,
    type=(str, str),
    metavar="KEY VALUE",
    help="HTTP headers (for HTTP/SSE transports, can be used multiple times)",
)
@click.option(
    "--read-only/--no-read-only", default=None, help="Enable read-only mode for this server (overrides global setting)"
)
@click.option(
    "--allow-pattern", multiple=True, help="Allow patterns for tool names (glob/regex, can be used multiple times)"
)
@click.option(
    "--block-pattern", multiple=True, help="Block patterns for tool names (glob/regex, can be used multiple times)"
)
@click.option("--allow-tool", multiple=True, help="Specific tool names to allow (can be used multiple times)")
@click.option("--block-tool", multiple=True, help="Specific tool names to block (can be used multiple times)")
@click.option(
    "--classify-tool",
    multiple=True,
    type=(str, click.Choice(["read", "write", "unknown"])),
    metavar="TOOL_NAME TYPE",
    help="Manual tool classification override (can be used multiple times)",
)
@click.pass_context
def add(
    ctx: click.Context,
    name: str,
    command: str | None,
    env: tuple[tuple[str, str], ...],
    cwd: str | None,
    tags: tuple[str, ...],
    oauth: bool,
    oauth_issuer: str | None,
    transport: str,
    url: str | None,
    enabled: bool,
    timeout: int | None,
    retry_attempts: int | None,
    retry_delay: int | None,
    health_check: bool | None,
    tool_namespace: str | None,
    resource_namespace: str | None,
    priority: int | None,
    log_level: str | None,
    header: tuple[tuple[str, str], ...],
    read_only: bool | None,
    allow_pattern: tuple[str, ...],
    block_pattern: tuple[str, ...],
    allow_tool: tuple[str, ...],
    block_tool: tuple[str, ...],
    classify_tool: tuple[tuple[str, str], ...],
) -> None:
    """Add new MCP server.

    For stdio transport, provide the complete command as a single string.

    Examples:
      foxxy-bridge mcp add fs 'npx @modelcontextprotocol/server-filesystem .'
      foxxy-bridge mcp add context7 'npx -y mcp-remote https://mcp.context7.com/se'
      foxxy-bridge mcp add github 'uvx mcp-server-github' --env GITHUB_TOKEN mytoken
    """
    # Normalize server name for consistency with OAuth token storage
    normalized_name = _validate_server_name(name)
    if normalized_name != name:
        ctx.obj["console"].print(f"[yellow]Server name normalized: '{name}' → '{normalized_name}'[/yellow]")

    # Parse command string into command and args for stdio transport
    server_command = None
    server_args = []

    if command:
        try:
            command_parts = shlex.split(command)
            if command_parts:
                server_command = command_parts[0]
                server_args = command_parts[1:]
        except ValueError as e:
            ctx.obj["console"].print(f"[red]Error: Invalid command string: {e}[/red]")
            raise click.Abort from e

    # Validate transport-specific requirements
    if transport in ("sse", "http", "streamablehttp"):
        if not url:
            ctx.obj["console"].print(f"[red]Error: --url is required for {transport} transport[/red]")
            raise click.Abort
        if server_command is not None and server_command != "":
            ctx.obj["console"].print(
                f"[yellow]Warning: command '{command}' ignored for {transport} transport (using URL)[/yellow]"
            )
    else:
        # stdio transport
        if not server_command:
            ctx.obj["console"].print("[red]Error: command is required for stdio transport[/red]")
            raise click.Abort
        if url:
            ctx.obj["console"].print("[yellow]Warning: --url ignored for stdio transport[/yellow]")

    args = SimpleNamespace(
        name=normalized_name,
        server_command=server_command,
        server_args=server_args,
        env=[builtins.list(e) for e in env],  # Convert tuples to lists
        cwd=cwd,
        tags=builtins.list(tags),
        oauth=oauth,
        oauth_issuer=oauth_issuer,
        transport=transport,
        url=url,
        enabled=enabled,
        timeout=timeout,
        retry_attempts=retry_attempts,
        retry_delay=retry_delay,
        health_check=health_check,
        tool_namespace=tool_namespace,
        resource_namespace=resource_namespace,
        priority=priority,
        log_level=log_level,
        headers=[builtins.list(h) for h in header],  # Convert header tuples to lists
        read_only=read_only,
        allow_patterns=builtins.list(allow_pattern),
        block_patterns=builtins.list(block_pattern),
        allow_tools=builtins.list(allow_tool),
        block_tools=builtins.list(block_tool),
        classify_tools=[builtins.list(c) for c in classify_tool],  # Convert classification tuples to lists
    )

    asyncio.run(
        handle_mcp_add(args, ctx.obj["config_path"], ctx.obj["config_dir"], ctx.obj["console"], ctx.obj["logger"])
    )


@mcp.command()
@click.argument("name")
@click.option("--force", "-F", is_flag=True, help="Force removal without confirmation")
@click.pass_context
def remove(ctx: click.Context, name: str, force: bool) -> None:
    """Remove MCP server."""
    args = SimpleNamespace(name=name, force=force)

    asyncio.run(
        handle_mcp_remove(args, ctx.obj["config_path"], ctx.obj["config_dir"], ctx.obj["console"], ctx.obj["logger"])
    )


@mcp.command("list")
@click.option("--format", "-f", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def list_servers(ctx: click.Context, format: str) -> None:  # noqa: A002
    """List configured MCP servers."""
    args = SimpleNamespace(format=format)

    asyncio.run(
        handle_mcp_list(args, ctx.obj["config_path"], ctx.obj["config_dir"], ctx.obj["console"], ctx.obj["logger"])
    )


@mcp.command("status")
@click.argument("name", required=False)
@click.option("--format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def status_mcp(ctx: click.Context, name: str | None, format: str) -> None:  # noqa: A002
    """Show MCP server status, connection state, and discovered tools.

    Shows running servers with their connection status, tool counts,
    and security information including suppressed tools.
    """
    args = SimpleNamespace(name=name, format=format)

    asyncio.run(
        handle_mcp_status(args, ctx.obj["config_path"], ctx.obj["config_dir"], ctx.obj["console"], ctx.obj["logger"])
    )


@mcp.command()
@click.argument("name")
@click.pass_context
def enable(ctx: click.Context, name: str) -> None:
    """Enable MCP server."""
    console.print(f"[green]Enabling server '{name}'[/green]")
    console.print("[yellow]Enable command not yet implemented[/yellow]")


@mcp.command()
@click.argument("name")
@click.pass_context
def disable(ctx: click.Context, name: str) -> None:
    """Disable MCP server."""
    console.print(f"[red]Disabling server '{name}'[/red]")
    console.print("[yellow]Disable command not yet implemented[/yellow]")


@mcp.command("restart")
@click.argument("server_name")
@click.pass_context
def restart_server(ctx: click.Context, server_name: str) -> None:
    """Restart/reconnect MCP server.

    Examples:
      foxxy-bridge mcp restart filesystem
      foxxy-bridge mcp restart github
    """
    args = SimpleNamespace(server_name=server_name)

    asyncio.run(
        handle_mcp_restart(args, ctx.obj["config_path"], ctx.obj["config_dir"], ctx.obj["console"], ctx.obj["logger"])
    )


@mcp.command()
@click.argument("server_name")
@click.option("--follow", "-f", is_flag=True, help="Follow log output (tail mode)")
@click.option("--lines", "-n", default=50, type=int, help="Number of lines to show (default: 50)")
@click.pass_context
def logs(ctx: click.Context, server_name: str, follow: bool, lines: int) -> None:
    """View or tail logs for an MCP server.

    Examples:
      foxxy-bridge mcp logs filesystem
      foxxy-bridge mcp logs github --follow
      foxxy-bridge mcp logs filesystem -n 100
    """
    args = SimpleNamespace(server_name=server_name, follow=follow, lines=lines)

    asyncio.run(
        handle_mcp_logs(args, ctx.obj["config_path"], ctx.obj["config_dir"], ctx.obj["console"], ctx.obj["logger"])
    )


@mcp.group("config")
@click.pass_context
def server_config(ctx: click.Context) -> None:
    """Manage MCP server configurations."""


@server_config.command("set")
@click.argument("server_name")
@click.argument("key")
@click.argument("value")
@click.pass_context
def set_server_config(ctx: click.Context, server_name: str, key: str, value: str) -> None:
    """Set MCP server configuration option.

    Examples:
      foxxy-bridge mcp config set filesystem timeout 120
      foxxy-bridge mcp config set github enabled true
    """
    args = argparse.Namespace(server_name=server_name, key=key, value=value)

    asyncio.run(_mcp_config_set(args, ctx.obj["config_path"], ctx.obj["console"], ctx.obj["logger"]))


@server_config.command("get")
@click.argument("server_name")
@click.argument("key")
@click.pass_context
def get_server_config(ctx: click.Context, server_name: str, key: str) -> None:
    """Get MCP server configuration value."""
    args = argparse.Namespace(server_name=server_name, key=key)

    asyncio.run(_mcp_config_get(args, ctx.obj["config_path"], ctx.obj["console"], ctx.obj["logger"]))


@server_config.command("unset")
@click.argument("server_name")
@click.argument("key")
@click.pass_context
def unset_server_config(ctx: click.Context, server_name: str, key: str) -> None:
    """Unset MCP server configuration option.

    Examples:
      foxxy-bridge mcp config unset filesystem timeout
      foxxy-bridge mcp config unset github enabled
    """
    args = argparse.Namespace(server_name=server_name, key=key)

    asyncio.run(_mcp_config_unset(args, ctx.obj["config_path"], ctx.obj["console"], ctx.obj["logger"]))


@server_config.command("show")
@click.argument("name", required=False)
@click.option("--format", type=click.Choice(["json", "yaml"]), default="yaml", help="Output format")
@click.pass_context
def show_server_config(ctx: click.Context, name: str | None, format: str) -> None:  # noqa: A002
    """Show MCP server details."""
    args = SimpleNamespace(name=name, format=format)

    asyncio.run(
        handle_mcp_show(args, ctx.obj["config_path"], ctx.obj["config_dir"], ctx.obj["console"], ctx.obj["logger"])
    )


@cli.group()
@click.pass_context
def server(ctx: click.Context) -> None:
    """Manage bridge server and MCP server monitoring."""


@server.command("status")
@click.argument("name", required=False)
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.option("--watch", "-w", is_flag=True, help="Watch for status changes (requires full API)")
@click.option("--api", "-a", is_flag=True, help="Show full API status (loads config, slower)")
@click.pass_context
def status(ctx: click.Context, name: str | None, format: str, watch: bool, api: bool) -> None:  # noqa: A002
    """Show server status.

    By default shows fast daemon-only status without loading configuration.
    Use --api for full server status including tool counts and health details.
    """
    args = SimpleNamespace(server_command="status", name=name, format=format, watch=watch, api=api)

    asyncio.run(
        handle_server_status(args, ctx.obj["config_path"], ctx.obj["config_dir"], ctx.obj["console"], ctx.obj["logger"])
    )


@server.command("start")
@click.option("--config-file", help="Configuration file path")
@click.option("--port", "-p", type=int, help="Server port")
@click.option("--host", help="Server host")
@click.option("--name", "-n", help="Daemon name (auto-generated from config if not provided)")
@click.option("--detach", is_flag=True, help="Run in background")
@click.pass_context
def start(
    ctx: click.Context, config_file: str | None, port: int | None, host: str | None, name: str | None, detach: bool
) -> None:
    """Start bridge server."""
    args = SimpleNamespace(
        daemon_command="start",
        config=config_file,
        port=port,
        host=host,
        name=name,
        detach=detach,
        debug=ctx.obj["debug"],
    )

    asyncio.run(
        handle_server_start(args, ctx.obj["config_path"], ctx.obj["config_dir"], ctx.obj["console"], ctx.obj["logger"])
    )


@server.command("list")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def list_daemons(ctx: click.Context, format: str) -> None:  # noqa: A002
    """List running bridge daemons."""
    args = SimpleNamespace(format=format)

    asyncio.run(
        handle_server_list(args, ctx.obj["config_path"], ctx.obj["config_dir"], ctx.obj["console"], ctx.obj["logger"])
    )


@server.command("stop")
@click.option("--force", "-F", is_flag=True, help="Force stop")
@click.option("--name", "-n", help="Daemon name to stop (stop all if not provided)")
@click.pass_context
def stop(ctx: click.Context, force: bool, name: str | None) -> None:
    """Stop bridge server."""
    args = SimpleNamespace(daemon_command="stop", force=force, name=name)

    asyncio.run(
        handle_server_stop(args, ctx.obj["config_path"], ctx.obj["config_dir"], ctx.obj["console"], ctx.obj["logger"])
    )


@server.command("restart")
@click.option("--force", "-F", is_flag=True, help="Force restart")
@click.option("--config-file", help="Configuration file path")
@click.option("--port", "-p", type=int, help="Server port")
@click.option("--host", help="Server host")
@click.option("--name", "-n", help="Daemon name to restart")
@click.pass_context
def restart(
    ctx: click.Context, force: bool, config_file: str | None, port: int | None, host: str | None, name: str | None
) -> None:
    """Restart bridge server."""
    args = SimpleNamespace(daemon_command="restart", force=force, config=config_file, port=port, host=host, name=name)

    asyncio.run(
        handle_server_restart(
            args, ctx.obj["config_path"], ctx.obj["config_dir"], ctx.obj["console"], ctx.obj["logger"]
        )
    )


@cli.group()
@click.pass_context
def tool(ctx: click.Context) -> None:
    """Discover and test MCP tools."""


@tool.command("list")
@click.argument("server", required=False)
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.option("--tag", help="Filter by server tag")
@click.pass_context
def list_tools(ctx: click.Context, server: str | None, format: str, tag: str | None) -> None:  # noqa: A002
    """List available tools."""
    args = SimpleNamespace(tool_command="list", server=server, format=format, tag=tag)

    asyncio.run(
        handle_tool_list(args, ctx.obj["config_path"], ctx.obj["config_dir"], ctx.obj["console"], ctx.obj["logger"])
    )


@cli.group()
@click.pass_context
def oauth(ctx: click.Context) -> None:
    """Manage OAuth authentication."""


@oauth.command("status")
@click.argument("name", required=False)
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def status_oauth(ctx: click.Context, name: str | None, format: str) -> None:  # noqa: A002
    """Show OAuth status for all servers or a specific server."""
    args = SimpleNamespace(oauth_command="status", name=name, format=format)

    asyncio.run(
        handle_oauth_status(args, ctx.obj["config_path"], ctx.obj["config_dir"], ctx.obj["console"], ctx.obj["logger"])
    )


@oauth.command("login")
@click.argument("name")
@click.option("--force", "-F", is_flag=True, help="Force re-authentication")
@click.pass_context
def login_oauth(ctx: click.Context, name: str, force: bool) -> None:
    """Trigger OAuth login for a server."""
    args = SimpleNamespace(oauth_command="login", name=name, force=force)

    asyncio.run(
        handle_oauth_login(args, ctx.obj["config_path"], ctx.obj["config_dir"], ctx.obj["console"], ctx.obj["logger"])
    )


@oauth.command("logout")
@click.argument("name")
@click.option("--all", is_flag=True, help="Clear all OAuth tokens")
@click.pass_context
def logout_oauth(ctx: click.Context, name: str, all_tokens: bool) -> None:
    """Clear OAuth tokens for a server."""
    args = SimpleNamespace(oauth_command="logout", name=name, all=all_tokens)

    asyncio.run(
        handle_oauth_logout(args, ctx.obj["config_path"], ctx.obj["config_dir"], ctx.obj["console"], ctx.obj["logger"])
    )


if __name__ == "__main__":
    cli()
