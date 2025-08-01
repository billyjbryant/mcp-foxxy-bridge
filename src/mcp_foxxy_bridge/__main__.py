#
# MCP Foxxy Bridge - Main Entry Point
#
# Copyright (C) 2024 Billy Bryant
# Portions copyright (C) 2024 Sergey Parfenyuk (original MIT-licensed author)
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
# MIT License attribution: Portions of this file were originally licensed
# under the MIT License by Sergey Parfenyuk (2024).
#
"""The entry point for the mcp-foxxy-bridge application.

It sets up the logging and runs the main function.

Two ways to run the application:
1. Run the application as a module `uv run -m mcp_foxxy_bridge`
2. Run the application as a package `uv run mcp-foxxy-bridge`

"""

import argparse
import asyncio
import json
import logging
import os
import shlex
import sys
import typing as t
from importlib.metadata import version
from pathlib import Path

from mcp.client.stdio import StdioServerParameters

from .config_loader import (
    BridgeConfiguration,
    load_bridge_config_from_file,
    load_named_server_configs_from_file,
)
from .logging_config import setup_rich_logging
from .mcp_server import MCPServerSettings, run_bridge_server
from .sse_client import run_sse_client
from .streamablehttp_client import run_streamablehttp_client

# Deprecated env var. Here for backwards compatibility.
SSE_URL: t.Final[str | None] = os.getenv(
    "SSE_URL",
    None,
)


def _setup_argument_parser() -> argparse.ArgumentParser:
    """Set up and return the argument parser for the MCP proxy."""
    parser = argparse.ArgumentParser(
        description=("Start the MCP proxy in one of two possible modes: as a client or a server."),
        epilog=(
            "Examples:\n"
            "  mcp-foxxy-bridge http://localhost:8080/sse\n"
            "  mcp-foxxy-bridge --transport streamablehttp http://localhost:8080/mcp\n"
            "  mcp-foxxy-bridge --headers Authorization 'Bearer YOUR_TOKEN' http://localhost:8080/sse\n"
            "  mcp-foxxy-bridge --port 8080 -- your-command --arg1 value1 --arg2 value2\n"
            "  mcp-foxxy-bridge --named-server fetch 'uvx mcp-server-fetch' --port 8080\n"
            "  mcp-foxxy-bridge your-command --port 8080 -e KEY VALUE "  # Line split
            "-e ANOTHER_KEY ANOTHER_VALUE\n"
            "  mcp-foxxy-bridge your-command --port 8080 --allow-origin='*'\n"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )

    _add_arguments_to_parser(parser)
    return parser


def _add_arguments_to_parser(parser: argparse.ArgumentParser) -> None:
    """Add all arguments to the argument parser."""
    try:
        package_version = version("mcp-foxxy-bridge")
    except Exception:  # noqa: BLE001
        try:
            # Try to read from VERSION file
            version_file = Path(__file__).parent.parent.parent / "VERSION"
            if version_file.exists():
                package_version = version_file.read_text().strip()
            else:
                package_version = "unknown"
        except Exception:  # noqa: BLE001
            package_version = "unknown"

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {package_version}",
        help="Show the version and exit",
    )

    parser.add_argument(
        "command_or_url",
        help=(
            "Command or URL to connect to. When a URL, will run an SSE/StreamableHTTP client. "
            "Otherwise, if --named-server is not used, this will be the command "
            "for the default stdio client. If --named-server is used, this argument "
            "is ignored for stdio mode unless no default server is desired. "
            "See corresponding options for more details."
        ),
        nargs="?",
        default=SSE_URL,
    )

    client_group = parser.add_argument_group("SSE/StreamableHTTP client options")
    client_group.add_argument(
        "-H",
        "--headers",
        nargs=2,
        action="append",
        metavar=("KEY", "VALUE"),
        help="Headers to pass to the SSE server. Can be used multiple times.",
        default=[],
    )
    client_group.add_argument(
        "--transport",
        choices=["sse", "streamablehttp"],
        default="sse",  # For backwards compatibility
        help="The transport to use for the client. Default is SSE.",
    )

    stdio_client_options = parser.add_argument_group("stdio client options")
    stdio_client_options.add_argument(
        "args",
        nargs="*",
        help=(
            "Any extra arguments to the command to spawn the default server. "
            "Ignored if only named servers are defined."
        ),
    )
    stdio_client_options.add_argument(
        "-e",
        "--env",
        nargs=2,
        action="append",
        metavar=("KEY", "VALUE"),
        help=(
            "Environment variables used when spawning the default server. Can be "
            "used multiple times. For named servers, environment is inherited or "
            "passed via --pass-environment."
        ),
        default=[],
    )
    stdio_client_options.add_argument(
        "--cwd",
        default=None,
        help=(
            "The working directory to use when spawning the default server process. "
            "Named servers inherit the proxy's CWD."
        ),
    )
    stdio_client_options.add_argument(
        "--pass-environment",
        action=argparse.BooleanOptionalAction,
        help="Pass through all environment variables when spawning all server processes.",
        default=False,
    )
    stdio_client_options.add_argument(
        "--debug",
        action=argparse.BooleanOptionalAction,
        help="Enable debug mode with detailed logging output.",
        default=False,
    )
    stdio_client_options.add_argument(
        "--named-server",
        action="append",
        nargs=2,
        metavar=("NAME", "COMMAND_STRING"),
        help=(
            "Define a named stdio server. NAME is for the URL path /servers/NAME/. "
            "COMMAND_STRING is a single string with the command and its arguments "
            "(e.g., 'uvx mcp-server-fetch --timeout 10'). "
            "These servers inherit the proxy's CWD and environment from --pass-environment."
        ),
        default=[],
        dest="named_server_definitions",
    )
    stdio_client_options.add_argument(
        "--named-server-config",
        type=str,
        default=None,
        metavar="FILE_PATH",
        help=(
            "Path to a JSON configuration file for named stdio servers. "
            "If provided, this will be the exclusive source for named server definitions, "
            "and any --named-server CLI arguments will be ignored."
        ),
    )
    stdio_client_options.add_argument(
        "--bridge-config",
        type=str,
        default=os.getenv("MCP_BRIDGE_CONFIG", "config.json"),
        metavar="FILE_PATH",
        help=(
            "Path to a bridge configuration file (JSON format). "
            "Defaults to 'config.json' in the current directory, "
            "or MCP_BRIDGE_CONFIG environment variable. "
            "When provided, starts the bridge server that aggregates multiple MCP servers. "
            "This mode ignores all other server configuration options."
        ),
    )

    mcp_server_group = parser.add_argument_group("SSE server options")
    mcp_server_group.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to expose an SSE server on. Default is 8080",
    )
    mcp_server_group.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to expose an SSE server on. Default is 127.0.0.1",
    )
    mcp_server_group.add_argument(
        "--stateless",
        action=argparse.BooleanOptionalAction,
        help="Enable stateless mode for streamable http transports. Default is False",
        default=False,
    )
    mcp_server_group.add_argument(
        "--sse-port",
        type=int,
        default=0,
        help="(deprecated) Same as --port",
    )
    mcp_server_group.add_argument(
        "--sse-host",
        default="127.0.0.1",
        help="(deprecated) Same as --host",
    )
    mcp_server_group.add_argument(
        "--allow-origin",
        nargs="+",
        default=[],
        help=(
            "Allowed origins for the SSE server. Can be used multiple times. "
            "Default is no CORS allowed."
        ),
    )


def _setup_logging(*, debug: bool) -> logging.Logger:
    """Set up Rich-based logging configuration and return the logger."""
    return setup_rich_logging(debug=debug)


def _handle_sse_client_mode(
    args_parsed: argparse.Namespace,
    logger: logging.Logger,
) -> None:
    """Handle SSE/StreamableHTTP client mode operation."""
    if args_parsed.named_server_definitions:
        logger.warning(
            "--named-server arguments are ignored when command_or_url is an HTTP/HTTPS URL "
            "(SSE/StreamableHTTP client mode).",
        )
    # Start a client connected to the SSE server, and expose as a stdio server
    logger.debug("Starting SSE/StreamableHTTP client and stdio server")
    headers = dict(args_parsed.headers)
    if api_access_token := os.getenv("API_ACCESS_TOKEN", None):
        headers["Authorization"] = f"Bearer {api_access_token}"

    if args_parsed.transport == "streamablehttp":
        asyncio.run(run_streamablehttp_client(args_parsed.command_or_url, headers=headers))
    else:
        asyncio.run(run_sse_client(args_parsed.command_or_url, headers=headers))


def _configure_default_server(
    args_parsed: argparse.Namespace,
    base_env: dict[str, str],
    logger: logging.Logger,
) -> StdioServerParameters | None:
    """Configure the default server if applicable."""
    if not (
        args_parsed.command_or_url
        and not args_parsed.command_or_url.startswith(("http://", "https://"))
    ):
        return None

    default_server_env = base_env.copy()
    default_server_env.update(dict(args_parsed.env))  # Specific env vars for default server

    default_stdio_params = StdioServerParameters(
        command=args_parsed.command_or_url,
        args=args_parsed.args,
        env=default_server_env,
        cwd=args_parsed.cwd if args_parsed.cwd else None,
    )
    logger.info(
        "Configured default server: %s %s",
        args_parsed.command_or_url,
        " ".join(args_parsed.args),
    )
    return default_stdio_params


def _load_named_servers_from_config(
    config_path: str,
    base_env: dict[str, str],
    logger: logging.Logger,
) -> dict[str, StdioServerParameters]:
    """Load named server configurations from a file."""
    try:
        return load_named_server_configs_from_file(config_path, base_env)
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        # Specific errors are already logged by the loader function
        # We log a generic message here before exiting
        logger.exception(
            "Failed to load server configurations from %s. Exiting.",
            config_path,
        )
        sys.exit(1)
    except Exception:  # Catch any other unexpected errors from loader
        logger.exception(
            "An unexpected error occurred while loading server configurations from %s. Exiting.",
            config_path,
        )
        sys.exit(1)


def _configure_named_servers_from_cli(
    named_server_definitions: list[tuple[str, str]],
    base_env: dict[str, str],
    logger: logging.Logger,
) -> dict[str, StdioServerParameters]:
    """Configure named servers from CLI arguments."""
    named_stdio_params: dict[str, StdioServerParameters] = {}

    for name, command_string in named_server_definitions:
        try:
            command_parts = shlex.split(command_string)
            if not command_parts:  # Handle empty command_string
                logger.error("Empty COMMAND_STRING for named server '%s'. Skipping.", name)
                continue

            command = command_parts[0]
            command_args = command_parts[1:]
            # Named servers inherit base_env (which includes passed-through env)
            # and use the proxy's CWD.
            named_stdio_params[name] = StdioServerParameters(
                command=command,
                args=command_args,
                env=base_env.copy(),  # Each named server gets a copy of the base env
                cwd=None,  # Named servers run in the proxy's CWD
            )
            logger.info("Configured named server '%s': %s", name, command_string)
        except IndexError:  # Should be caught by the check for empty command_parts
            logger.exception(
                "Invalid COMMAND_STRING for named server '%s': '%s'. Must include a command.",
                name,
                command_string,
            )
            sys.exit(1)
        except Exception:
            logger.exception("Error parsing COMMAND_STRING for named server '%s'", name)
            sys.exit(1)

    return named_stdio_params


def _create_mcp_settings(
    args_parsed: argparse.Namespace,
    bridge_config: "BridgeConfiguration | None" = None,
) -> MCPServerSettings:
    """Create MCP server settings from parsed arguments and optional bridge config."""
    # Priority: CLI args > config file > defaults
    default_host = "127.0.0.1"
    default_port = 8080

    if bridge_config and bridge_config.bridge:
        # Use CLI args if provided, otherwise fall back to config file values
        host = args_parsed.host if args_parsed.host != default_host else bridge_config.bridge.host
        port = args_parsed.port if args_parsed.port != default_port else bridge_config.bridge.port
    else:
        # Fallback to CLI args or deprecated sse_* args
        host = args_parsed.host if args_parsed.host is not None else args_parsed.sse_host
        port = args_parsed.port if args_parsed.port is not None else args_parsed.sse_port

    return MCPServerSettings(
        bind_host=host,
        port=port,
        stateless=args_parsed.stateless,
        allow_origins=args_parsed.allow_origin if len(args_parsed.allow_origin) > 0 else None,
        log_level="DEBUG" if args_parsed.debug else "INFO",
    )


def main() -> None:
    """Start the client using asyncio."""
    parser = _setup_argument_parser()
    args_parsed = parser.parse_args()
    logger = _setup_logging(debug=args_parsed.debug)

    # Handle bridge mode first (takes precedence over all other options)
    # Check if config file exists (especially for default config.json)
    # Resolve the actual config path used (important for config reloading)
    config_path = args_parsed.bridge_config

    if not Path(config_path).exists():
        if config_path == "config.json":
            # Default config.json doesn't exist, provide helpful guidance
            logger.info("No config.json found in current directory.")
            logger.info("To get started with MCP Foxxy Bridge, you need a configuration file.")
            logger.info("You can:")
            logger.info("  1. Copy an example: cp docs/examples/basic-config.json config.json")
            logger.info("  2. Create a minimal config:")
            logger.info(
                '     echo \'{"servers": {"filesystem": {"command": "npx", '
                '"args": ["-y", "@modelcontextprotocol/server-filesystem", "./"]}}}\' '
                "> config.json",
            )
            logger.info(
                "  3. Use a different config: mcp-foxxy-bridge --bridge-config "
                "path/to/your/config.json",
            )
            logger.info("  4. See available examples in docs/examples/ directory")
            logger.info("")
            logger.info(
                "For more help, see: https://github.com/billyjbryant/mcp-foxxy-bridge/blob/main/docs/configuration.md",
            )
            sys.exit(1)
        else:
            # Custom config file doesn't exist
            logger.error("Bridge configuration file not found: %s", config_path)
            sys.exit(1)

    logger.info("Starting in bridge mode with config: %s", config_path)

    # Load bridge configuration
    bridge_base_env: dict[str, str] = {}
    if args_parsed.pass_environment:
        bridge_base_env.update(os.environ)

    try:
        bridge_config = load_bridge_config_from_file(config_path, bridge_base_env)
    except Exception:
        logger.exception("Failed to load bridge configuration")
        sys.exit(1)

    # Create MCP server settings and run the bridge server
    mcp_settings = _create_mcp_settings(args_parsed, bridge_config)
    try:
        asyncio.run(run_bridge_server(mcp_settings, bridge_config, config_path))
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down gracefully...")
    except Exception:
        logger.exception("Bridge server error")
        return


if __name__ == "__main__":
    main()
