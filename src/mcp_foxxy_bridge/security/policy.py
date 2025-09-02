#
# MCP Foxxy Bridge - Security Policy Resolution
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
"""Security policy resolution with hierarchical configuration support."""

from typing import Any

from .classifier import ToolClassifier, ToolType
from .config import BridgeSecurityConfig, ServerSecurityConfig, ToolSecurityConfig
from .patterns import PatternMatcher


class SecurityPolicy:
    """Resolves security policies by combining bridge and server-specific configurations."""

    def __init__(
        self,
        bridge_config: BridgeSecurityConfig,
        server_config: ServerSecurityConfig | None = None,
    ) -> None:
        """Initialize security policy resolver.

        Args:
            bridge_config: Global bridge security configuration
            server_config: Optional server-specific security configuration
        """
        self.bridge_config = bridge_config
        self.server_config = server_config

        # Resolve the effective read-only mode
        self._read_only_mode = self._resolve_read_only_mode()

        # Resolve the effective tool security configuration
        self._effective_tool_config = self._resolve_tool_security_config()

        # Create tool classifier with merged overrides
        classification_overrides = {}
        if bridge_config and bridge_config.tools:
            classification_overrides.update(bridge_config.tools.classification_overrides)
        if server_config and server_config.tools:
            classification_overrides.update(server_config.tools.classification_overrides)

        self._tool_classifier = ToolClassifier(classification_overrides)

        # Create pattern matchers
        self._allow_matcher: PatternMatcher | None = None
        self._block_matcher: PatternMatcher | None = None
        if self._effective_tool_config:
            self._allow_matcher = PatternMatcher.create_allow_matcher(
                self._effective_tool_config.allow_patterns,
                self._effective_tool_config.allow_tools,
            )
            self._block_matcher = PatternMatcher.create_block_matcher(
                self._effective_tool_config.block_patterns,
                self._effective_tool_config.block_tools,
            )

    def _resolve_read_only_mode(self) -> bool:
        """Resolve the effective read-only mode.

        Returns:
            True if read-only mode should be enforced, False otherwise
        """
        # Server-specific setting overrides bridge setting when more specific
        if self.server_config and self.server_config.read_only_mode is not None:
            return self.server_config.read_only_mode

        # Fall back to bridge setting (defaults to True for security)
        if self.bridge_config:
            return self.bridge_config.read_only_mode

        # Default to True for security if no configuration is provided
        return True

    def _resolve_tool_security_config(self) -> ToolSecurityConfig | None:
        """Resolve the effective tool security configuration by merging bridge and server configs.

        Returns:
            Merged tool security configuration
        """
        bridge_tool_config = self.bridge_config.tools if self.bridge_config else None
        server_tool_config = self.server_config.tools if self.server_config else None

        # If neither has tool security config, return None
        if not bridge_tool_config and not server_tool_config:
            return None

        # If only one has config, return that one
        if not bridge_tool_config:
            return server_tool_config
        if not server_tool_config:
            return bridge_tool_config

        # Merge both configurations (server takes precedence over bridge)
        return ToolSecurityConfig(
            allow_patterns=bridge_tool_config.allow_patterns + server_tool_config.allow_patterns,
            block_patterns=bridge_tool_config.block_patterns + server_tool_config.block_patterns,
            allow_tools=bridge_tool_config.allow_tools + server_tool_config.allow_tools,
            block_tools=bridge_tool_config.block_tools + server_tool_config.block_tools,
            classification_overrides={
                **bridge_tool_config.classification_overrides,
                **server_tool_config.classification_overrides,  # Server overrides bridge
            },
        )

    def is_tool_allowed(self, tool_name: str) -> bool:
        """Check if a tool is allowed to be executed.

        Args:
            tool_name: Name of the tool to check

        Returns:
            True if tool is allowed, False if blocked
        """
        # Check explicit block rules first (highest priority)
        if self._block_matcher and self._block_matcher.matches(tool_name):
            return False

        # If allow rules are configured, tool must match to be allowed
        if self._allow_matcher and not self._allow_matcher.is_empty():
            if not self._allow_matcher.matches(tool_name):
                return False

        # Check read-only mode restrictions
        if self._read_only_mode:
            tool_type = self._tool_classifier.classify_tool(tool_name)
            if tool_type == ToolType.WRITE:
                return False
            # Unknown tools are blocked in read-only mode for safety
            if tool_type == ToolType.UNKNOWN:
                return False

        # Tool is allowed if it passes all checks
        return True

    def get_block_reason(self, tool_name: str) -> str | None:
        """Get the reason why a tool is blocked.

        Args:
            tool_name: Name of the tool to check

        Returns:
            Human-readable reason for blocking, or None if tool is allowed
        """
        if not self.is_tool_allowed(tool_name):
            # Check explicit block rules
            if self._block_matcher and self._block_matcher.matches(tool_name):
                matching_patterns = self._block_matcher.get_matching_patterns(tool_name)
                return f"Tool blocked by patterns: {', '.join(matching_patterns)}"

            # Check allow list restrictions
            if self._allow_matcher and not self._allow_matcher.is_empty():
                if not self._allow_matcher.matches(tool_name):
                    return "Tool not in allow list"

            # Check read-only mode restrictions
            if self._read_only_mode:
                tool_type = self._tool_classifier.classify_tool(tool_name)
                if tool_type == ToolType.WRITE:
                    return "Write operations blocked in read-only mode"
                if tool_type == ToolType.UNKNOWN:
                    return "Unknown tool type blocked in read-only mode"

        return None

    def classify_tool(self, tool_name: str) -> ToolType:
        """Classify a tool using the configured classifier.

        Args:
            tool_name: Name of the tool to classify

        Returns:
            Tool classification
        """
        return self._tool_classifier.classify_tool(tool_name)

    def is_read_only_mode(self) -> bool:
        """Check if read-only mode is enabled.

        Returns:
            True if read-only mode is active, False otherwise
        """
        return self._read_only_mode

    def get_effective_config_summary(self) -> dict[str, Any]:
        """Get a summary of the effective security configuration.

        Returns:
            Dictionary with configuration summary
        """
        summary = {
            "read_only_mode": self._read_only_mode,
            "has_allow_rules": self._allow_matcher is not None and not self._allow_matcher.is_empty(),
            "has_block_rules": self._block_matcher is not None and not self._block_matcher.is_empty(),
            "classification_overrides_count": len(self._tool_classifier.classification_overrides),
        }

        if self._effective_tool_config:
            summary.update(
                {
                    "allow_patterns_count": len(self._effective_tool_config.allow_patterns),
                    "block_patterns_count": len(self._effective_tool_config.block_patterns),
                    "allow_tools_count": len(self._effective_tool_config.allow_tools),
                    "block_tools_count": len(self._effective_tool_config.block_tools),
                }
            )

        return summary
