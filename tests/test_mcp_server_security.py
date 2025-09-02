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

"""Security tests for the MCP server."""

from unittest.mock import MagicMock, patch

from mcp_foxxy_bridge.oauth.utils import find_available_port


def test_find_available_port_uses_specified_host() -> None:
    """Test that _find_available_port uses the specified host, not all interfaces.

    This test verifies the security fix that prevents binding to all network interfaces.
    """
    test_host = "127.0.0.1"
    requested_port = 0  # Use system-assigned port for testing

    with patch("socket.socket") as mock_socket_class:
        mock_socket = MagicMock()
        mock_socket_class.return_value.__enter__.return_value = mock_socket
        mock_socket.getsockname.return_value = (test_host, 12345)

        # When the requested port is immediately available
        mock_socket.bind.return_value = None  # Successful bind

        result_port = find_available_port(requested_port, host=test_host)

        # Verify the socket was bound to the specified host, not empty string
        mock_socket.bind.assert_called_with((test_host, requested_port))
        assert result_port == requested_port


def test_find_available_port_fallback_uses_specified_host() -> None:
    """Test that _find_available_port fallback port binding uses specified host.

    This test specifically verifies the security fix in the fallback code path.
    """
    test_host = "127.0.0.1"
    requested_port = 8080

    with patch("socket.socket") as mock_socket_class:
        # Mock the first 99 socket attempts that fail (for ports 8080-8178)
        failing_sockets = []
        for _ in range(99):
            failing_socket = MagicMock()
            failing_socket.bind.side_effect = OSError("Port in use")
            failing_sockets.append(failing_socket)

        # Mock the final socket that succeeds (for port 8179)
        success_socket = MagicMock()
        success_socket.bind.return_value = None
        success_socket.getsockname.return_value = (test_host, 8179)

        # Setup the socket class to return context managers
        socket_instances = [*failing_sockets, success_socket]
        mock_socket_class.return_value.__enter__.side_effect = socket_instances

        result_port = find_available_port(requested_port, host=test_host)

        # Verify the success socket was bound to the specified host, not empty string
        # The last successful socket should be bound to (test_host, requested_port + 99)
        expected_final_port = requested_port + 99
        success_socket.bind.assert_called_with((test_host, expected_final_port))
        assert result_port == expected_final_port


def test_find_available_port_never_binds_to_all_interfaces() -> None:
    """Test that _find_available_port never binds to all network interfaces.

    This is a comprehensive security test to ensure no binding to "" or "0.0.0.0"
    unless explicitly requested.
    """
    test_hosts = ["127.0.0.1", "localhost", "192.168.1.100"]

    for test_host in test_hosts:
        with patch("socket.socket") as mock_socket_class:
            mock_socket = MagicMock()
            mock_socket_class.return_value.__enter__.return_value = mock_socket
            mock_socket.getsockname.return_value = (test_host, 8080)
            mock_socket.bind.return_value = None

            find_available_port(8080, host=test_host)

            # Verify that all bind calls use the specified host
            for call in mock_socket.bind.call_args_list:
                host_used = call[0][0][0]  # First arg, first tuple element
                # Should never bind to empty string (all interfaces)
                msg = f"Security violation: bound to all interfaces instead of {test_host}"
                assert host_used != "", msg
                assert host_used == test_host, f"Expected host {test_host}, got {host_used}"
