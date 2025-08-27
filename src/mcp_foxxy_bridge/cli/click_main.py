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

import asyncio
from pathlib import Path

import click
import rich_click as click  # Use rich-click for better formatting
from rich.console import Console

from ..utils.config_migration import get_config_dir
from ..utils.logging import setup_logging

def print_version(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    try:
        from importlib.metadata import version
        ver = version("mcp-foxxy-bridge")
    except ImportError:
        ver = "1.5.0"
    click.echo(f"foxxy-bridge, version {ver}")
    ctx.exit()

# Configure rich-click for better help output
click.rich_click.USE_RICH_MARKUP = True
click.rich_click.USE_MARKDOWN = True
click.rich_click.SHOW_ARGUMENTS = True
click.rich_click.GROUP_ARGUMENTS_OPTIONS = True

console = Console()


# Global options that apply to all commands
@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--config-dir", "-C", type=click.Path(exists=False, path_type=Path),
              help="Configuration directory path (default: ~/.config/foxxy-bridge/)")
@click.option("--config", "-c", type=click.Path(exists=False, path_type=Path),
              envvar="FOXXY_BRIDGE_CONFIG",
              help="Configuration file path (default: {config_dir}/config.json, env: FOXXY_BRIDGE_CONFIG)")
@click.option("--debug", "-d", is_flag=True, help="Enable debug logging")
@click.option("--no-color", is_flag=True, help="Disable colored output")
@click.option("-v", "--version", is_flag=True, expose_value=False, is_eager=True, 
              callback=print_version, help="Show version and exit")
@click.pass_context
def cli(ctx: click.Context, config_dir: Path | None, config: Path | None,
        debug: bool, no_color: bool) -> None:
    """CLI for managing MCP Foxxy Bridge configuration and operations."""
    # Configure console and logging
    if no_color:
        console._color_system = None

    logger = setup_logging(debug=debug)

    # Get config directory and config path
    if config_dir:
        from ..utils.path_security import validate_config_dir
        try:
            config_dir = validate_config_dir(config_dir)
        except Exception as e:
            console.print(f"[red]Error: Invalid config directory: {e}[/red]")
            raise click.Abort()
    else:
        config_dir = get_config_dir()

    # Determine config file path with priority: CLI arg > ENV var > default
    if config:
        from ..utils.path_security import validate_config_path
        try:
            config_path = validate_config_path(config)
        except Exception as e:
            console.print(f"[red]Error: Invalid config file path: {e}[/red]")
            raise click.Abort()
    else:
        config_path = config_dir / "config.json"

    # Store in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj["config_dir"] = config_dir
    ctx.obj["config_path"] = config_path
    ctx.obj["console"] = console
    ctx.obj["logger"] = logger


# Configuration management group
@cli.group()
@click.pass_context
def config(ctx: click.Context) -> None:
    """Manage bridge configuration settings."""


@config.command()
@click.option("--format", "-f", type=click.Choice(["json", "yaml"]), default="yaml",
              help="Output format")
@click.pass_context
def show(ctx: click.Context, format: str) -> None:
    """Show bridge configuration."""
    # Create a namespace-like object for compatibility
    from types import SimpleNamespace

    from .commands.mcp_handlers import handle_config_show

    args = SimpleNamespace(format=format, name=None)

    asyncio.run(handle_config_show(
        args, ctx.obj["config_path"], ctx.obj["config_dir"],
        ctx.obj["console"], ctx.obj["logger"]
    ))


@config.command()
@click.argument("key")
@click.argument("value")
@click.pass_context
def set(ctx: click.Context, key: str, value: str) -> None:
    """Set bridge configuration option.
    
    Examples:
      foxxy-bridge config set bridge.port 9000
      foxxy-bridge config set bridge.host 0.0.0.0
    """
    from types import SimpleNamespace
    from .commands.config import _config_set
    
    args = SimpleNamespace(key=key, value=value)
    
    asyncio.run(_config_set(
        args, ctx.obj["config_path"], 
        ctx.obj["console"], ctx.obj["logger"]
    ))


@config.command()
@click.argument("key")
@click.pass_context
def get(ctx: click.Context, key: str) -> None:
    """Get bridge configuration value."""
    from types import SimpleNamespace
    from .commands.config import _config_get
    
    args = SimpleNamespace(key=key)
    
    asyncio.run(_config_get(
        args, ctx.obj["config_path"],
        ctx.obj["console"], ctx.obj["logger"]
    ))


@config.command()
@click.argument("key")
@click.pass_context
def unset(ctx: click.Context, key: str) -> None:
    """Unset bridge configuration option.
    
    Examples:
      foxxy-bridge config unset security.tools.block_patterns
      foxxy-bridge config unset port
    """
    from types import SimpleNamespace
    from .commands.config import _config_unset
    
    args = SimpleNamespace(key=key)
    
    asyncio.run(_config_unset(
        args, ctx.obj["config_path"],
        ctx.obj["console"], ctx.obj["logger"]
    ))


@config.command()
@click.option("--fix", is_flag=True, help="Attempt to fix validation issues")
@click.pass_context
def validate(ctx: click.Context, fix: bool) -> None:
    """Validate configuration."""
    from types import SimpleNamespace

    from .commands.mcp_handlers import handle_config_validate

    args = SimpleNamespace(fix=fix)

    asyncio.run(handle_config_validate(
        args, ctx.obj["config_path"], ctx.obj["config_dir"],
        ctx.obj["console"], ctx.obj["logger"]
    ))


@config.command()
@click.option("--force", "-F", is_flag=True, help="Overwrite existing configuration")
@click.pass_context
def init(ctx: click.Context, force: bool) -> None:
    """Initialize configuration with defaults."""
    from types import SimpleNamespace

    from .commands.mcp_handlers import handle_config_init

    args = SimpleNamespace(force=force)

    asyncio.run(handle_config_init(
        args, ctx.obj["config_path"], ctx.obj["config_dir"],
        ctx.obj["console"], ctx.obj["logger"]
    ))


@config.group()
@click.pass_context
def security(ctx: click.Context) -> None:
    """Manage bridge security configuration."""


@security.command("show")
@click.option("--format", "-f", type=click.Choice(["json", "yaml"]), default="yaml",
              help="Output format")
@click.pass_context
def security_show(ctx: click.Context, format: str) -> None:
    """Show bridge security configuration."""
    from types import SimpleNamespace

    from .commands.security_handlers import handle_security_show

    args = SimpleNamespace(format=format)

    asyncio.run(handle_security_show(
        args, ctx.obj["config_path"], ctx.obj["config_dir"],
        ctx.obj["console"], ctx.obj["logger"]
    ))


@security.command("set")
@click.option("--read-only/--no-read-only", default=None, help="Set global read-only mode")
@click.option("--allow-pattern", multiple=True, help="Set allow patterns (replaces existing)")
@click.option("--block-pattern", multiple=True, help="Set block patterns (replaces existing)")
@click.option("--allow-tool", multiple=True, help="Set allow tools (replaces existing)")
@click.option("--block-tool", multiple=True, help="Set block tools (replaces existing)")
@click.option("--classify-tool", multiple=True, type=(str, click.Choice(["read", "write", "unknown"])),
              metavar="TOOL_NAME TYPE", help="Set tool classifications (replaces existing)")
@click.pass_context
def security_set(ctx: click.Context, read_only: bool, allow_pattern: tuple, block_pattern: tuple,
                allow_tool: tuple, block_tool: tuple, classify_tool: tuple) -> None:
    """Set bridge security configuration."""
    import builtins
    from types import SimpleNamespace

    from .commands.security_handlers import handle_security_set

    args = SimpleNamespace(
        read_only=read_only,
        allow_patterns=builtins.list(allow_pattern),
        block_patterns=builtins.list(block_pattern),
        allow_tools=builtins.list(allow_tool),
        block_tools=builtins.list(block_tool),
        classify_tools=[builtins.list(c) for c in classify_tool]
    )

    asyncio.run(handle_security_set(
        args, ctx.obj["config_path"], ctx.obj["config_dir"],
        ctx.obj["console"], ctx.obj["logger"]
    ))


# MCP server management group
@cli.group()
@click.pass_context
def mcp(ctx: click.Context) -> None:
    """Manage MCP servers."""


@mcp.command()
@click.argument("name")
@click.argument("server_command", required=False)
@click.argument("server_args", nargs=-1)
@click.option("--env", multiple=True, type=(str, str), metavar="KEY VALUE",
              help="Environment variables (can be used multiple times)")
@click.option("--cwd", help="Working directory")
@click.option("--tags", multiple=True, help="Server tags")
@click.option("--oauth", is_flag=True, help="Enable OAuth")
@click.option("--oauth-issuer", help="OAuth issuer URL")
@click.option("--transport", "-t", type=click.Choice(["stdio", "sse", "http"]),
              default="stdio", help="Server transport type")
@click.option("--url", "-u", help="Server URL (for SSE/HTTP transports)")
@click.option("--enabled/--disabled", default=True, help="Enable or disable the server")
@click.option("--timeout", type=int, help="Server timeout in seconds")
@click.option("--retry-attempts", type=int, help="Number of retry attempts on failure")
@click.option("--retry-delay", type=int, help="Delay between retry attempts in milliseconds")
@click.option("--health-check/--no-health-check", default=None, help="Enable or disable health checks")
@click.option("--tool-namespace", help="Namespace for server tools")
@click.option("--resource-namespace", help="Namespace for server resources")
@click.option("--priority", type=int, help="Server priority (higher = more priority)")
@click.option("--log-level", type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "QUIET"]),
              help="Server log level")
@click.option("--header", multiple=True, type=(str, str), metavar="KEY VALUE",
              help="HTTP headers (for HTTP/SSE transports, can be used multiple times)")
@click.option("--read-only/--no-read-only", default=None,
              help="Enable read-only mode for this server (overrides global setting)")
@click.option("--allow-pattern", multiple=True,
              help="Allow patterns for tool names (glob/regex, can be used multiple times)")
@click.option("--block-pattern", multiple=True,
              help="Block patterns for tool names (glob/regex, can be used multiple times)")
@click.option("--allow-tool", multiple=True,
              help="Specific tool names to allow (can be used multiple times)")
@click.option("--block-tool", multiple=True,
              help="Specific tool names to block (can be used multiple times)")
@click.option("--classify-tool", multiple=True, type=(str, click.Choice(["read", "write", "unknown"])),
              metavar="TOOL_NAME TYPE", help="Manual tool classification override (can be used multiple times)")
@click.pass_context
def add(ctx: click.Context, name: str, server_command: str | None, server_args: tuple,
        env: tuple, cwd: str | None, tags: tuple, oauth: bool,
        oauth_issuer: str | None, transport: str, url: str | None,
        enabled: bool, timeout: int | None, retry_attempts: int | None,
        retry_delay: int | None, health_check: bool | None, tool_namespace: str | None,
        resource_namespace: str | None, priority: int | None, log_level: str | None,
        header: tuple, read_only: bool | None, allow_pattern: tuple, block_pattern: tuple,
        allow_tool: tuple, block_tool: tuple, classify_tool: tuple) -> None:
    """Add new MCP server."""
    import builtins
    from types import SimpleNamespace

    from .commands.mcp_handlers import handle_mcp_add

    # Normalize server name for consistency with OAuth token storage
    from mcp_foxxy_bridge.oauth.utils import _validate_server_name
    normalized_name = _validate_server_name(name)
    if normalized_name != name:
        ctx.obj["console"].print(f"[yellow]Server name normalized: '{name}' → '{normalized_name}'[/yellow]")

    # Validate transport-specific requirements
    if transport in ("sse", "http", "streamablehttp"):
        if not url:
            ctx.obj["console"].print(f"[red]Error: --url is required for {transport} transport[/red]")
            raise click.Abort()
        if server_command is not None and server_command != "":
            ctx.obj["console"].print(f"[yellow]Warning: server_command '{server_command}' ignored for {transport} transport (using URL)[/yellow]")
    else:
        # stdio transport
        if not server_command:
            ctx.obj["console"].print("[red]Error: server_command is required for stdio transport[/red]")
            raise click.Abort()
        if url:
            ctx.obj["console"].print("[yellow]Warning: --url ignored for stdio transport[/yellow]")

    args = SimpleNamespace(
        name=normalized_name,
        server_command=server_command,
        server_args=builtins.list(server_args),
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
        classify_tools=[builtins.list(c) for c in classify_tool]  # Convert classification tuples to lists
    )

    asyncio.run(handle_mcp_add(
        args, ctx.obj["config_path"], ctx.obj["config_dir"],
        ctx.obj["console"], ctx.obj["logger"]
    ))


@mcp.command()
@click.argument("name")
@click.option("--force", "-F", is_flag=True, help="Force removal without confirmation")
@click.pass_context
def remove(ctx: click.Context, name: str, force: bool) -> None:
    """Remove MCP server."""
    from types import SimpleNamespace

    from .commands.mcp_handlers import handle_mcp_remove

    args = SimpleNamespace(name=name, force=force)

    asyncio.run(handle_mcp_remove(
        args, ctx.obj["config_path"], ctx.obj["config_dir"],
        ctx.obj["console"], ctx.obj["logger"]
    ))


@mcp.command()
@click.option("--format", "-f", type=click.Choice(["table", "json", "yaml"]),
              default="table", help="Output format")
@click.pass_context
def list(ctx: click.Context, format: str) -> None:
    """List configured MCP servers."""
    from types import SimpleNamespace

    from .commands.mcp_handlers import handle_mcp_list

    args = SimpleNamespace(format=format)

    asyncio.run(handle_mcp_list(
        args, ctx.obj["config_path"], ctx.obj["config_dir"],
        ctx.obj["console"], ctx.obj["logger"]
    ))


@mcp.command()
@click.argument("name", required=False)
@click.option("--format", type=click.Choice(["json", "yaml"]),
              default="yaml", help="Output format")
@click.pass_context
def show(ctx: click.Context, name: str | None, format: str) -> None:
    """Show MCP server details."""
    from types import SimpleNamespace

    from .commands.mcp_handlers import handle_mcp_show

    args = SimpleNamespace(name=name, format=format)

    asyncio.run(handle_mcp_show(
        args, ctx.obj["config_path"], ctx.obj["config_dir"],
        ctx.obj["console"], ctx.obj["logger"]
    ))


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


@mcp.command()
@click.argument("server_name")
@click.pass_context
def restart(ctx: click.Context, server_name: str) -> None:
    """Restart/reconnect MCP server.
    
    Examples:
      foxxy-bridge mcp restart filesystem
      foxxy-bridge mcp restart github
    """
    from types import SimpleNamespace
    from .commands.mcp_handlers import handle_mcp_restart
    
    args = SimpleNamespace(server_name=server_name)
    
    asyncio.run(handle_mcp_restart(
        args, ctx.obj["config_path"], ctx.obj["config_dir"],
        ctx.obj["console"], ctx.obj["logger"]
    ))


@mcp.group()
@click.pass_context
def config(ctx: click.Context) -> None:
    """Manage MCP server configurations."""


@config.command()
@click.argument("server_name")
@click.argument("key")
@click.argument("value")
@click.pass_context
def set(ctx: click.Context, server_name: str, key: str, value: str) -> None:
    """Set MCP server configuration option.
    
    Examples:
      foxxy-bridge mcp config set filesystem timeout 120
      foxxy-bridge mcp config set github enabled true
    """
    from types import SimpleNamespace
    from .commands.config import _mcp_config_set
    
    args = SimpleNamespace(server_name=server_name, key=key, value=value)
    
    asyncio.run(_mcp_config_set(
        args, ctx.obj["config_path"], 
        ctx.obj["console"], ctx.obj["logger"]
    ))


@config.command()
@click.argument("server_name")
@click.argument("key")
@click.pass_context
def get(ctx: click.Context, server_name: str, key: str) -> None:
    """Get MCP server configuration value."""
    from types import SimpleNamespace
    from .commands.config import _mcp_config_get
    
    args = SimpleNamespace(server_name=server_name, key=key)
    
    asyncio.run(_mcp_config_get(
        args, ctx.obj["config_path"], 
        ctx.obj["console"], ctx.obj["logger"]
    ))


@config.command()
@click.argument("server_name")
@click.argument("key")
@click.pass_context
def unset(ctx: click.Context, server_name: str, key: str) -> None:
    """Unset MCP server configuration option.
    
    Examples:
      foxxy-bridge mcp config unset filesystem timeout
      foxxy-bridge mcp config unset github enabled
    """
    from types import SimpleNamespace
    from .commands.config import _mcp_config_unset
    
    args = SimpleNamespace(server_name=server_name, key=key)
    
    asyncio.run(_mcp_config_unset(
        args, ctx.obj["config_path"], 
        ctx.obj["console"], ctx.obj["logger"]
    ))


@cli.group()
@click.pass_context
def server(ctx: click.Context) -> None:
    """Manage bridge server and MCP server monitoring."""


@server.command()
@click.argument("name", required=False)
@click.option("--format", type=click.Choice(["table", "json"]),
              default="table", help="Output format")
@click.option("--watch", "-w", is_flag=True, help="Watch for status changes (requires full API)")
@click.option("--api", "-a", is_flag=True, help="Show full API status (loads config, slower)")
@click.pass_context
def status(ctx: click.Context, name: str | None, format: str, watch: bool, api: bool) -> None:
    """Show server status.
    
    By default shows fast daemon-only status without loading configuration.
    Use --api for full server status including tool counts and health details.
    """
    from types import SimpleNamespace

    from .commands.server import handle_server_status

    args = SimpleNamespace(
        server_command="status",
        name=name,
        format=format,
        watch=watch,
        api=api
    )

    asyncio.run(handle_server_status(
        args, ctx.obj["config_path"], ctx.obj["config_dir"],
        ctx.obj["console"], ctx.obj["logger"]
    ))


@server.command()
@click.option("--config-file", help="Configuration file path")
@click.option("--port", "-p", type=int, help="Server port")
@click.option("--host", help="Server host")
@click.option("--name", "-n", help="Daemon name (auto-generated from config if not provided)")
@click.option("--detach", is_flag=True, help="Run in background")
@click.pass_context
def start(ctx: click.Context, config_file: str | None, port: int | None,
          host: str | None, name: str | None, detach: bool) -> None:
    """Start bridge server."""
    from types import SimpleNamespace

    from .commands.server import handle_server_start

    args = SimpleNamespace(
        daemon_command="start",
        config=config_file,
        port=port,
        host=host,
        name=name,
        detach=detach
    )

    asyncio.run(handle_server_start(
        args, ctx.obj["config_path"], ctx.obj["config_dir"],
        ctx.obj["console"], ctx.obj["logger"]
    ))


@server.command("list")
@click.option("--format", type=click.Choice(["table", "json"]),
              default="table", help="Output format")
@click.pass_context
def list_daemons(ctx: click.Context, format: str) -> None:
    """List running bridge daemons."""
    from types import SimpleNamespace
    
    from .commands.server import handle_server_list
    
    args = SimpleNamespace(format=format)
    
    asyncio.run(handle_server_list(
        args, ctx.obj["config_path"], ctx.obj["config_dir"],
        ctx.obj["console"], ctx.obj["logger"]
    ))


@server.command()
@click.option("--force", "-F", is_flag=True, help="Force stop")
@click.option("--name", "-n", help="Daemon name to stop (stop all if not provided)")
@click.pass_context
def stop(ctx: click.Context, force: bool, name: str | None) -> None:
    """Stop bridge server."""
    from types import SimpleNamespace

    from .commands.server import handle_server_stop

    args = SimpleNamespace(
        daemon_command="stop",
        force=force,
        name=name
    )

    asyncio.run(handle_server_stop(
        args, ctx.obj["config_path"], ctx.obj["config_dir"],
        ctx.obj["console"], ctx.obj["logger"]
    ))


@server.command()
@click.option("--force", "-F", is_flag=True, help="Force restart")
@click.option("--config-file", help="Configuration file path")
@click.option("--port", "-p", type=int, help="Server port")
@click.option("--host", help="Server host")
@click.option("--name", "-n", help="Daemon name to restart")
@click.pass_context
def restart(ctx: click.Context, force: bool, config_file: str | None,
            port: int | None, host: str | None, name: str | None) -> None:
    """Restart bridge server."""
    from types import SimpleNamespace

    from .commands.server import handle_server_restart

    args = SimpleNamespace(
        daemon_command="restart",
        force=force,
        config=config_file,
        port=port,
        host=host,
        name=name
    )

    asyncio.run(handle_server_restart(
        args, ctx.obj["config_path"], ctx.obj["config_dir"],
        ctx.obj["console"], ctx.obj["logger"]
    ))


@cli.group()
@click.pass_context
def tool(ctx: click.Context) -> None:
    """Discover and test MCP tools."""


@tool.command()
@click.argument("server", required=False)
@click.option("--format", type=click.Choice(["table", "json"]),
              default="table", help="Output format")
@click.option("--tag", help="Filter by server tag")
@click.pass_context
def list(ctx: click.Context, server: str | None, format: str, tag: str | None) -> None:
    """List available tools."""
    from types import SimpleNamespace

    from .commands.tool import handle_tool_list

    args = SimpleNamespace(
        tool_command="list",
        server=server,
        format=format,
        tag=tag
    )

    asyncio.run(handle_tool_list(
        args, ctx.obj["config_path"], ctx.obj["config_dir"],
        ctx.obj["console"], ctx.obj["logger"]
    ))


@cli.group()
@click.pass_context
def oauth(ctx: click.Context) -> None:
    """Manage OAuth authentication."""


@oauth.command()
@click.argument("name", required=False)
@click.option("--format", type=click.Choice(["table", "json"]),
              default="table", help="Output format")
@click.pass_context
def status(ctx: click.Context, name: str | None, format: str) -> None:
    """Show OAuth status."""
    from types import SimpleNamespace

    from .commands.oauth import handle_oauth_status

    args = SimpleNamespace(
        oauth_command="status",
        name=name,
        format=format
    )

    asyncio.run(handle_oauth_status(
        args, ctx.obj["config_path"], ctx.obj["config_dir"],
        ctx.obj["console"], ctx.obj["logger"]
    ))


if __name__ == "__main__":
    cli()
