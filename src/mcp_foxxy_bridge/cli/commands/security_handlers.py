#
# MCP Foxxy Bridge - Security Configuration Handlers
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
"""Security configuration management command handlers."""

import json
import logging
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console

from .config import _load_config_safe, _save_config


async def handle_security_show(
    args: Any,
    config_path: Path,
    config_dir: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Show bridge security configuration."""
    try:
        config = _load_config_safe(config_path, logger)
        bridge_config = config.get("bridge", {})
        security_config = bridge_config.get("security", {})

        if not security_config:
            console.print("[yellow]No security configuration found. Using defaults:[/yellow]")
            security_config = {"read_only_mode": True}

        if args.format == "json":
            console.print(json.dumps(security_config, indent=2))
        else:  # yaml
            yaml_str = yaml.dump(security_config, default_flow_style=False, sort_keys=False)  # type: ignore[no-untyped-call]
            console.print(yaml_str.rstrip())

    except Exception as e:
        console.print(f"[red]Error showing security configuration: {e}[/red]")
        logger.exception("Failed to show security configuration")


async def handle_security_set(
    args: Any,
    config_path: Path,
    config_dir: Path,
    console: Console,
    logger: logging.Logger,
) -> None:
    """Set bridge security configuration."""
    try:
        config = _load_config_safe(config_path, logger)

        # Ensure bridge configuration exists
        if "bridge" not in config:
            config["bridge"] = {}

        bridge_config = config["bridge"]

        # Ensure security configuration exists
        if "security" not in bridge_config:
            bridge_config["security"] = {}

        security_config = bridge_config["security"]

        # Set read-only mode if specified
        if args.read_only is not None:
            security_config["read_only_mode"] = args.read_only
            console.print(f"[green]✓[/green] Set read-only mode: {args.read_only}")

        # Set tool security configuration
        has_tool_security_updates = any(
            [args.allow_patterns, args.block_patterns, args.allow_tools, args.block_tools, args.classify_tools]
        )

        if has_tool_security_updates:
            if "tool_security" not in security_config:
                security_config["tool_security"] = {}

            tool_security = security_config["tool_security"]

            if args.allow_patterns:
                # Sanitize patterns
                sanitized_patterns = [str(p).strip() for p in args.allow_patterns if str(p).strip()]
                tool_security["allow_patterns"] = sanitized_patterns
                console.print(f"[green]✓[/green] Set allow patterns: {sanitized_patterns}")

            if args.block_patterns:
                sanitized_patterns = [str(p).strip() for p in args.block_patterns if str(p).strip()]
                tool_security["block_patterns"] = sanitized_patterns
                console.print(f"[green]✓[/green] Set block patterns: {sanitized_patterns}")

            if args.allow_tools:
                sanitized_tools = [str(t).strip() for t in args.allow_tools if str(t).strip()]
                tool_security["allow_tools"] = sanitized_tools
                console.print(f"[green]✓[/green] Set allow tools: {sanitized_tools}")

            if args.block_tools:
                sanitized_tools = [str(t).strip() for t in args.block_tools if str(t).strip()]
                tool_security["block_tools"] = sanitized_tools
                console.print(f"[green]✓[/green] Set block tools: {sanitized_tools}")

            if args.classify_tools:
                classification_overrides = {}
                for tool_name, tool_type in args.classify_tools:
                    clean_name = str(tool_name).strip()
                    clean_type = str(tool_type).strip().lower()
                    if clean_name and clean_type in ["read", "write", "unknown"]:
                        classification_overrides[clean_name] = clean_type

                if classification_overrides:
                    tool_security["classification_overrides"] = classification_overrides
                    console.print(f"[green]✓[/green] Set tool classifications: {classification_overrides}")

        # Save configuration
        _save_config(config, config_path, console, logger)

        console.print("[green]✓[/green] Bridge security configuration updated successfully")
        logger.info("Updated bridge security configuration")

    except Exception as e:
        console.print(f"[red]Error setting security configuration: {e}[/red]")
        logger.exception("Failed to set security configuration")
