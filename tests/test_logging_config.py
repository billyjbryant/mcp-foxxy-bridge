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

"""Tests for the enhanced logging configuration module."""

import logging
from io import StringIO
from unittest.mock import MagicMock, patch

from rich.console import Console

from mcp_foxxy_bridge.utils.logging import (
    MCPRichHandler,
    get_logger,
    setup_logging,
)

# Constants for console width testing
DEFAULT_CONSOLE_WIDTH = 120
CUSTOM_CONSOLE_WIDTH = 80


class TestMCPRichHandler:
    """Test cases for MCPRichHandler class."""

    def test_init_default_settings(self) -> None:
        """Test MCPRichHandler initialization with default settings."""
        handler = MCPRichHandler()

        assert handler.console is not None
        assert isinstance(handler.console, Console)
        assert handler.console.stderr  # Should use stderr
        assert handler.console._force_terminal
        assert handler.console.options.max_width == DEFAULT_CONSOLE_WIDTH

    def test_init_custom_console(self) -> None:
        """Test MCPRichHandler initialization with custom console."""
        custom_console = Console(width=CUSTOM_CONSOLE_WIDTH)
        handler = MCPRichHandler(console=custom_console)

        assert handler.console is custom_console
        assert handler.console.options.max_width == CUSTOM_CONSOLE_WIDTH

    def test_init_custom_options(self) -> None:
        """Test MCPRichHandler initialization with custom options."""
        handler = MCPRichHandler(
            show_time=False,
            show_level=False,
            show_path=True,
            rich_tracebacks=False,
            tracebacks_show_locals=True,
        )

        # Note: These settings are passed to parent RichHandler
        # We can't easily test them without complex introspection
        assert isinstance(handler.console, Console)

    def test_get_level_text(self) -> None:
        """Test custom level text formatting."""
        handler = MCPRichHandler()

        # Create a mock log record
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        level_text = handler.get_level_text(record)

        assert level_text.plain == " INFO  "  # Centered in 7 characters
        # Check that the style contains the logging level style
        assert len(level_text.spans) > 0
        assert level_text.spans[0].style == "logging.level.info"

    def test_render_message_basic(self) -> None:
        """Test basic message rendering."""
        handler = MCPRichHandler()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        message_text = handler.render_message(record, "Test message")

        assert message_text.plain == "Test message"

    def test_render_message_server_highlighting(self) -> None:
        """Test message rendering with server name highlighting."""
        handler = MCPRichHandler()

        # Create record that looks like it's from a server
        record = logging.LogRecord(
            name="mcp.server.filesystem.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Server message",
            args=(),
            exc_info=None,
        )

        message_text = handler.render_message(record, "Server message")

        # Should include server name highlighting
        assert "filesystem" in message_text.markup
        assert "[bold green]" in message_text.markup

    def test_render_message_non_server(self) -> None:
        """Test message rendering for non-server logs."""
        handler = MCPRichHandler()

        record = logging.LogRecord(
            name="mcp_foxxy_bridge.config_loader",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Config message",
            args=(),
            exc_info=None,
        )

        message_text = handler.render_message(record, "Config message")

        # Should not include server highlighting
        assert message_text.plain == "Config message"


class TestSetupRichLogging:
    """Test cases for setup_rich_logging function."""

    def teardown_method(self) -> None:
        """Clean up logging configuration after each test."""
        # Reset root logger
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        root_logger.setLevel(logging.WARNING)

        # Reset specific loggers
        for logger_name in ["uvicorn", "uvicorn.access", "uvicorn.error", "mcp", "mcp.server"]:
            logger = logging.getLogger(logger_name)
            logger.handlers.clear()
            logger.setLevel(logging.NOTSET)
            logger.propagate = True

    def test_setup_rich_logging_debug_mode(self) -> None:
        """Test setup_rich_logging in debug mode."""
        setup_logging(debug=True)

        # Check root logger configuration
        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG
        assert len(root_logger.handlers) == 2  # Console + file handler
        handler_types = [type(h).__name__ for h in root_logger.handlers]
        assert "MCPRichHandler" in handler_types
        assert "RotatingFileHandler" in handler_types

        # Check MCP handler level
        mcp_handler = next(h for h in root_logger.handlers if isinstance(h, MCPRichHandler))
        handler = mcp_handler
        assert handler.level == logging.DEBUG

    def test_setup_rich_logging_normal_mode(self) -> None:
        """Test setup_rich_logging in normal mode."""
        setup_logging(debug=False)

        # Check root logger configuration
        root_logger = logging.getLogger()
        assert root_logger.level == logging.INFO
        assert len(root_logger.handlers) == 2  # Console + file handler
        handler_types = [type(h).__name__ for h in root_logger.handlers]
        assert "MCPRichHandler" in handler_types
        assert "RotatingFileHandler" in handler_types

        # Check MCP handler level
        mcp_handler = next(h for h in root_logger.handlers if isinstance(h, MCPRichHandler))
        handler = mcp_handler
        assert handler.level == logging.INFO

    def test_setup_third_party_loggers(self) -> None:
        """Test setup of third-party logger configurations."""
        setup_logging(debug=True)

        # Check asyncio logger
        asyncio_logger = logging.getLogger("asyncio")
        assert asyncio_logger.level == logging.ERROR

        # Check uvicorn loggers
        uvicorn_logger = logging.getLogger("uvicorn")
        assert uvicorn_logger.level == logging.INFO
        assert not uvicorn_logger.propagate
        assert len(uvicorn_logger.handlers) == 1
        assert isinstance(uvicorn_logger.handlers[0], MCPRichHandler)

        uvicorn_access_logger = logging.getLogger("uvicorn.access")
        assert uvicorn_access_logger.level == logging.INFO
        assert not uvicorn_access_logger.propagate

        uvicorn_error_logger = logging.getLogger("uvicorn.error")
        assert uvicorn_error_logger.level == logging.WARNING
        assert not uvicorn_error_logger.propagate

    def test_setup_mcp_loggers_debug_mode(self) -> None:
        """Test MCP logger setup in debug mode."""
        setup_logging(debug=True)

        # Check MCP loggers
        mcp_logger = logging.getLogger("mcp")
        assert mcp_logger.level == logging.WARNING
        assert not mcp_logger.propagate

        mcp_server_logger = logging.getLogger("mcp.server")
        assert mcp_server_logger.level == logging.INFO  # Debug mode
        assert not mcp_server_logger.propagate

    def test_setup_mcp_loggers_normal_mode(self) -> None:
        """Test MCP logger setup in normal mode."""
        setup_logging(debug=False)

        # Check MCP server logger in normal mode
        mcp_server_logger = logging.getLogger("mcp.server")
        assert mcp_server_logger.level == logging.ERROR  # Normal mode
        assert not mcp_server_logger.propagate

    def test_handler_replacement(self) -> None:
        """Test that existing handlers are properly replaced."""
        # Add some existing handlers
        root_logger = logging.getLogger()
        old_handler = logging.StreamHandler()
        root_logger.addHandler(old_handler)

        uvicorn_logger = logging.getLogger("uvicorn")
        old_uvicorn_handler = logging.StreamHandler()
        uvicorn_logger.addHandler(old_uvicorn_handler)

        # Setup rich logging
        setup_logging(debug=True)

        # Check that old handlers were removed
        assert old_handler not in root_logger.handlers
        assert old_uvicorn_handler not in uvicorn_logger.handlers

        # Check that new handlers are MCPRichHandler and RotatingFileHandler instances
        assert len(root_logger.handlers) == 2  # Console + file handler
        handler_types = [type(h).__name__ for h in root_logger.handlers]
        assert "MCPRichHandler" in handler_types
        assert "RotatingFileHandler" in handler_types

        assert len(uvicorn_logger.handlers) == 1
        assert isinstance(uvicorn_logger.handlers[0], MCPRichHandler)

    def test_uvicorn_access_formatter(self) -> None:
        """Test custom Uvicorn access log formatter."""
        setup_logging(debug=True)

        uvicorn_access_logger = logging.getLogger("uvicorn.access")
        handler = uvicorn_access_logger.handlers[0]
        formatter = handler.formatter
        assert formatter is not None, "Formatter should not be None"

        # Create a mock record like uvicorn creates
        record = logging.LogRecord(
            name="uvicorn.access",
            level=logging.INFO,
            pathname="access.py",
            lineno=1,
            msg='%s - "%s" %s',
            args=("127.0.0.1:12345", "GET /test", "200"),
            exc_info=None,
        )

        formatted = formatter.format(record)

        # Should format as: client - "method path" status
        assert formatted == '127.0.0.1:12345 - "GET /test" 200'

    def test_uvicorn_access_formatter_insufficient_args(self) -> None:
        """Test Uvicorn access formatter with insufficient arguments."""
        setup_logging(debug=True)

        uvicorn_access_logger = logging.getLogger("uvicorn.access")
        handler = uvicorn_access_logger.handlers[0]
        formatter = handler.formatter
        assert formatter is not None, "Formatter should not be None"

        # Create a record with insufficient args
        record = logging.LogRecord(
            name="uvicorn.access",
            level=logging.INFO,
            pathname="access.py",
            lineno=1,
            msg="Incomplete log entry %s",  # Proper format string
            args=("127.0.0.1",),  # Only 1 arg
            exc_info=None,
        )

        formatted = formatter.format(record)

        # Should fall back to default formatting
        assert formatted == "Incomplete log entry 127.0.0.1"

    def test_uvicorn_access_formatter_no_args(self) -> None:
        """Test Uvicorn access formatter with no arguments."""
        setup_logging(debug=True)

        uvicorn_access_logger = logging.getLogger("uvicorn.access")
        handler = uvicorn_access_logger.handlers[0]
        formatter = handler.formatter
        assert formatter is not None, "Formatter should not be None"

        # Create a record with no args
        record = logging.LogRecord(
            name="uvicorn.access",
            level=logging.INFO,
            pathname="access.py",
            lineno=1,
            msg="No args log entry",
            args=(),
            exc_info=None,
        )

        formatted = formatter.format(record)

        # Should fall back to default formatting
        assert formatted == "No args log entry"


class TestGetLogger:
    """Test cases for get_logger function."""

    def test_get_logger(self) -> None:
        """Test get_logger function."""
        logger = get_logger("test.module")

        assert isinstance(logger, logging.Logger)
        assert logger.name == "test.module"

    def test_get_logger_hierarchy(self) -> None:
        """Test logger hierarchy with get_logger."""
        parent_logger = get_logger("parent")
        child_logger = get_logger("parent.child")

        assert child_logger.parent == parent_logger

    def test_get_logger_same_instance(self) -> None:
        """Test that get_logger returns the same instance for the same name."""
        logger1 = get_logger("same.name")
        logger2 = get_logger("same.name")

        assert logger1 is logger2


class TestLoggingIntegration:
    """Integration tests for logging configuration."""

    def teardown_method(self) -> None:
        """Clean up logging configuration after each test."""
        # Reset root logger
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        root_logger.setLevel(logging.WARNING)

    def test_logging_output_capture(self) -> None:
        """Test that logging output can be captured for testing."""
        # Setup logging with a test handler
        test_handler = logging.StreamHandler(StringIO())
        test_handler.setLevel(logging.DEBUG)

        root_logger = logging.getLogger()
        root_logger.addHandler(test_handler)
        root_logger.setLevel(logging.DEBUG)

        # Create a logger and log a message
        logger = get_logger("test.output")
        logger.info("Test message")

        # Check that message was captured
        output = test_handler.stream.getvalue()
        assert "Test message" in output

    def test_server_logger_formatting(self) -> None:
        """Test that server loggers format messages correctly."""
        setup_logging(debug=True)

        # Create a server logger
        server_logger = get_logger("mcp_foxxy_bridge.servers.test_server")

        # This would be tested more thoroughly in integration tests
        # where we can capture the actual Rich output
        assert server_logger.name == "mcp_foxxy_bridge.servers.test_server"

    @patch("mcp_foxxy_bridge.utils.logging.Console")
    def test_rich_console_configuration(self, mock_console_class: MagicMock) -> None:
        """Test Rich console configuration."""
        mock_console = MagicMock()
        mock_console_class.return_value = mock_console

        MCPRichHandler()

        # Verify console was configured correctly
        mock_console_class.assert_called_with(
            stderr=True,
            force_terminal=True,
            width=120,
        )

    def test_multiple_setup_calls(self) -> None:
        """Test that multiple setup calls work correctly."""
        # First setup
        setup_logging(debug=True)
        root_handlers_count_1 = len(logging.getLogger().handlers)

        # Second setup - should replace handlers
        setup_logging(debug=False)
        root_handlers_count_2 = len(logging.getLogger().handlers)

        # Should still have the same number of handlers (console + file)
        assert root_handlers_count_1 == root_handlers_count_2 == 2

        # Root logger level should be updated
        assert logging.getLogger().level == logging.INFO
