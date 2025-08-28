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

"""Tests for facility-aware logging functionality."""

import logging
from unittest.mock import MagicMock, patch

from mcp_foxxy_bridge.utils.logging import MCPRichHandler, get_logger


class TestFacilityAwareLogging:
    """Test cases for facility-aware logging system."""

    def teardown_method(self) -> None:
        """Clean up logging configuration after each test."""
        # Reset any loggers we created
        for logger_name in [
            "test.facility",
            "test.oauth",
            "test.bridge",
            "test.server",
            "test.client",
            "test.config",
            "test.security",
            "test.utils",
        ]:
            logger = logging.getLogger(logger_name)
            if hasattr(logger, "_facility"):
                delattr(logger, "_facility")

    def test_get_logger_without_facility(self) -> None:
        """Test get_logger function without facility parameter."""
        logger = get_logger("test.facility")

        assert isinstance(logger, logging.Logger)
        assert logger.name == "test.facility"
        assert hasattr(logger, "success")  # Should have success method
        assert not hasattr(logger, "_facility")  # No facility set

    def test_get_logger_with_facility(self) -> None:
        """Test get_logger function with facility parameter."""
        logger = get_logger("test.facility", facility="OAUTH")

        assert isinstance(logger, logging.Logger)
        assert logger.name == "test.facility"
        assert hasattr(logger, "success")  # Should have success method
        assert hasattr(logger, "_facility")  # Facility should be set
        assert logger._facility == "OAUTH"  # type: ignore[attr-defined]

    def test_get_logger_facility_none(self) -> None:
        """Test get_logger function with explicit None facility."""
        logger = get_logger("test.facility", facility=None)

        assert isinstance(logger, logging.Logger)
        assert logger.name == "test.facility"
        assert hasattr(logger, "success")  # Should have success method
        assert not hasattr(logger, "_facility")  # No facility set

    def test_get_logger_same_instance_different_facility(self) -> None:
        """Test that get_logger returns the same instance but updates facility."""
        # First call with OAUTH facility
        logger1 = get_logger("test.facility", facility="OAUTH")
        assert logger1._facility == "OAUTH"  # type: ignore[attr-defined]

        # Second call with BRIDGE facility - should update the facility
        logger2 = get_logger("test.facility", facility="BRIDGE")

        # Should be the same logger instance
        assert logger1 is logger2
        # But facility should be updated
        assert logger2._facility == "BRIDGE"  # type: ignore[attr-defined]

    def test_facility_colors_defined(self) -> None:
        """Test that all facility colors are properly defined in MCPRichHandler."""
        handler = MCPRichHandler()

        # Create a mock record with facility
        record = logging.LogRecord(
            name="test.facility",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        # Test each facility color
        facilities = {
            "OAUTH": "bold orange3",
            "BRIDGE": "bold blue",
            "SERVER": "bold magenta",
            "CLIENT": "bold cyan",
            "CONFIG": "bold green",
            "SECURITY": "bold red",
            "UTILS": "bold white",
        }

        for facility, expected_color in facilities.items():
            # Mock logger with facility
            with patch("logging.getLogger") as mock_get_logger:
                mock_logger = MagicMock()
                mock_logger._facility = facility
                mock_get_logger.return_value = mock_logger

                message_text = handler.render_message(record, "Test message")

                # Should contain facility markup
                assert f"[{expected_color}]" in message_text.markup
                assert f"[{facility}]" in message_text.markup

    def test_facility_message_rendering(self) -> None:
        """Test message rendering with facility information."""
        handler = MCPRichHandler()

        record = logging.LogRecord(
            name="test.facility",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        # Mock logger with OAUTH facility
        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_logger._facility = "OAUTH"
            mock_get_logger.return_value = mock_logger

            message_text = handler.render_message(record, "Test message")

            # Should contain facility prefix and color
            assert "[bold orange3]" in message_text.markup
            assert "[OAUTH]" in message_text.markup
            assert "Test message" in message_text.plain

    def test_facility_fallback_color(self) -> None:
        """Test facility rendering with unknown facility falls back to default color."""
        handler = MCPRichHandler()

        record = logging.LogRecord(
            name="test.facility",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        # Mock logger with unknown facility
        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_logger._facility = "UNKNOWN_FACILITY"
            mock_get_logger.return_value = mock_logger

            message_text = handler.render_message(record, "Test message")

            # Should use default white color for unknown facility
            assert "[bold white]" in message_text.markup
            assert "[UNKNOWN_FACILITY]" in message_text.markup

    def test_facility_vs_server_name_precedence(self) -> None:
        """Test that facility takes precedence over server name highlighting."""
        handler = MCPRichHandler()

        # Create record that would normally trigger server name highlighting
        record = logging.LogRecord(
            name="mcp.server.filesystem",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        # Mock logger with facility - facility should take precedence
        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_logger._facility = "SERVER"
            mock_get_logger.return_value = mock_logger

            message_text = handler.render_message(record, "Test message")

            # Should use facility color (magenta), not server color (green)
            assert "[bold magenta]" in message_text.markup
            assert "[SERVER]" in message_text.markup
            # Should NOT contain server name highlighting
            assert "[filesystem]" not in message_text.markup

    def test_no_facility_falls_back_to_server_highlighting(self) -> None:
        """Test that without facility, server name highlighting still works."""
        handler = MCPRichHandler()

        record = logging.LogRecord(
            name="mcp.server.filesystem",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        # Create a real logger without facility (don't mock getLogger)
        # This will test the actual fallback logic
        message_text = handler.render_message(record, "Test message")

        # Should use server name highlighting
        assert "[bold green]" in message_text.markup  # INFO level server color
        assert "[filesystem]" in message_text.markup

    def test_facility_logger_success_method(self) -> None:
        """Test that facility-aware loggers still have success method."""
        logger = get_logger("test.facility", facility="CONFIG")

        # Should have success method
        assert hasattr(logger, "success")
        assert callable(logger.success)

        # Test that we can call it without error
        with patch.object(logger, "log") as mock_log:
            logger.success("Test success message")

            # Should call log with SUCCESS_LEVEL (25)
            mock_log.assert_called_once()
            args = mock_log.call_args[0]
            assert args[0] == 25  # SUCCESS_LEVEL
            assert args[1] == "Test success message"

    def test_all_facilities_render_correctly(self) -> None:
        """Test that all defined facilities render with correct colors."""
        handler = MCPRichHandler()

        facilities_and_colors = {
            "OAUTH": "bold orange3",
            "BRIDGE": "bold blue",
            "SERVER": "bold magenta",
            "CLIENT": "bold cyan",
            "CONFIG": "bold green",
            "SECURITY": "bold red",
            "UTILS": "bold white",
        }

        for facility, expected_color in facilities_and_colors.items():
            get_logger(f"test.{facility.lower()}", facility=facility)

            record = logging.LogRecord(
                name=f"test.{facility.lower()}",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg=f"Message from {facility}",
                args=(),
                exc_info=None,
            )

            message_text = handler.render_message(record, f"Message from {facility}")

            # Check that it contains the correct facility and color
            assert f"[{expected_color}]" in message_text.markup
            assert f"[{facility}]" in message_text.markup
            assert f"Message from {facility}" in message_text.plain

    def test_facility_with_no_record_name(self) -> None:
        """Test facility rendering when record has no name."""
        handler = MCPRichHandler()

        record = logging.LogRecord(
            name="",  # Empty name
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        message_text = handler.render_message(record, "Test message")

        # Should handle empty name gracefully
        assert message_text.plain == "Test message"

    def test_facility_message_with_existing_emoji(self) -> None:
        """Test that facility messages work with existing emojis."""
        handler = MCPRichHandler()

        record = logging.LogRecord(
            name="test.facility",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Error message",
            args=(),
            exc_info=None,
        )

        # Mock logger with facility
        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_logger._facility = "SECURITY"
            mock_get_logger.return_value = mock_logger

            # Message already has emoji - should not add another
            message_text = handler.render_message(record, "❌ Error message")

            # Should contain facility but not duplicate emoji
            assert "[bold red]" in message_text.markup
            assert "[SECURITY]" in message_text.markup
            assert "❌ Error message" in message_text.plain
