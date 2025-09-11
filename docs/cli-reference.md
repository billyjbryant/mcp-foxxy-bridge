# CLI Reference Guide

The MCP Foxxy Bridge CLI provides comprehensive management capabilities with facility-aware logging for better operational visibility.

## Table of Contents

- [Global Options](#global-options)
- [Server Management](#server-management)
- [MCP Server Management](#mcp-server-management)
- [Configuration Management](#configuration-management)
- [Tool Discovery & Testing](#tool-discovery--testing)
- [OAuth Authentication](#oauth-authentication)
- [Monitoring & Logs](#monitoring--logs)
- [Facility-Aware Logging](#facility-aware-logging)

## Global Options

Available for all commands:

```bash
foxxy-bridge [OPTIONS] COMMAND [ARGS]...
```

| Option | Description |
|--------|-------------|
| `-C, --config-dir PATH` | Configuration directory path (default: `~/.config/foxxy-bridge/`) |
| `-c, --config PATH` | Configuration file path (env: `FOXXY_BRIDGE_CONFIG`) |
| `-d, --debug` | Enable debug logging |
| `--no-color` | Disable colored output |
| `-v, --version` | Show version and exit |
| `-h, --help` | Show help message |

## Server Management

### Start Bridge Server

```bash
foxxy-bridge server start [OPTIONS]
```

**Options:**

- `--port INTEGER` - Server port (default: 8080)
- `--host TEXT` - Server host (default: 127.0.0.1)
- `--config PATH` - Configuration file path
- `--daemon` - Run as background daemon
- `--log-level [debug|info|warning|error]` - Logging level

**Examples:**

```bash
# Start server on default port
foxxy-bridge server start

# Start on custom port with specific config
foxxy-bridge server start --port 9000 --config ./prod-config.json

# Start as daemon with debug logging
foxxy-bridge server start --daemon --log-level debug
```

### Stop Bridge Server

```bash
foxxy-bridge server stop [OPTIONS]
```

**Options:**

- `--force` - Force stop without graceful shutdown

### List Running Instances

```bash
foxxy-bridge server list
```

Shows all running bridge daemon instances with their status.

### Server Status

```bash
foxxy-bridge server server-status [SERVER]
```

**Options:**

- `--format [table|json]` - Output format
- `--watch, -w` - Watch for status changes

### Restart Server

```bash
foxxy-bridge server server-restart SERVER [OPTIONS]
```

**Options:**

- `--force` - Force restart without graceful shutdown

## MCP Server Management

### Add MCP Server

```bash
foxxy-bridge mcp add NAME COMMAND [ARGS...] [OPTIONS]
```

**Options:**

- `--transport [stdio|sse|http]` - Transport type (default: stdio)
- `--url URL` - Server URL (required for SSE/HTTP)
- `--env KEY VALUE` - Environment variables (repeatable)
- `--cwd PATH` - Working directory
- `--tags TAG [TAG...]` - Server tags for grouping
- `--oauth` - Enable OAuth authentication
- `--oauth-issuer URL` - OAuth issuer URL
- `--timeout INTEGER` - Connection timeout in seconds
- `--retry-attempts INTEGER` - Number of retry attempts
- `--retry-delay FLOAT` - Delay between retries
- `--health-check` - Enable health checking
- `--tool-namespace TEXT` - Tool namespace prefix
- `--resource-namespace TEXT` - Resource namespace prefix
- `--priority INTEGER` - Server priority
- `--log-level [debug|info|warning|error]` - Server log level
- `--headers KEY VALUE` - HTTP headers (for HTTP/SSE transports)
- `--read-only` - Enable read-only mode
- `--allow-patterns TEXT` - Tool allow patterns (repeatable)
- `--block-patterns TEXT` - Tool block patterns (repeatable)
- `--allow-tools TEXT` - Allowed tools (repeatable)
- `--block-tools TEXT` - Blocked tools (repeatable)
- `--classify-tools TOOL TYPE` - Tool classifications (repeatable)

**Examples:**

```bash
# Add basic stdio server
foxxy-bridge mcp add github "npx" "-y" "@modelcontextprotocol/server-github" \
  --env GITHUB_TOKEN "${GITHUB_TOKEN}" \
  --tags development git

# Add SSE server with OAuth
foxxy-bridge mcp add remote-api "https://api.example.com/mcp" \
  --transport sse \
  --oauth \
  --oauth-issuer "https://auth.example.com" \
  --tags production remote

# Add server with security restrictions
foxxy-bridge mcp add restricted-fs "npx" "-y" "@modelcontextprotocol/server-filesystem" \
  --read-only \
  --allow-patterns "read_*" "list_*" \
  --block-patterns "delete_*" "remove_*"
```

### List MCP Servers

```bash
foxxy-bridge mcp mcp-list [OPTIONS]
```

**Options:**

- `--format [table|json|yaml]` - Output format

### Show Server Details

```bash
foxxy-bridge mcp mcp-show [NAME] [OPTIONS]
```

**Options:**

- `--format [json|yaml]` - Output format

If no name provided, shows all servers.

### Remove MCP Server

```bash
foxxy-bridge mcp remove NAME [OPTIONS]
```

**Options:**

- `--force` - Remove without confirmation

### Enable/Disable Server

```bash
foxxy-bridge mcp enable NAME
foxxy-bridge mcp disable NAME
```

### Restart MCP Server

```bash
foxxy-bridge mcp mcp-restart SERVER
```

Forces reconnection to the specified MCP server.

### View Server Logs

```bash
foxxy-bridge mcp logs SERVER [OPTIONS]
```

**Options:**

- `--follow, -f` - Follow log output
- `--lines, -n INTEGER` - Number of lines to show (default: 50)
- `--level [debug|info|warning|error]` - Filter by log level

## Configuration Management

### Initialize Configuration

```bash
foxxy-bridge config init [OPTIONS]
```

**Options:**

- `--force` - Overwrite existing configuration

Creates a default configuration with schema reference and sample MCP server.

### Show Configuration

```bash
foxxy-bridge config config-show [OPTIONS]
```

**Options:**

- `--format [json|yaml]` - Output format (default: yaml)

### Validate Configuration

```bash
foxxy-bridge config validate [OPTIONS]
```

**Options:**

- `--fix` - Attempt to fix validation issues

### Get/Set Configuration Values

```bash
foxxy-bridge config get-value KEY
foxxy-bridge config set-value KEY VALUE
foxxy-bridge config unset-value KEY
```

**Examples:**

```bash
# Get bridge port
foxxy-bridge config get-value bridge.port

# Set bridge host
foxxy-bridge config set-value bridge.host "0.0.0.0"

# Remove configuration key
foxxy-bridge config unset-value bridge.oauth_port
```

### Security Configuration

```bash
foxxy-bridge config security show [OPTIONS]
foxxy-bridge config security set KEY VALUE
foxxy-bridge config security allow-tool TOOL_NAME
foxxy-bridge config security block-tool TOOL_NAME
foxxy-bridge config security classify-tool TOOL [read|write|unknown]
```

**Options for show:**

- `--format [json|yaml]` - Output format

**Examples:**

```bash
# Show security settings
foxxy-bridge config security show

# Set read-only mode
foxxy-bridge config security set read_only_mode true

# Allow specific tool
foxxy-bridge config security allow-tool file_read

# Classify tool as read-only
foxxy-bridge config security classify-tool user_info read
```

## Tool Discovery & Testing

### List Tools

```bash
foxxy-bridge tool tool-list [SERVER] [OPTIONS]
```

**Options:**

- `--format [table|json]` - Output format
- `--tag TAG` - Filter by server tag

**Examples:**

```bash
# List all tools
foxxy-bridge tool tool-list

# List tools from specific server
foxxy-bridge tool tool-list github

# List tools by tag
foxxy-bridge tool tool-list --tag development
```

## OAuth Authentication

### OAuth Login

```bash
foxxy-bridge oauth login SERVER [OPTIONS]
```

Initiates OAuth authentication flow for a specific server.

**Options:**

- `--force` - Force re-authentication even if tokens exist

**Examples:**

```bash
# Initiate OAuth flow
foxxy-bridge oauth login production-api

# Force re-authentication
foxxy-bridge oauth login production-api --force
```

### OAuth Logout

```bash
foxxy-bridge oauth logout SERVER [OPTIONS]
```

Clears stored OAuth tokens for a specific server.

**Options:**

- `--confirm` - Skip confirmation prompt

**Examples:**

```bash
# Clear tokens for a server
foxxy-bridge oauth logout staging-api

# Clear without confirmation
foxxy-bridge oauth logout staging-api --confirm
```

### OAuth Status

```bash
foxxy-bridge oauth status [SERVER] [OPTIONS]
```

**Options:**

- `--format [table|json]` - Output format
- `--detailed` - Show additional token information

Shows OAuth authentication status for servers with OAuth enabled.

**Examples:**

```bash
# Show all OAuth statuses
foxxy-bridge oauth status

# Show status for specific server
foxxy-bridge oauth status remote-api

# Detailed status in JSON format
foxxy-bridge oauth status --format json --detailed
```

**Output Example:**

```
╭─────────────┬──────────────┬─────────────────────╮
│ Server      │ OAuth Status │ Token Expiry        │
├─────────────┼──────────────┼─────────────────────┤
│ production  │ ✓ Valid      │ 2024-01-15 14:30:00 │
│ staging     │ ⚠ Expired    │ 2024-01-10 10:15:00 │
│ development │ ✗ No tokens  │ -                   │
╰─────────────┴──────────────┴─────────────────────╯
```

## Monitoring & Logs

### MCP Server Logs

```bash
foxxy-bridge mcp logs SERVER [OPTIONS]
```

**Options:**

- `--follow, -f` - Follow log output
- `--lines, -n INTEGER` - Number of lines to show
- `--level [debug|info|warning|error]` - Filter by log level

**Examples:**

```bash
# View last 50 lines
foxxy-bridge mcp logs github

# Follow logs with debug level
foxxy-bridge mcp logs github --follow --level debug

# Show last 100 lines
foxxy-bridge mcp logs filesystem --lines 100
```

## Facility-Aware Logging

The CLI uses color-coded facility logging for better operational visibility:

| Facility | Color | Purpose |
|----------|--------|---------|
| `[BRIDGE]` | Blue | Bridge server operations |
| `[OAUTH]` | Orange | OAuth authentication flows |
| `[SERVER]` | Magenta | MCP server operations |

**Example Output:**

```bash
[BRIDGE] Starting bridge server on 127.0.0.1:8080
[BRIDGE] Loaded configuration from /home/user/.config/foxxy-bridge/config.json
[SERVER] Connected to MCP server 'github'
[OAUTH] Initiating OAuth flow for server 'remote-api'
[OAUTH] Authentication successful for server 'remote-api'
[SERVER] Health check passed for 'filesystem'
```

**Disable Colors:**

```bash
foxxy-bridge --no-color server start
```

## Exit Codes

- `0` - Success
- `1` - General error
- `2` - Configuration error
- `3` - Authentication error
- `4` - Server connection error

## Environment Variables

| Variable | Description |
|----------|-------------|
| `FOXXY_BRIDGE_CONFIG` | Default configuration file path |
| `FOXXY_BRIDGE_CONFIG_DIR` | Default configuration directory |
| `FOXXY_BRIDGE_LOG_LEVEL` | Default log level (debug, info, warning, error) |
| `FOXXY_BRIDGE_NO_COLOR` | Disable colored output (any value) |

## Configuration File Location

Default locations (in order of precedence):
1. `--config` CLI argument
2. `FOXXY_BRIDGE_CONFIG` environment variable
3. `~/.config/foxxy-bridge/config.json`
4. `./config.json` (current directory)
