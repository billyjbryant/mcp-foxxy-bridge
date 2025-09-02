#
# MCP Foxxy Bridge - Pattern Matching for Security Rules
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
"""Pattern matching for allow/block list processing."""

import fnmatch
import re
from re import Pattern


class PatternMatcher:
    """Handles pattern matching for security rules using glob and regex patterns."""

    def __init__(self, patterns: list[str]) -> None:
        """Initialize pattern matcher with a list of patterns.

        Args:
            patterns: List of glob or regex patterns to match against
        """
        self.patterns = patterns
        self._compiled_patterns: list[Pattern[str]] = []
        self._glob_patterns: list[str] = []

        # Separate regex patterns (starting with ^, containing regex metacharacters)
        # from glob patterns (simple wildcards)
        for pattern in patterns:
            if self._is_regex_pattern(pattern):
                try:
                    self._compiled_patterns.append(re.compile(pattern, re.IGNORECASE))
                except re.error:
                    # If regex compilation fails, treat as glob pattern
                    self._glob_patterns.append(pattern)
            else:
                self._glob_patterns.append(pattern)

    def _is_regex_pattern(self, pattern: str) -> bool:
        """Determine if a pattern is regex or glob.

        Args:
            pattern: Pattern string to analyze

        Returns:
            True if pattern appears to be regex, False if glob
        """
        # Check for common regex indicators
        regex_indicators = [
            pattern.startswith("^"),
            pattern.endswith("$"),
            "(" in pattern and ")" in pattern,
            "[" in pattern and "]" in pattern,
            "+" in pattern,
            "{" in pattern and "}" in pattern,
            "\\d" in pattern,
            "\\w" in pattern,
            "\\s" in pattern,
            pattern == ".*" or (pattern.startswith(".*") and len(pattern) > 2),
        ]

        return any(regex_indicators)

    def matches(self, text: str) -> bool:
        """Check if text matches any of the patterns.

        Args:
            text: Text to match against patterns

        Returns:
            True if text matches any pattern, False otherwise
        """
        # Check glob patterns
        for pattern in self._glob_patterns:
            if fnmatch.fnmatch(text.lower(), pattern.lower()):
                return True

        # Check regex patterns
        return any(compiled_pattern.match(text) for compiled_pattern in self._compiled_patterns)

    def get_matching_patterns(self, text: str) -> list[str]:
        """Get all patterns that match the given text.

        Args:
            text: Text to match against patterns

        Returns:
            List of patterns that match the text
        """
        # Check glob patterns
        matching_patterns = [
            pattern for pattern in self._glob_patterns if fnmatch.fnmatch(text.lower(), pattern.lower())
        ]

        # Check regex patterns
        for _i, compiled_pattern in enumerate(self._compiled_patterns):
            if compiled_pattern.match(text):
                # Find the original pattern string
                for pattern in self.patterns:
                    if self._is_regex_pattern(pattern):
                        try:
                            if re.compile(pattern, re.IGNORECASE) == compiled_pattern:
                                matching_patterns.append(pattern)
                                break
                        except re.error:
                            continue

        return matching_patterns

    def is_empty(self) -> bool:
        """Check if this matcher has any patterns.

        Returns:
            True if no patterns are configured, False otherwise
        """
        return len(self.patterns) == 0

    @classmethod
    def create_allow_matcher(cls, allow_patterns: list[str], allow_tools: list[str]) -> "PatternMatcher":
        """Create a matcher for allow rules.

        Args:
            allow_patterns: List of allow patterns (glob/regex)
            allow_tools: List of specific tool names to allow

        Returns:
            PatternMatcher configured for allow rules
        """
        # Convert specific tool names to exact match patterns
        exact_patterns = [f"^{re.escape(tool)}$" for tool in allow_tools]
        all_patterns = allow_patterns + exact_patterns
        return cls(all_patterns)

    @classmethod
    def create_block_matcher(cls, block_patterns: list[str], block_tools: list[str]) -> "PatternMatcher":
        """Create a matcher for block rules.

        Args:
            block_patterns: List of block patterns (glob/regex)
            block_tools: List of specific tool names to block

        Returns:
            PatternMatcher configured for block rules
        """
        # Convert specific tool names to exact match patterns
        exact_patterns = [f"^{re.escape(tool)}$" for tool in block_tools]
        all_patterns = block_patterns + exact_patterns
        return cls(all_patterns)
