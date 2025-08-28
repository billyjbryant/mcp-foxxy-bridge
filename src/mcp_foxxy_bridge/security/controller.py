#
# MCP Foxxy Bridge - Access Control System
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
"""Central access control system for MCP tools and resources."""

import re
from typing import Any

from mcp_foxxy_bridge.utils.logging import get_logger

from .config import BridgeSecurityConfig, ServerSecurityConfig
from .policy import SecurityPolicy

logger = get_logger(__name__, facility="SECURITY")

# Security constants
MAX_INPUT_LENGTH = 255  # Maximum allowed input string length


class AccessController:
    """Central access control system for managing tool and resource access."""

    def __init__(self, bridge_config: BridgeSecurityConfig) -> None:
        """Initialize access controller with bridge security configuration.

        Args:
            bridge_config: Global bridge security configuration
        """
        self.bridge_config = bridge_config
        self._server_policies: dict[str, SecurityPolicy] = {}
        self._sanitize_bridge_config()

    def _sanitize_input(self, value: str) -> str:
        """Sanitize user input to prevent injection attacks.

        Args:
            value: User input value to sanitize

        Returns:
            Sanitized input value
        """
        if not isinstance(value, str):
            return str(value)  # type: ignore[unreachable]

        # Remove dangerous characters and control sequences - be restrictive for security
        # Allow alphanumeric, hyphens, underscores, dots, forward/back slashes for tool/server names
        sanitized = re.sub(r"[^\w\-_./\\]", "", value)

        # Limit length to prevent DoS
        if len(sanitized) > MAX_INPUT_LENGTH:
            logger.warning(f"Pattern truncated from {len(sanitized)} to {MAX_INPUT_LENGTH} characters")
            sanitized = sanitized[:MAX_INPUT_LENGTH]

        return sanitized

    def _sanitize_pattern_list(self, patterns: list[str]) -> list[str]:
        """Sanitize a list of patterns.

        Args:
            patterns: List of patterns to sanitize

        Returns:
            List of sanitized patterns
        """
        if not patterns:
            return []

        sanitized_patterns = []
        for pattern in patterns[:50]:  # Limit to 50 patterns to prevent DoS
            if isinstance(pattern, str) and pattern.strip():
                sanitized = self._sanitize_input(pattern.strip())
                if sanitized:  # Only add non-empty patterns
                    sanitized_patterns.append(sanitized)

        if len(patterns) > 50:
            logger.warning(f"Pattern list truncated from {len(patterns)} to 50 entries")

        return sanitized_patterns

    def _sanitize_bridge_config(self) -> None:
        """Sanitize bridge configuration patterns."""
        if self.bridge_config.tools:
            tool_security = self.bridge_config.tools

            # Sanitize patterns
            tool_security.allow_patterns = self._sanitize_pattern_list(tool_security.allow_patterns)
            tool_security.block_patterns = self._sanitize_pattern_list(tool_security.block_patterns)
            tool_security.allow_tools = self._sanitize_pattern_list(tool_security.allow_tools)
            tool_security.block_tools = self._sanitize_pattern_list(tool_security.block_tools)

            # Sanitize classification overrides
            sanitized_overrides = {}
            for tool_name, classification in tool_security.classification_overrides.items():
                if isinstance(tool_name, str) and isinstance(classification, str):
                    clean_tool = self._sanitize_input(tool_name)
                    clean_classification = classification.lower().strip()
                    if clean_tool and clean_classification in ["read", "write", "unknown"]:
                        sanitized_overrides[clean_tool] = clean_classification

            tool_security.classification_overrides = sanitized_overrides

    def register_server(self, server_name: str, server_config: ServerSecurityConfig | None = None) -> None:
        """Register a server with its security configuration.

        Args:
            server_name: Name of the server to register
            server_config: Optional server-specific security configuration
        """
        # Sanitize server name
        clean_server_name = self._sanitize_input(server_name)
        if not clean_server_name:
            logger.warning(f"Invalid server name: {server_name}")
            return

        # Sanitize server configuration if provided
        if server_config:
            self._sanitize_server_config(server_config)

        # Create security policy for this server
        policy = SecurityPolicy(self.bridge_config, server_config)
        self._server_policies[clean_server_name] = policy

        logger.info(f"Registered security policy for server: {clean_server_name}")
        logger.debug(f"Policy summary: {policy.get_effective_config_summary()}")

    def _sanitize_server_config(self, server_config: ServerSecurityConfig) -> None:
        """Sanitize server-specific security configuration.

        Args:
            server_config: Server configuration to sanitize
        """
        if server_config.tools:
            tool_security = server_config.tools

            # Sanitize patterns
            tool_security.allow_patterns = self._sanitize_pattern_list(tool_security.allow_patterns)
            tool_security.block_patterns = self._sanitize_pattern_list(tool_security.block_patterns)
            tool_security.allow_tools = self._sanitize_pattern_list(tool_security.allow_tools)
            tool_security.block_tools = self._sanitize_pattern_list(tool_security.block_tools)

            # Sanitize classification overrides
            sanitized_overrides = {}
            for tool_name, classification in tool_security.classification_overrides.items():
                if isinstance(tool_name, str) and isinstance(classification, str):
                    clean_tool = self._sanitize_input(tool_name)
                    clean_classification = classification.lower().strip()
                    if clean_tool and clean_classification in ["read", "write", "unknown"]:
                        sanitized_overrides[clean_tool] = clean_classification

            tool_security.classification_overrides = sanitized_overrides

    def is_tool_allowed(self, server_name: str, tool_name: str) -> bool:
        """Check if a tool is allowed to be executed on a specific server.

        Args:
            server_name: Name of the server
            tool_name: Name of the tool to check

        Returns:
            True if tool is allowed, False if blocked
        """
        # Sanitize inputs
        clean_server_name = self._sanitize_input(server_name)
        clean_tool_name = self._sanitize_input(tool_name)

        if not clean_server_name or not clean_tool_name:
            logger.warning(f"Invalid input - server: {server_name}, tool: {tool_name}")
            return False

        # Get policy for server (fallback to bridge-only policy)
        policy = self._server_policies.get(clean_server_name)
        if not policy:
            logger.warning(f"No policy found for server: {clean_server_name}, using bridge policy")
            policy = SecurityPolicy(self.bridge_config)

        # Check if tool is allowed
        allowed = policy.is_tool_allowed(clean_tool_name)

        if not allowed:
            reason = policy.get_block_reason(clean_tool_name)
            logger.info(f"Tool '{clean_tool_name}' blocked on server '{clean_server_name}': {reason}")

        return allowed

    def get_block_reason(self, server_name: str, tool_name: str) -> str | None:
        """Get the reason why a tool is blocked.

        Args:
            server_name: Name of the server
            tool_name: Name of the tool to check

        Returns:
            Human-readable reason for blocking, or None if tool is allowed
        """
        # Sanitize inputs
        clean_server_name = self._sanitize_input(server_name)
        clean_tool_name = self._sanitize_input(tool_name)

        if not clean_server_name or not clean_tool_name:
            return "Invalid server or tool name"

        # Get policy for server
        policy = self._server_policies.get(clean_server_name)
        if not policy:
            policy = SecurityPolicy(self.bridge_config)

        return policy.get_block_reason(clean_tool_name)

    def get_server_policy_summary(self, server_name: str) -> dict[str, Any] | None:
        """Get a summary of the security policy for a specific server.

        Args:
            server_name: Name of the server

        Returns:
            Dictionary with policy summary, or None if server not found
        """
        clean_server_name = self._sanitize_input(server_name)
        policy = self._server_policies.get(clean_server_name)
        return policy.get_effective_config_summary() if policy else None

    def list_registered_servers(self) -> list[str]:
        """Get list of registered server names.

        Returns:
            List of registered server names
        """
        return list(self._server_policies.keys())

    def audit_tool_access(self, tools_by_server: dict[str, list[str]]) -> dict[str, dict[str, str]]:
        """Audit tool access permissions across all servers.

        Args:
            tools_by_server: Dictionary mapping server names to tool lists

        Returns:
            Dictionary with access audit results
        """
        audit_results = {}

        for server_name, tools in tools_by_server.items():
            clean_server_name = self._sanitize_input(server_name)
            server_results = {}

            for tool_name in tools:
                clean_tool_name = self._sanitize_input(tool_name)
                if self.is_tool_allowed(clean_server_name, clean_tool_name):
                    server_results[clean_tool_name] = "allowed"
                else:
                    reason = self.get_block_reason(clean_server_name, clean_tool_name)
                    server_results[clean_tool_name] = f"blocked: {reason}"

            audit_results[clean_server_name] = server_results

        return audit_results
