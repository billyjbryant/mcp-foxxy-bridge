# Configuration Guide

This guide covers how to configure MCP Foxxy Bridge for your use case, from basic setups to advanced production deployments.

## Quick Start

**👀 Want to jump straight to examples?** Check out our [Example Configurations](examples/README.md) for ready-to-use config files.

**🔐 Setting up authentication?** See the [OAuth Guide](oauth.md) for SSE/HTTP servers.

**🛡️ Security concerns?** Review the [Security Guide](security.md) for best practices.

## Configuration Overview

MCP Foxxy Bridge uses JSON configuration files with two main sections:

```json
{
  "mcpServers": {           // 🔌 Define your MCP servers here
    "github": { /* ... */ },
    "filesystem": { /* ... */ }
  },
  "bridge": {               // ⚙️ Bridge-wide settings
    "host": "127.0.0.1",
    "port": 8080
  }
}
```

### Configuration Methods

**🎯 Preferred Method - CLI Management:**
```bash
# Initialize configuration
foxxy-bridge config init

# Add servers via CLI
foxxy-bridge mcp add github "npx" "-y" "@modelcontextprotocol/server-github"

# Modify settings
foxxy-bridge config set-value bridge.port 9000
```

**📄 Legacy Method - Direct Config File:**
```bash
# Run with config file (still supported)
mcp-foxxy-bridge --bridge-config config.json
```

## Quick CLI Configuration

**🚀 The easiest way to configure MCP Foxxy Bridge:**

```bash
# 1. Initialize default configuration
foxxy-bridge config init

# 2. Add your first server
foxxy-bridge mcp add github "npx" "-y" "@modelcontextprotocol/server-github" \
  --env GITHUB_TOKEN "${GITHUB_TOKEN}" \
  --tags development git

# 3. View your configuration
foxxy-bridge config config-show

# 4. Start the bridge
foxxy-bridge server start
```

**🔧 Common CLI Configuration Tasks:**

```bash
# List all servers
foxxy-bridge mcp mcp-list

# Add filesystem server
foxxy-bridge mcp add filesystem "npx" "-y" "@modelcontextprotocol/server-filesystem" "./"

# Change bridge port
foxxy-bridge config set-value bridge.port 9000

# View specific configuration value
foxxy-bridge config get-value bridge.host

# Validate your configuration
foxxy-bridge config validate

# Show server details
foxxy-bridge mcp mcp-show github
```

## Server Configuration

Each MCP server in the `mcpServers` object has these options:

### Basic Settings

```json
{
  "enabled": true,                    // Whether to start this server
  "command": "npx",                   // Command to run
  "args": ["-y", "@modelcontextprotocol/server-github"],  // Arguments
  "timeout": 60,                      // Connection timeout (seconds)
  "transportType": "stdio"            // Always "stdio"
}
```

### Environment Variables

```json
{
  "env": {
    "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}",
    "API_URL": "${API_URL:https://api.github.com}",  // With default
    "DEBUG": "${DEBUG_MODE:false}"
  }
}
```

Environment variable syntax:

- `${VAR_NAME}` - Use environment variable value
- `${VAR_NAME:default}` - Use value or default if not set

### Namespacing

```json
{
  "toolNamespace": "github",          // Prefix for tools (github.search_repositories)
  "resourceNamespace": "gh",          // Prefix for resources
  "promptNamespace": "github"         // Prefix for prompts
}
```

### Reliability Settings

```json
{
  "retryAttempts": 3,                 // Connection retry attempts
  "retryDelay": 1000,                 // Delay between retries (ms)
  "priority": 100,                    // Server priority (lower = higher priority)
  "healthCheck": {
    "enabled": true,                  // Enable health monitoring
    "interval": 30000,                // Check interval (ms)
    "timeout": 5000                   // Health check timeout (ms)
  }
}
```

### Metadata

```json
{
  "tags": ["github", "git", "version-control"]  // Tags for organization
}
```

### OAuth Configuration (SSE/HTTP Only)

OAuth is only used for remote network-based MCP servers (SSE or HTTP streaming), not for local command-based servers.

```json
{
  "url": "https://mcp.example.com/sse",      // Remote MCP server URL (required for OAuth)
  "transport": "sse",                        // Must be "sse" or "streamablehttp"
  "oauth": {
    "enabled": true,                         // Enable OAuth 2.0 authentication
    "issuer": "https://auth.example.com",    // OAuth issuer URL (optional - auto-discovered if not provided)
    "client_name": "MCP Bridge Client",      // OAuth client name
    "client_uri": "https://your-app.com",    // OAuth client URI
    "verify_ssl": true,                      // Verify SSL certificates (default: true)
    "scopes": ["read:data"]                  // Optional: specific OAuth scopes (auto-discovered if not provided)
  }
}
```

**Important**: OAuth configuration requires:
- `"url"` field instead of `"command"`/`"args"`
- `"transport"` field set to `"sse"` or `"streamablehttp"`

OAuth authentication features:
- **Dynamic discovery**: Bridge attempts discovery on multiple endpoints (server URL and base URL)
- **Preflight checks**: Validates OAuth configuration before starting, providing immediate error feedback
- **PKCE support**: Uses Proof Key for Code Exchange for enhanced security
- **Token management**: Automatic token storage and refresh
- **Browser-based flow**: Opens browser for user authentication
- **SSL verification**: Configurable SSL certificate verification (secure by default)
- **HTTP/2 support**: Automatic HTTP/2 usage when available for better performance
- **CLI commands**: Built-in `login`, `logout`, and `status` commands for OAuth management
- **Transport awareness**: Differentiates between SSE and HTTP streaming OAuth requirements
- **No hardcoded scopes**: Scopes are dynamically determined from server requirements

## Bridge Configuration

The `bridge` section controls bridge-wide behavior:

```json
{
  "bridge": {
    "host": "127.0.0.1",               // Host to bind to (default: localhost)
    "port": 8080,                      // Port to bind to (default: 8080)
    "oauth_port": 8090,                // OAuth callback port (independent of bridge port)
    "conflictResolution": "namespace",  // How to handle tool name conflicts
    "defaultNamespace": true,           // Use server name as default namespace
    "allow_command_substitution": false, // Enable command substitution like $(op read ...)
    "allowed_commands": [               // Whitelist of allowed commands (optional)
      "op", "vault", "git", "echo"
    ],
    "allow_dangerous_commands": false,  // UNSAFE: Allow ANY command without validation
    "aggregation": {
      "tools": true,                    // Aggregate tools from all servers
      "resources": true,                // Aggregate resources
      "prompts": true                   // Aggregate prompts
    },
    "failover": {
      "enabled": true,                  // Enable automatic failover
      "maxFailures": 3,                 // Max failures before failed
      "recoveryInterval": 60000         // Time before retry (ms)
    }
  }
}
```

### Network Configuration

- `"host"`: Interface to bind to (default: `"127.0.0.1"` for localhost-only access)
  - Use `"127.0.0.1"` for local-only access (recommended for security)
  - Use `"0.0.0.0"` to allow external connections (requires careful firewall setup)
- `"port"`: TCP port to bind to (default: `8080`)

**Security Note**: The default configuration binds only to localhost (`127.0.0.1`) for security. Only change this if you need external access and have proper security measures in place.

### Security Configuration

The bridge includes comprehensive security features to protect against command injection and unauthorized access:

#### Command Substitution Security

- `"allow_command_substitution"`: Enable command substitution like `$(op read secret)` in config files
- `"allowed_commands"`: Whitelist of commands allowed for substitution (if not specified, uses safe defaults)
- `"allow_dangerous_commands"`: **⚠️ UNSAFE** - Bypasses all security validation (testing only!)

**Default allowed commands** (when `allowed_commands` is not specified):
```json
[
  "echo", "printf", "env", "printenv", "pwd", "uname", "date", "whoami",
  "op", "vault", "base64", "jq", "git", "gh", "grep", "cat", "head", "tail", "curl", "wget"
]
```

**Command validation includes:**
- Allow-list enforcement for command names
- Shell injection protection (blocks operators like `|`, `&`, `;`, etc.)
- Argument validation for sensitive commands (`git`, `vault`, `op`, `gh`)
- Read-only operation enforcement (prevents write/delete operations)

**Environment variables for security control:**
- `MCP_ALLOW_COMMAND_SUBSTITUTION=true` - Enable command substitution
- `MCP_ALLOWED_COMMANDS=git,op,vault` - Additional allowed commands (comma-separated)
- `MCP_ALLOW_DANGEROUS_COMMANDS=true` - **⚠️ UNSAFE** - Disable all validation

#### OAuth Security

- OAuth 2.0 with PKCE (Proof Key for Code Exchange) for enhanced security
- Automatic issuer discovery from server endpoints
- Secure token storage in local filesystem
- Browser-based authentication flow with automatic callback handling

### Conflict Resolution Options

- `"namespace"` - Use namespaces to avoid conflicts (recommended)
- `"priority"` - Higher priority server wins
- `"first"` - First server to provide the tool wins
- `"error"` - Throw error on conflicts

## Example Configurations

### Minimal Configuration

```json
{
  "mcpServers": {
    "filesystem": {
      "enabled": true,
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    }
  },
  "bridge": {
    "conflictResolution": "namespace"
  }
}
```

### OAuth-Enabled Configuration (Remote MCP Server)

```json
{
  "mcpServers": {
    "remote-mcp": {
      "enabled": true,
      "timeout": 60,
      "url": "https://mcp.company.com/sse",
      "transport": "sse",
      "oauth": {
        "enabled": true,
        // Issuer is optional - will be auto-discovered from the server URL
        // "issuer": "https://auth.company.com",
        "verify_ssl": true  // Verify SSL certificates (default: true)
      },
      "toolNamespace": "remote",
      "priority": 100,
      "tags": ["remote", "oauth", "enterprise"]
    },
    "development-server": {
      "enabled": true,
      "url": "https://dev.example.com/sse",
      "transport": "sse",
      "oauth": {
        "enabled": true,
        "issuer": "https://dev-auth.example.com",
        "verify_ssl": false  // Only for development with self-signed certificates
      },
      "toolNamespace": "dev",
      "tags": ["development", "test"]
    }
  },
  "bridge": {
    "host": "127.0.0.1",
    "port": 8080,
    "oauth_port": 8090,
    "conflictResolution": "namespace"
  }
}
```

### Command Substitution Configuration

```json
{
  "mcpServers": {
    "secrets": {
      "enabled": true,
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/app/data"],
      "env": {
        "API_KEY": "$(op read op://vault/item/credential)",
        "DATABASE_URL": "$(vault kv get -field=url secret/db)",
        "GITHUB_TOKEN": "${GITHUB_TOKEN}"
      },
      "toolNamespace": "secrets"
    }
  },
  "bridge": {
    "allow_command_substitution": true,
    "allowed_commands": ["op", "vault", "git"],
    "conflictResolution": "namespace"
  }
}
```

### Production Configuration

```json
{
  "mcpServers": {
    "fetch": {
      "enabled": true,
      "timeout": 60,
      "command": "uvx",
      "args": ["mcp-server-fetch"],
      "retryAttempts": 3,
      "retryDelay": 1000,
      "healthCheck": {
        "enabled": true,
        "interval": 30000,
        "timeout": 5000
      },
      "toolNamespace": "fetch",
      "priority": 100,
      "tags": ["web", "http", "fetch"]
    },
    "github": {
      "enabled": true,
      "timeout": 60,
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"
      },
      "retryAttempts": 3,
      "retryDelay": 1000,
      "healthCheck": {
        "enabled": true,
        "interval": 30000,
        "timeout": 5000
      },
      "toolNamespace": "github",
      "priority": 100,
      "tags": ["github", "git", "version-control"]
    },
    "filesystem": {
      "enabled": true,
      "timeout": 30,
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/app/data"],
      "retryAttempts": 2,
      "retryDelay": 500,
      "healthCheck": {
        "enabled": true,
        "interval": 45000,
        "timeout": 3000
      },
      "toolNamespace": "fs",
      "resourceNamespace": "fs",
      "priority": 50,
      "tags": ["filesystem", "files", "local"]
    }
  },
  "bridge": {
    "host": "127.0.0.1",
    "port": 8080,
    "conflictResolution": "namespace",
    "defaultNamespace": true,
    "aggregation": {
      "tools": true,
      "resources": true,
      "prompts": true
    },
    "failover": {
      "enabled": true,
      "maxFailures": 3,
      "recoveryInterval": 60000
    }
  }
}
```

## Command Line Options

Override configuration with command-line arguments:

```bash
# Basic usage
mcp-foxxy-bridge --bridge-config config.json

# Custom port and host (overrides config file settings)
mcp-foxxy-bridge --bridge-config config.json --port 8081 --host 0.0.0.0

# Debug mode
mcp-foxxy-bridge --bridge-config config.json --debug

# Enable command substitution (security feature)
mcp-foxxy-bridge --bridge-config config.json --allow-command-substitution

# UNSAFE: Allow dangerous commands (testing only!)
mcp-foxxy-bridge --bridge-config config.json --allow-dangerous-commands

# Pass environment variables
GITHUB_TOKEN=abc123 mcp-foxxy-bridge --bridge-config config.json
```

**Configuration Priority** (highest to lowest):
1. Command-line arguments (`--host`, `--port`)
2. Configuration file bridge settings (`bridge.host`, `bridge.port`)
3. Default values (`127.0.0.1:8080`)

## Validation

The bridge validates configuration files on startup. Common validation errors:

- **Missing required fields**: Every server needs a `command`
- **Invalid JSON**: Syntax errors in the configuration file
- **Unknown fields**: Typos in field names
- **Invalid values**: Wrong types or out-of-range values

## Best Practices

1. **Use environment variables** for secrets instead of hardcoding them
2. **Set appropriate timeouts** based on your MCP servers' response times
3. **Enable health checks** for production deployments
4. **Use namespaces** to avoid tool name conflicts
5. **Set priorities** to control which server handles conflicts
6. **Tag your servers** for better organization
7. **Test configurations** with a single server first
8. **Keep SSL verification enabled** (default) for security - only disable for development with self-signed certificates
9. **Use HTTP/2** when available for better performance with OAuth-enabled servers

## Next Steps

- See [Deployment Guide](deployment.md) for running the configured bridge
- Check [Troubleshooting Guide](troubleshooting.md) for common issues
- Review [API Reference](api.md) for endpoint usage details
