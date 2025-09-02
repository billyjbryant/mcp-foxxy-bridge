#
# MCP Foxxy Bridge - Security Configuration Models
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
"""Security configuration models for tool access control."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolSecurityConfig:
    """Configuration for tool security and access control."""

    # Allow/block patterns (glob/regex patterns)
    allow_patterns: list[str] = field(default_factory=list)
    block_patterns: list[str] = field(default_factory=list)

    # Allow/block specific tool names
    allow_tools: list[str] = field(default_factory=list)
    block_tools: list[str] = field(default_factory=list)

    # Manual tool classification overrides
    classification_overrides: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolSecurityConfig":
        """Create from dictionary configuration."""
        return cls(
            allow_patterns=data.get("allow_patterns", []),
            block_patterns=data.get("block_patterns", []),
            allow_tools=data.get("allow_tools", []),
            block_tools=data.get("block_tools", []),
            classification_overrides=data.get("classification_overrides", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "allow_patterns": self.allow_patterns,
            "block_patterns": self.block_patterns,
            "allow_tools": self.allow_tools,
            "block_tools": self.block_tools,
            "classification_overrides": self.classification_overrides,
        }

    def is_empty(self) -> bool:
        """Check if this config has any security rules defined."""
        return (
            not self.allow_patterns
            and not self.block_patterns
            and not self.allow_tools
            and not self.block_tools
            and not self.classification_overrides
        )


@dataclass
class ServerSecurityConfig:
    """Security configuration for an individual MCP server."""

    # Read-only mode for this server
    read_only_mode: bool | None = None  # None means inherit from bridge

    # Tool security configuration
    tools: ToolSecurityConfig | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ServerSecurityConfig":
        """Create from dictionary configuration."""
        tool_data = data.get("tools") or data.get("tool") or data.get("tool_security")  # Support all variants
        return cls(
            read_only_mode=data.get("read_only_mode"),
            tools=ToolSecurityConfig.from_dict(tool_data) if tool_data else None,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result: dict[str, Any] = {}
        if self.read_only_mode is not None:
            result["read_only_mode"] = self.read_only_mode
        if self.tools is not None:
            result["tools"] = self.tools.to_dict()
        return result


@dataclass
class BridgeSecurityConfig:
    """Global security configuration for the bridge."""

    # Global read-only mode (default: True for security)
    read_only_mode: bool = True

    # Global tool security configuration
    tools: ToolSecurityConfig | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BridgeSecurityConfig":
        """Create from dictionary configuration."""
        tool_data = data.get("tools") or data.get("tool") or data.get("tool_security")  # Support all variants
        return cls(
            read_only_mode=data.get("read_only_mode", True),  # Secure by default
            tools=ToolSecurityConfig.from_dict(tool_data) if tool_data else None,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result: dict[str, Any] = {"read_only_mode": self.read_only_mode}
        if self.tools is not None:
            result["tools"] = self.tools.to_dict()
        return result
