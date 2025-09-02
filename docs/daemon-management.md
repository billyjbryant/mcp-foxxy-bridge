# Daemon Management Guide

MCP Foxxy Bridge includes comprehensive daemon management capabilities for running the bridge server in the background with process monitoring and lifecycle management.

## Quick Start

```bash
# Start as daemon
foxxy-bridge server start --daemon

# Check running daemons
foxxy-bridge server list

# Stop daemon
foxxy-bridge server stop
```

## Daemon Operations

### Starting a Daemon

```bash
# Start with default configuration
foxxy-bridge server start --daemon

# Start with custom configuration
foxxy-bridge server start --daemon --config /path/to/config.json

# Start with specific port and host
foxxy-bridge server start --daemon --port 9000 --host 0.0.0.0
```

### Listing Running Daemons

```bash
foxxy-bridge server list
```

**Example Output:**

```
┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Name               ┃ PID      ┃ Status     ┃ Config File                          ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ default            │ 12345    │ running    │ ~/.config/foxxy-bridge/config.json  │
│ production         │ 12346    │ running    │ /etc/foxxy-bridge/prod-config.json  │
└────────────────────┴──────────┴────────────┴──────────────────────────────────────┘
```

### Stopping Daemons

```bash
# Stop specific daemon by name
foxxy-bridge server stop production

# Force stop if graceful shutdown fails
foxxy-bridge server stop production --force

# Stop all daemons
foxxy-bridge server stop --all
```

### Daemon Status

```bash
# Check status of specific daemon
foxxy-bridge server server-status production

# Check status with JSON output
foxxy-bridge server server-status production --format json
```

## Process Management

### Process Identification

Daemons are identified by:
1. **Configuration Path**: Each unique config file creates a separate daemon
2. **Daemon Name**: Derived from config filename or explicitly set
3. **Process ID (PID)**: Operating system process identifier

### Process Monitoring

The daemon manager automatically:
- Tracks process status and health
- Monitors for unexpected exits
- Maintains process metadata
- Cleans up orphaned processes

### Process Files

**PID Files:**

- Location: `~/.config/foxxy-bridge/pids/`
- Format: `{daemon-name}.pid`
- Contains: Process ID and metadata

**Log Files:**

- Location: `~/.config/foxxy-bridge/logs/`
- Format: `{daemon-name}.log`
- Automatic log rotation supported

## Configuration

### Daemon-Specific Options

```json
{
  "bridge": {
    "daemon": {
      "pid_file": "~/.config/foxxy-bridge/pids/bridge.pid",
      "log_file": "~/.config/foxxy-bridge/logs/bridge.log",
      "user": "foxxy-bridge",
      "group": "foxxy-bridge"
    }
  }
}
```

### Multiple Daemon Configurations

Run multiple bridge instances with different configurations:

```bash
# Production instance
foxxy-bridge server start --daemon --config /etc/foxxy-bridge/prod.json

# Development instance
foxxy-bridge server start --daemon --config ~/.config/foxxy-bridge/dev.json

# Testing instance
foxxy-bridge server start --daemon --config ./test-config.json
```

## Daemon Health Monitoring

### Health Checks

The daemon manager performs automatic health monitoring:

```bash
# Manual health check
foxxy-bridge server server-status production

# Continuous monitoring
foxxy-bridge server server-status production --watch
```

### Health Check Operations

- **Process Status**: Verify daemon process is running
- **Port Availability**: Check if server port is responsive
- **API Endpoint**: Test bridge API health endpoint
- **MCP Server Status**: Monitor connected MCP server health

### Automatic Recovery

**Process Restart:**

- Automatic restart on unexpected exit
- Configurable retry attempts and delays
- Process state preservation

**Configuration Reload:**

- Hot reload on configuration changes
- Graceful server restart when needed
- Validation before applying changes

## Service Integration

### systemd Integration

Create a systemd service file:

```ini
# /etc/systemd/system/foxxy-bridge.service
[Unit]
Description=MCP Foxxy Bridge
After=network.target

[Service]
Type=forking
User=foxxy-bridge
Group=foxxy-bridge
ExecStart=/usr/local/bin/foxxy-bridge server start --daemon --config /etc/foxxy-bridge/config.json
ExecStop=/usr/local/bin/foxxy-bridge server stop
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**Enable and start:**

```bash
sudo systemctl enable foxxy-bridge
sudo systemctl start foxxy-bridge
sudo systemctl status foxxy-bridge
```

### Docker Daemon Mode

Run as daemon in Docker containers:

```dockerfile
# Use daemon mode in container
CMD ["foxxy-bridge", "server", "start", "--daemon", "--host", "0.0.0.0"]
```

## Troubleshooting

### Common Issues

**Daemon Won't Start:**

```bash
# Check configuration
foxxy-bridge config validate

# Check port availability
lsof -i :8080

# Check permissions
ls -la ~/.config/foxxy-bridge/
```

**Daemon Stops Unexpectedly:**

```bash
# Check daemon logs
tail -f ~/.config/foxxy-bridge/logs/bridge.log

# Check system logs
journalctl -u foxxy-bridge

# Verify process limits
ulimit -a
```

**Multiple Daemons Conflict:**

```bash
# List all running daemons
foxxy-bridge server list

# Check port conflicts
netstat -tulpn | grep :8080

# Stop conflicting daemons
foxxy-bridge server stop --all
```

### Debug Mode

Enable debug logging for daemon troubleshooting:

```bash
# Start daemon with debug logging
foxxy-bridge --debug server start --daemon

# Check debug logs
tail -f ~/.config/foxxy-bridge/logs/bridge.log | grep DEBUG
```

### Process Cleanup

Clean up orphaned processes and files:

```bash
# Manual cleanup
rm -f ~/.config/foxxy-bridge/pids/*.pid
pkill -f foxxy-bridge

# Automatic cleanup on start
foxxy-bridge server start --daemon --cleanup
```

## Best Practices

### Production Deployment

1. **Dedicated User**: Run daemon as non-root user
2. **Configuration Management**: Use absolute paths for config files
3. **Log Rotation**: Configure log rotation to prevent disk space issues
4. **Monitoring**: Set up external monitoring for daemon health
5. **Backup**: Regular backup of configuration and state files

### Development Environment

1. **Separate Configs**: Use different configurations for dev/test/prod
2. **Port Management**: Use non-conflicting ports for multiple instances
3. **Log Monitoring**: Monitor daemon logs during development
4. **Quick Restart**: Use `--force` for rapid development cycles

### Security Considerations

1. **File Permissions**: Restrict access to PID and log files
2. **Process Isolation**: Run each daemon with minimal privileges
3. **Configuration Security**: Protect configuration files containing secrets
4. **Network Security**: Bind to localhost in development, use proper firewall rules in production

## Migration from Direct Mode

**Convert from direct server execution:**

```bash
# Old way (blocking)
foxxy-bridge server start --port 8080

# New way (daemon)
foxxy-bridge server start --daemon --port 8080
```

**Process management benefits:**

- Background execution
- Process monitoring
- Automatic restart
- Multiple instance support
- Service integration
