#
# MCP Foxxy Bridge - Tool Classification for Security
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
"""Tool classification for automatic read/write detection."""

import re
from enum import Enum
from typing import ClassVar


class ToolType(Enum):
    """Classification of tool operations."""

    READ = "read"
    WRITE = "write"
    UNKNOWN = "unknown"


class ToolClassifier:
    """Classifies tools as read or write operations based on name patterns."""

    # Patterns for read operations
    READ_PATTERNS: ClassVar[list[str]] = [
        r"^read_.*",
        r"^get_.*",
        r"^list_.*",
        r"^show_.*",
        r"^view_.*",
        r"^fetch_.*",
        r"^query_.*",
        r"^search_.*",
        r"^find_.*",
        r"^check_.*",
        r"^verify_.*",
        r"^validate_.*",
        r"^test_.*",
        r"^status_.*",
        r"^info_.*",
        r"^describe_.*",
        r"^export_.*",
        r"^download_.*",
        r"^backup_.*",
        r".*_info$",
        r".*_status$",
        r".*_details$",
        r".*_summary$",
    ]

    # Patterns for write operations
    WRITE_PATTERNS: ClassVar[list[str]] = [
        r"^write_.*",
        r"^create_.*",
        r"^add_.*",
        r"^insert_.*",
        r"^update_.*",
        r"^modify_.*",
        r"^edit_.*",
        r"^change_.*",
        r"^set_.*",
        r"^put_.*",
        r"^post_.*",
        r"^patch_.*",
        r"^delete_.*",
        r"^remove_.*",
        r"^drop_.*",
        r"^destroy_.*",
        r"^clear_.*",
        r"^reset_.*",
        r"^move_.*",
        r"^copy_.*",
        r"^rename_.*",
        r"^execute_.*",
        r"^run_.*",
        r"^start_.*",
        r"^stop_.*",
        r"^restart_.*",
        r"^kill_.*",
        r"^terminate_.*",
        r"^upload_.*",
        r"^deploy_.*",
        r"^install_.*",
        r"^uninstall_.*",
        r"^configure_.*",
        r"^setup_.*",
        r"^initialize_.*",
        r"^commit_.*",
        r"^push_.*",
        r"^publish_.*",
        r"^send_.*",
        r"^submit_.*",
        r"^apply_.*",
        r"^restore_.*",
        r"^recover_.*",
        r".*_force_.*",
        r".*_unsafe_.*",
    ]

    def __init__(self, classification_overrides: dict[str, str] | None = None) -> None:
        """Initialize classifier with optional overrides.

        Args:
            classification_overrides: Manual tool classification overrides
        """
        self.classification_overrides = classification_overrides or {}
        self._read_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in self.READ_PATTERNS]
        self._write_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in self.WRITE_PATTERNS]

    def classify_tool(self, tool_name: str) -> ToolType:
        """Classify a tool as read, write, or unknown.

        Args:
            tool_name: Name of the tool to classify

        Returns:
            ToolType classification
        """
        # Check for manual overrides first
        if tool_name in self.classification_overrides:
            override_value = self.classification_overrides[tool_name].lower()
            if override_value == "read":
                return ToolType.READ
            if override_value == "write":
                return ToolType.WRITE
            if override_value == "unknown":
                return ToolType.UNKNOWN

        # Check write patterns first (more restrictive)
        for pattern in self._write_patterns:
            if pattern.match(tool_name):
                return ToolType.WRITE

        # Check read patterns
        for pattern in self._read_patterns:
            if pattern.match(tool_name):
                return ToolType.READ

        # Default to unknown if no patterns match
        return ToolType.UNKNOWN

    def is_read_only_tool(self, tool_name: str) -> bool:
        """Check if a tool is classified as read-only.

        Args:
            tool_name: Name of the tool to check

        Returns:
            True if tool is read-only, False otherwise
        """
        return self.classify_tool(tool_name) == ToolType.READ

    def is_write_tool(self, tool_name: str) -> bool:
        """Check if a tool is classified as a write operation.

        Args:
            tool_name: Name of the tool to check

        Returns:
            True if tool performs write operations, False otherwise
        """
        return self.classify_tool(tool_name) == ToolType.WRITE

    def add_classification_override(self, tool_name: str, tool_type: ToolType) -> None:
        """Add a manual classification override for a specific tool.

        Args:
            tool_name: Name of the tool
            tool_type: Classification to override with
        """
        self.classification_overrides[tool_name] = tool_type.value

    def get_classification_stats(self, tool_names: list[str]) -> dict[str, int]:
        """Get classification statistics for a list of tools.

        Args:
            tool_names: List of tool names to analyze

        Returns:
            Dictionary with counts for each classification type
        """
        stats = {"read": 0, "write": 0, "unknown": 0}

        for tool_name in tool_names:
            classification = self.classify_tool(tool_name)
            stats[classification.value] += 1

        return stats
