#
# MCP Foxxy Bridge - Tool Management Commands
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
"""Tool discovery and testing CLI commands."""

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import aiohttp
from rich.console import Console
from rich.prompt import Confirm

from mcp_foxxy_bridge.cli.api_client import get_api_client_from_config
from mcp_foxxy_bridge.cli.formatters import ToolFormatter


async def handle_tool_list(
    args: Any,
    config_path: Path,
    config_dir: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Handle tool listing command from Click CLI.

    Args:
        args: Click command arguments containing server, format, and tag filters
        config_path: Path to the configuration file
        config_dir: Configuration directory (unused)
        console: Rich console for output
        logger: Logger for error reporting

    Lists available tools from MCP servers with filtering and formatting options.
    """
    # Convert to argparse-style namespace for compatibility
    argparse_args = argparse.Namespace(
        tool_command="list",
        server=getattr(args, "server", None),
        format=getattr(args, "format", "table"),
        tag=getattr(args, "tag", None),
    )
    await _tool_list(argparse_args, config_path, console, logger)


async def handle_tool_command(
    args: argparse.Namespace,
    config_path: Path,
    config_dir: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Handle tool discovery, testing, and management commands.

    Args:
        args: Command line arguments with tool_command subcommand
        config_path: Path to the configuration file
        config_dir: Configuration directory (unused)
        console: Rich console for output
        logger: Logger for error reporting

    Routes to appropriate tool subcommand handler (list, test, call, search).
    """
    # Check if no subcommand was provided
    if not hasattr(args, "tool_command") or args.tool_command is None:
        console.print("[yellow]Usage: foxxy-bridge tool <command>[/yellow]")
        console.print("Available commands: list, test, call, search")
        return

    if args.tool_command == "list":
        await _tool_list(args, config_path, console, logger)
    elif args.tool_command == "test":
        await _tool_test(args, config_path, console, logger)
    elif args.tool_command == "call":
        await _tool_call(args, config_path, console, logger)
    elif args.tool_command == "search":
        await _tool_search(args, config_path, console, logger)
    else:
        console.print(f"[red]Unknown tool command: {args.tool_command}[/red]")


async def _tool_list(
    args: argparse.Namespace,
    config_path: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """List available tools from MCP servers.

    Args:
        args: Command line arguments with server, format, and tag filters
        config_path: Path to the configuration file
        console: Rich console for output
        logger: Logger for error reporting

    Supports filtering by server, tag, or showing all tools.
    Output formats include table and JSON.
    """
    """List available tools."""
    try:
        api_client = get_api_client_from_config(str(config_path), console)

        if args.server:
            # List tools for specific server
            tools_data = await api_client.list_server_tools(args.server)
        elif args.tag:
            # List tools by tag
            tools_data = await api_client.list_tools_by_tag(args.tag)
        else:
            # List all tools
            tools_data = await api_client.list_all_tools()

        if args.format == "json":
            console.print(json.dumps(tools_data, indent=2))
        else:
            ToolFormatter.format_tools_table(tools_data, console)

            # Show summary
            console.print(f"\n[dim]Total: {len(tools_data)} tool(s)[/dim]")

    except aiohttp.ClientError as e:
        console.print(f"[red]Failed to list tools: {e}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Failed to list tools")


async def _tool_test(
    args: argparse.Namespace,
    config_path: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Test connectivity and functionality of MCP server tools.

    Args:
        args: Command line arguments with server and test options
        config_path: Path to the configuration file
        console: Rich console for output
        logger: Logger for error reporting

    Tests that tools are available and callable from the specified server.
    Useful for verifying server configuration and connectivity.
    """
    """Test tool functionality."""
    try:
        api_client = get_api_client_from_config(str(config_path), console)

        # First, find the tool
        if args.server:
            tools_data = await api_client.list_server_tools(args.server)
        else:
            tools_data = await api_client.list_all_tools()

        matching_tools = [tool for tool in tools_data if tool.get("name") == args.name]

        if not matching_tools:
            console.print(f"[red]Tool '{args.name}' not found[/red]")
            return

        if len(matching_tools) > 1 and not args.server:
            console.print(f"[yellow]Multiple tools named '{args.name}' found:[/yellow]")
            for tool in matching_tools:
                console.print(f"  - {tool.get('server', 'unknown')}")
            console.print("[yellow]Please specify --server to disambiguate[/yellow]")
            return

        tool = matching_tools[0]
        server_name = tool.get("server", "unknown")

        if args.dry_run:
            console.print(
                f"[blue]Would test tool '[cyan]{args.name}[/cyan]' on server '[cyan]{server_name}[/cyan]'[/blue]"
            )
            console.print(f"Description: {tool.get('description', 'No description')}")
            if "inputSchema" in tool:
                console.print("Input Schema:")
                console.print(json.dumps(tool["inputSchema"], indent=2))
            return

        # Perform basic test (call without arguments)
        console.print(f"Testing tool '[cyan]{args.name}[/cyan]' on server '[cyan]{server_name}[/cyan]'...")

        try:
            result = await api_client.call_tool(server_name, args.name, {})
            ToolFormatter.format_tool_call_result(result, console)

        except aiohttp.ClientError as e:
            # This is expected for tools that require arguments
            if "arguments" in str(e).lower() or "required" in str(e).lower():
                console.print("[yellow]Tool requires arguments (this is normal)[/yellow]")
                console.print("Tool test completed - server connection OK")
            else:
                console.print(f"[red]Tool test failed: {e}[/red]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Failed to test tool")


async def _tool_call(
    args: argparse.Namespace,
    config_path: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Execute a specific tool with provided arguments.

    Args:
        args: Command line arguments with server, tool name, and arguments
        config_path: Path to the configuration file
        console: Rich console for output
        logger: Logger for error reporting

    Calls the specified tool on the given server with provided arguments.
    Prompts for confirmation if force flag is not used.
    """
    """Execute a tool with arguments."""
    try:
        api_client = get_api_client_from_config(str(config_path), console)

        # Parse arguments
        arguments = {}
        if args.args:
            try:
                arguments = json.loads(args.args)
            except json.JSONDecodeError as e:
                console.print(f"[red]Invalid JSON arguments: {e}[/red]")
                return
        elif args.input_file:
            try:
                # Read file content
                arguments = json.loads(Path(args.input_file).read_text())
            except (FileNotFoundError, json.JSONDecodeError) as e:
                console.print(f"[red]Error reading input file: {e}[/red]")
                return

        # Find the tool if server not specified
        if not args.server:
            tools_data = await api_client.list_all_tools()
            matching_tools = [tool for tool in tools_data if tool.get("name") == args.name]

            if not matching_tools:
                console.print(f"[red]Tool '{args.name}' not found[/red]")
                return

            if len(matching_tools) > 1:
                console.print(f"[yellow]Multiple tools named '{args.name}' found:[/yellow]")
                for tool in matching_tools:
                    console.print(f"  - {tool.get('server', 'unknown')}")
                console.print("[yellow]Please specify --server to disambiguate[/yellow]")
                return

            server_name = matching_tools[0].get("server", "unknown")
        else:
            server_name = args.server

        # Show what we're about to do
        console.print(f"Calling tool '[cyan]{args.name}[/cyan]' on server '[cyan]{server_name}[/cyan]'")
        if arguments:
            console.print(f"Arguments: {json.dumps(arguments, indent=2)}")

        # Confirm execution for potentially dangerous operations
        if not Confirm.ask("Execute tool?"):
            console.print("[yellow]Operation cancelled[/yellow]")
            return

        # Execute the tool
        with console.status("Executing tool..."):
            result = await api_client.call_tool(server_name, args.name, arguments)

        ToolFormatter.format_tool_call_result(result, console)

    except aiohttp.ClientError as e:
        console.print(f"[red]Tool execution failed: {e}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Failed to execute tool")


async def _tool_search(
    args: argparse.Namespace,
    config_path: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Search for tools matching specified criteria.

    Args:
        args: Command line arguments with search pattern and filters
        config_path: Path to the configuration file
        console: Rich console for output
        logger: Logger for error reporting

    Searches tool names and descriptions for matching patterns.
    Supports filtering by server and output formatting options.
    """
    try:
        api_client = get_api_client_from_config(str(config_path), console)

        # Get tools to search
        if args.server:
            tools_data = await api_client.list_server_tools(args.server)
        else:
            tools_data = await api_client.list_all_tools()

        # Filter tools by search pattern
        pattern_lower = args.pattern.lower()
        matching_tools = []

        for tool in tools_data:
            name = tool.get("name", "").lower()
            description = tool.get("description", "").lower()

            if pattern_lower in name or (args.description and pattern_lower in description):
                matching_tools.append(tool)

        if not matching_tools:
            console.print(f"[yellow]No tools found matching '[cyan]{args.pattern}[/cyan]'[/yellow]")
            return

        console.print(f"Found {len(matching_tools)} tool(s) matching '[cyan]{args.pattern}[/cyan]':")
        ToolFormatter.format_tools_table(matching_tools, console)

    except aiohttp.ClientError as e:
        console.print(f"[red]Failed to search tools: {e}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Failed to search tools")
