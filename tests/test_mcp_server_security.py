"""Security tests for the MCP server."""

from unittest.mock import MagicMock, patch

from mcp_foxxy_bridge.mcp_server import _find_available_port


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

        result_port = _find_available_port(test_host, requested_port)

        # Verify the socket was bound to the specified host, not empty string
        mock_socket.bind.assert_called_with((test_host, requested_port))
        assert result_port == requested_port


def test_find_available_port_fallback_uses_specified_host() -> None:
    """Test that _find_available_port fallback port binding uses specified host.

    This test specifically verifies the security fix in the fallback code path.
    """
    test_host = "127.0.0.1"
    requested_port = 8080
    fallback_port = 12345

    with patch("socket.socket") as mock_socket_class:
        # Mock the first 100 socket attempts that fail
        failing_sockets = []
        for _ in range(100):
            failing_socket = MagicMock()
            failing_socket.bind.side_effect = OSError("Port in use")
            failing_sockets.append(failing_socket)

        # Mock the final fallback socket that succeeds
        fallback_socket = MagicMock()
        fallback_socket.bind.return_value = None
        fallback_socket.getsockname.return_value = (test_host, fallback_port)

        # Setup the socket class to return context managers
        socket_instances = [*failing_sockets, fallback_socket]
        mock_socket_class.return_value.__enter__.side_effect = socket_instances

        result_port = _find_available_port(test_host, requested_port)

        # Verify the fallback socket was bound to the specified host, not empty string
        # This is the critical security fix - should be (host, 0) not ("", 0)
        fallback_socket.bind.assert_called_with((test_host, 0))
        assert result_port == fallback_port


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

            _find_available_port(test_host, 8080)

            # Verify that all bind calls use the specified host
            for call in mock_socket.bind.call_args_list:
                host_used = call[0][0][0]  # First arg, first tuple element
                # Should never bind to empty string (all interfaces)
                msg = f"Security violation: bound to all interfaces instead of {test_host}"
                assert host_used != "", msg
                assert host_used == test_host, f"Expected host {test_host}, got {host_used}"
