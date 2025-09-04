#
# MCP Foxxy Bridge - Daemon Management
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
"""Daemon process management utilities."""

import asyncio
import contextlib
import hashlib
import json
import os
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import psutil
from rich.console import Console

from mcp_foxxy_bridge.config.config_loader import load_bridge_config_from_file


class DaemonManager:
    """Manage the bridge daemon process."""

    @staticmethod
    def generate_daemon_name(config_file: str | Path) -> str:
        """Generate a unique daemon name based on the config file path.

        Args:
            config_file: Path to the configuration file

        Returns:
            A short, unique daemon name
        """
        config_path = Path(config_file).resolve()

        # Create a short hash from the absolute path
        path_hash = hashlib.md5(str(config_path).encode()).hexdigest()[:8]

        # Use the config file stem (name without extension) plus hash
        config_stem = config_path.stem
        return f"{config_stem}-{path_hash}"

    @staticmethod
    def find_running_bridge_processes() -> list[dict[str, Any]]:
        """Find all running bridge processes by scanning the process table.

        Returns:
            List of process info dictionaries for running bridge instances
        """
        running_processes = []

        try:
            for proc in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):  # type: ignore[no-untyped-call]
                try:
                    cmdline = proc.info["cmdline"]
                    if not cmdline:
                        continue

                    # Look for bridge server processes only
                    cmdline_str = " ".join(cmdline)

                    # Match only actual bridge server invocations by looking at the executed command
                    executable = cmdline[0] if cmdline else ""

                    # Check if this is a bridge server process
                    is_bridge = False

                    # Direct invocation of bridge commands
                    if executable.endswith(("foxxy-bridge", "mcp-foxxy-bridge")):
                        is_bridge = True
                    # Python module invocation
                    elif executable.endswith(("python", "python3")):
                        if len(cmdline) > 2 and cmdline[1] == "-m" and "mcp_foxxy_bridge" in cmdline[2]:
                            is_bridge = True

                    if is_bridge:
                        # Extract configuration info from command line
                        config_file = None
                        port = None
                        host = None
                        name = None

                        # Parse command line arguments
                        for i, arg in enumerate(cmdline):
                            if arg in ["--bridge-config", "-c"] and i + 1 < len(cmdline):
                                config_file = cmdline[i + 1]
                            elif arg in ["--port", "-p"] and i + 1 < len(cmdline):
                                with contextlib.suppress(ValueError):
                                    port = int(cmdline[i + 1])
                            elif arg in ["--host"] and i + 1 < len(cmdline):
                                host = cmdline[i + 1]
                            elif arg in ["--name", "-n"] and i + 1 < len(cmdline):
                                name = cmdline[i + 1]

                        process_info = {
                            "pid": proc.info["pid"],
                            "name": name or f"foreground-{proc.info['pid']}",
                            "status": "running",
                            "type": "foreground",
                            "config_file": config_file,
                            "port": port,
                            "host": host,
                            "started_at": str(int(proc.info["create_time"])),
                            "cmdline": cmdline_str,
                        }

                        running_processes.append(process_info)

                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    # Process may have disappeared or we don't have access
                    continue

        except Exception:
            # If process scanning fails entirely, just return empty list
            pass

        return running_processes

    @staticmethod
    def list_daemons(config_dir: Path) -> list[dict[str, Any]]:
        """List all running bridge instances (both daemon and foreground).

        Args:
            config_dir: Configuration directory to search

        Returns:
            List of daemon/process info dictionaries
        """
        daemons = []
        daemon_pids = set()

        # Find all daemon info files
        for info_file in config_dir.glob("bridge-*.json"):
            try:
                with info_file.open("r") as f:
                    daemon_info = json.load(f)

                # Check if process is still running
                pid = daemon_info.get("pid")
                if pid and psutil.pid_exists(pid):  # type: ignore[no-untyped-call]
                    daemon_info["status"] = "running"
                    daemon_info["type"] = "daemon"
                    daemons.append(daemon_info)
                    daemon_pids.add(pid)
                else:
                    # Process is dead, clean up stale files and skip
                    daemon_info["status"] = "stopped"
                    try:
                        # Extract daemon name from file name
                        daemon_name = info_file.stem.replace("bridge-", "")
                        info_file.unlink()  # Remove .json file

                        # Also remove corresponding PID file
                        pid_file = config_dir / f"bridge-{daemon_name}.pid"
                        if pid_file.exists():
                            pid_file.unlink()
                    except (PermissionError, OSError):
                        # If cleanup fails, still show the stopped daemon
                        daemons.append(daemon_info)

            except (json.JSONDecodeError, FileNotFoundError, PermissionError):
                # Skip invalid or inaccessible files
                continue

        # Also check for default daemon
        default_info_file = config_dir / "bridge.json"
        if default_info_file.exists():
            try:
                with default_info_file.open("r") as f:
                    daemon_info = json.load(f)

                # Check if process is still running
                pid = daemon_info.get("pid")
                if pid and psutil.pid_exists(pid):  # type: ignore[no-untyped-call]
                    daemon_info["status"] = "running"
                    daemon_info["type"] = "daemon"
                    daemons.append(daemon_info)
                    daemon_pids.add(pid)
                else:
                    # Process is dead, clean up stale files and skip
                    daemon_info["status"] = "stopped"
                    try:
                        default_info_file.unlink()  # Remove .json file

                        # Also remove corresponding PID file
                        pid_file = config_dir / "bridge.pid"
                        if pid_file.exists():
                            pid_file.unlink()
                    except (PermissionError, OSError):
                        # If cleanup fails, still show the stopped daemon
                        daemons.append(daemon_info)

            except (json.JSONDecodeError, FileNotFoundError, PermissionError):
                pass

        # Find running foreground processes not already tracked as daemons
        daemons.extend(
            process_info
            for process_info in DaemonManager.find_running_bridge_processes()
            if process_info["pid"] not in daemon_pids
        )

        return daemons

    @staticmethod
    def get_daemon_info_by_name(config_dir: Path, daemon_name: str) -> dict[str, Any] | None:
        """Get daemon info by name without loading config.

        Args:
            config_dir: Configuration directory
            daemon_name: Name of the daemon

        Returns:
            Daemon info dictionary or None if not found
        """
        if daemon_name == "default":
            info_file = config_dir / "bridge.json"
        else:
            info_file = config_dir / f"bridge-{daemon_name}.json"

        # First try to find in daemon files
        if info_file.exists():
            try:
                with info_file.open("r") as f:
                    daemon_info = json.load(f)

                # Check if process is still running
                pid = daemon_info.get("pid")
                if pid and psutil.pid_exists(pid):  # type: ignore[no-untyped-call]
                    daemon_info["status"] = "running"
                    daemon_info["type"] = "daemon"
                    try:
                        process = psutil.Process(pid)  # type: ignore[no-untyped-call]
                        daemon_info["memory_info"] = process.memory_info()._asdict()
                        daemon_info["cpu_percent"] = process.cpu_percent()  # type: ignore[no-untyped-call]
                        daemon_info["create_time"] = process.create_time()  # type: ignore[no-untyped-call]
                    except psutil.NoSuchProcess:
                        daemon_info["status"] = "stopped"
                        # Clean up stale daemon files
                        _cleanup_stale_daemon_files(config_dir, daemon_name)
                else:
                    daemon_info["status"] = "stopped"
                    # Clean up stale daemon files
                    _cleanup_stale_daemon_files(config_dir, daemon_name)

                return daemon_info  # type: ignore[no-any-return]
            except (json.JSONDecodeError, FileNotFoundError, PermissionError):
                pass

        # If not found in daemon files, check running processes
        for process_info in DaemonManager.find_running_bridge_processes():
            if process_info["name"] == daemon_name:
                return process_info

        return None

    def __init__(self, config_dir: Path, console: Console | None = None, daemon_name: str | None = None) -> None:
        """Initialize daemon manager.

        Args:
            config_dir: Configuration directory
            console: Rich console for output
            daemon_name: Optional daemon name for named daemons
        """
        self.config_dir = config_dir
        self.console = console or Console()
        self.daemon_name = daemon_name

        # Use daemon name for file naming if provided
        if daemon_name:
            self.pid_file = config_dir / f"bridge-{daemon_name}.pid"
            self.log_file = config_dir / f"bridge-{daemon_name}.log"
            self.info_file = config_dir / f"bridge-{daemon_name}.json"
        else:
            self.pid_file = config_dir / "bridge.pid"
            self.log_file = config_dir / "bridge.log"
            self.info_file = config_dir / "bridge.json"

    async def start_daemon(
        self,
        config_file: str | None = None,
        host: str | None = None,
        port: int | None = None,
        detach: bool = True,
        debug: bool = False,
    ) -> bool:
        """Start the bridge daemon.

        Args:
            config_file: Configuration file path
            host: Server host override
            port: Server port override
            detach: Whether to run in background (daemon mode)
            debug: Whether to enable debug logging

        Returns:
            True if started successfully
        """
        if await self.is_running():
            self.console.print("[yellow]Bridge daemon is already running[/yellow]")
            return False

        # Build command
        cmd = [sys.executable, "-m", "mcp_foxxy_bridge"]

        if debug:
            cmd.append("--debug")

        if config_file:
            cmd.extend(["--bridge-config", config_file])
        else:
            # Use default config
            default_config = self.config_dir / "config.json"
            if default_config.exists():
                cmd.extend(["--bridge-config", str(default_config)])

        if host:
            cmd.extend(["--host", host])

        if port:
            cmd.extend(["--port", str(port)])

        # Ensure log directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)

        if detach:
            # Start daemon in background
            try:
                with self.log_file.open("w") as log_f:
                    process = subprocess.Popen(
                        cmd,
                        stdout=log_f,
                        stderr=subprocess.STDOUT,
                        stdin=subprocess.DEVNULL,
                        start_new_session=True,  # This already creates a new session on Unix
                    )

                # Write PID file
                with self.pid_file.open("w") as pid_f:
                    pid_f.write(str(process.pid))

                # Write daemon info file
                daemon_info = {
                    "pid": process.pid,
                    "name": self.daemon_name or "default",
                    "config_file": str(Path(config_file).resolve()) if config_file else None,
                    "started_at": datetime.now().isoformat(),
                    "host": host,
                    "port": port,
                    "log_file": str(self.log_file),
                    "pid_file": str(self.pid_file),
                }

                with self.info_file.open("w") as info_f:
                    json.dump(daemon_info, info_f, indent=2)

                # Give it a moment to start, then detach completely
                await asyncio.sleep(1)  # Reduced wait time

                # Detach from the process - don't maintain reference
                pid = process.pid
                process = None  # type: ignore[assignment] # Release the process reference

                # Quick check if process exists without blocking
                return bool(await self._is_process_running(pid))

            except Exception as e:
                self.console.print(f"[red]Failed to start daemon: {e}[/red]")
                return False
        else:
            # Start in foreground
            try:
                result = subprocess.run(cmd, check=False)
                return result.returncode == 0
            except Exception as e:
                self.console.print(f"[red]Failed to start daemon: {e}[/red]")
                return False

    async def stop_daemon(self, force: bool = False) -> bool:
        """Stop the bridge daemon.

        Args:
            force: Force stop with SIGKILL

        Returns:
            True if stopped successfully
        """
        pid = await self._get_daemon_pid()
        if not pid:
            self.console.print("[yellow]Bridge daemon is not running[/yellow]")
            return True

        try:
            process = psutil.Process(pid)  # type: ignore[no-untyped-call]

            if force:
                process.kill()  # type: ignore[no-untyped-call]
                self.console.print(f"[red]Forcibly killed[/red] daemon (PID: {pid})")
            else:
                process.terminate()  # type: ignore[no-untyped-call]

                # Wait for graceful shutdown
                try:
                    process.wait(timeout=10)  # type: ignore[no-untyped-call]
                    self.console.print(f"[green]✓[/green] Stopped daemon (PID: {pid})")
                except psutil.TimeoutExpired:
                    self.console.print("[yellow]Daemon didn't stop gracefully, forcing...[/yellow]")
                    process.kill()  # type: ignore[no-untyped-call]
                    process.wait(timeout=5)  # type: ignore[no-untyped-call]
                    self.console.print(f"[red]Forcibly stopped[/red] daemon (PID: {pid})")

            # Clean up PID file
            if self.pid_file.exists():
                self.pid_file.unlink()

            # Wait for daemon to be fully stopped and port to be released
            if not await self._wait_for_daemon_stopped():
                self.console.print("[yellow]Warning: Daemon may not be fully stopped[/yellow]")

            host, port = await self._get_bridge_host_port()
            if not await self._wait_for_port_available(host, port):
                self.console.print(f"[yellow]Warning: Port {port} on {host} may still be in use[/yellow]")

            return True

        except psutil.NoSuchProcess:
            self.console.print("[yellow]Daemon process no longer exists[/yellow]")
            if self.pid_file.exists():
                self.pid_file.unlink()
            return True
        except Exception as e:
            self.console.print(f"[red]Failed to stop daemon: {e}[/red]")
            return False

    async def restart_daemon(self, force: bool = False, **start_kwargs: Any) -> bool:
        """Restart the bridge daemon.

        Args:
            force: Force stop before restart
            **start_kwargs: Arguments for start_daemon

        Returns:
            True if restarted successfully
        """
        if await self.is_running():
            if not await self.stop_daemon(force):
                return False

        # Wait for port to be available
        host, port = await self._get_bridge_host_port()
        if not await self._wait_for_port_available(host, port):
            self.console.print(f"[red]Error: Port {port} on {host} is still in use after stopping daemon[/red]")
            return False

        return await self.start_daemon(**start_kwargs)

    async def _wait_for_port_available(self, host: str = "127.0.0.1", port: int = 9090, timeout: int = 30) -> bool:
        """Wait for a port to become available.

        Args:
            host: Host to check (default: 127.0.0.1)
            port: Port number to check
            timeout: Maximum time to wait in seconds

        Returns:
            True if port became available, False if timeout
        """
        start_time = asyncio.get_event_loop().time()

        while (asyncio.get_event_loop().time() - start_time) < timeout:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    sock.bind((host, port))
                    return True
            except OSError:
                await asyncio.sleep(0.5)

        return False

    async def _wait_for_daemon_stopped(self, timeout: int = 30) -> bool:
        """Wait for daemon to be fully stopped.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if daemon stopped, False if timeout
        """
        start_time = asyncio.get_event_loop().time()

        while (asyncio.get_event_loop().time() - start_time) < timeout:
            if not await self.is_running():
                return True
            await asyncio.sleep(0.5)

        return False

    async def _get_bridge_host_port(self) -> tuple[str, int]:
        """Get bridge host and port from config.

        Returns:
            Tuple of (host, port) from config, defaults to ("127.0.0.1", 9090)
        """
        try:
            # Try to find config file - look in common locations
            config_paths = [
                Path.home() / ".config" / "foxxy-bridge" / "config.json",
                Path.cwd() / "config.json",
            ]

            for config_path in config_paths:
                if config_path.exists():
                    try:
                        bridge_config = load_bridge_config_from_file(str(config_path), dict(os.environ))
                        if bridge_config and bridge_config.bridge:
                            configured_host = getattr(bridge_config.bridge, "host", "127.0.0.1")
                            # If server binds to 0.0.0.0, check port on localhost instead
                            host = "127.0.0.1" if configured_host == "0.0.0.0" else configured_host  # noqa: S104
                            port = getattr(bridge_config.bridge, "port", 9090)
                            return (host, port)
                    except Exception:
                        pass

        except Exception:
            pass

        return ("127.0.0.1", 9090)

    async def get_daemon_status(self) -> dict[str, Any]:
        """Get daemon status information.

        Returns:
            Dictionary with daemon status details
        """
        pid = await self._get_daemon_pid()
        if not pid:
            return {"status": "stopped", "pid": None}

        try:
            process = psutil.Process(pid)  # type: ignore[no-untyped-call]

            # Get process info
            info = {
                "status": "running",
                "pid": pid,
                "name": process.name(),  # type: ignore[no-untyped-call]
                "create_time": process.create_time(),  # type: ignore[no-untyped-call]
                "memory_info": process.memory_info()._asdict(),
                "cpu_percent": process.cpu_percent(),  # type: ignore[no-untyped-call]
            }

            # Try to get connection info if available
            try:
                connections = process.connections()
                for conn in connections:
                    if conn.status == "LISTEN":
                        info["host"] = conn.laddr.ip
                        info["port"] = conn.laddr.port
                        break
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                pass

            return info

        except psutil.NoSuchProcess:
            # Process no longer exists, clean up
            if self.pid_file.exists():
                self.pid_file.unlink()
            return {"status": "stopped", "pid": None}
        except Exception as e:
            return {"status": "error", "pid": pid, "error": str(e)}

    async def is_running(self) -> bool:
        """Check if daemon is running.

        Returns:
            True if daemon is running
        """
        pid = await self._get_daemon_pid()
        return bool(pid and await self._is_process_running(pid))

    async def get_log_content(self, lines: int = 50) -> str:
        """Get daemon log content.

        Args:
            lines: Number of lines to read from end

        Returns:
            Log content as string
        """
        if not self.log_file.exists():
            return "No log file found"

        try:
            # Read last N lines
            with self.log_file.open("r") as f:
                all_lines = f.readlines()
                return "".join(all_lines[-lines:])
        except Exception as e:
            return f"Error reading log: {e}"

    async def follow_logs(self, console: Console) -> None:
        """Follow daemon logs in real-time.

        Args:
            console: Rich console for output
        """
        if not self.log_file.exists():
            console.print("[red]No log file found[/red]")
            return

        try:
            # Start from end of file
            with self.log_file.open("r") as f:
                # Go to end
                f.seek(0, 2)

                console.print(f"[dim]Following logs: {self.log_file}[/dim]")
                console.print("[dim]Press Ctrl+C to stop[/dim]\n")

                while True:
                    line = f.readline()
                    if line:
                        console.print(line.rstrip())
                    else:
                        await asyncio.sleep(0.1)

        except KeyboardInterrupt:
            console.print("\n[yellow]Stopped following logs[/yellow]")
        except Exception as e:
            console.print(f"[red]Error following logs: {e}[/red]")

    async def _get_daemon_pid(self) -> int | None:
        """Get daemon PID from file.

        Returns:
            PID if found and valid, None otherwise
        """
        if not self.pid_file.exists():
            return None

        try:
            with self.pid_file.open("r") as f:
                pid_str = f.read().strip()
                return int(pid_str) if pid_str else None
        except (ValueError, FileNotFoundError):
            return None

    async def _is_process_running(self, pid: int) -> bool:
        """Check if process with PID is running.

        Args:
            pid: Process ID

        Returns:
            True if process is running
        """
        try:
            return psutil.pid_exists(pid)  # type: ignore[no-untyped-call, no-any-return]
        except Exception:
            return False


def _cleanup_stale_daemon_files(config_dir: Path, daemon_name: str) -> None:
    """Clean up stale daemon files when process is confirmed dead."""
    try:
        if daemon_name == "default":
            files_to_remove = [
                config_dir / "bridge.pid",
                config_dir / "bridge.json",
            ]
        else:
            files_to_remove = [
                config_dir / f"bridge-{daemon_name}.pid",
                config_dir / f"bridge-{daemon_name}.json",
            ]

        for file_path in files_to_remove:
            if file_path.exists():
                try:
                    file_path.unlink()
                except (PermissionError, OSError):
                    # Ignore cleanup failures - don't break status checking
                    pass

    except Exception:
        # Ignore cleanup failures - don't break status checking
        pass
