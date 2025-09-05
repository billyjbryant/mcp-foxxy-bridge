# OAuth Authentication Guide

This guide covers how to configure and use OAuth 2.0 authentication with MCP Foxxy Bridge.

## Overview

MCP Foxxy Bridge supports OAuth 2.0 authentication with PKCE (Proof Key for Code Exchange) to securely connect to **SSE and HTTP streaming MCP endpoints**. OAuth authentication is **only available for network-based MCP servers**, not for local stdio-based servers that are launched with commands.

This enables integration with remote services like:

- Remote MCP servers protected by OAuth
- Cloud-based MCP services
- Enterprise MCP deployments with authentication

## OAuth Flow Overview

1. **Configuration**: Define OAuth settings in your bridge config
2. **Discovery**: Bridge dynamically discovers OAuth endpoints from the server
3. **Preflight Check**: Bridge validates OAuth configuration before starting
4. **Authorization**: User authenticates via browser (automatic or CLI-initiated)
5. **Token Exchange**: Bridge exchanges authorization code for tokens using PKCE
6. **Token Storage**: Tokens are stored securely for future use
7. **Auto-Refresh**: Tokens are automatically refreshed when needed

## Configuration

OAuth is **only used with SSE and HTTP streaming endpoints**, not with local command-based servers.

### Basic OAuth Configuration

For connecting to a remote MCP server via SSE with OAuth:

```json
{
  "mcpServers": {
    "remote-mcp": {
      "enabled": true,
      "url": "https://mcp.example.com/sse",
      "transport": "sse",
      "oauth": {
        "enabled": true,
        "issuer": "https://auth.example.com",
        "client_name": "MCP Foxxy Bridge",
        "client_uri": "https://github.com/billyjbryant/mcp-foxxy-bridge",
        "verify_ssl": true  // Default: true for security
      },
      "toolNamespace": "remote"
    }
  },
  "bridge": {
    "oauth_port": 8090
  }
}
```

**Key Requirements:**
- Must specify `"url"` instead of `"command"/"args"`
- Must specify `"transport": "sse"` or `"transport": "streamablehttp"`
- OAuth configuration goes in the server config, not bridge config

### OAuth Configuration Options

| Field | Description | Required | Default |
|-------|-------------|----------|---------|
| `enabled` | Enable OAuth authentication | Yes | `false` |
| `issuer` | OAuth issuer URL | No* | Auto-discovered |
| `client_name` | OAuth client name | No | `"MCP Foxxy Bridge"` |
| `client_uri` | OAuth client URI | No | Bridge GitHub URL |
| `verify_ssl` | Verify SSL/TLS certificates | No | `true` |
| `scopes` | OAuth scopes to request | No | Server-defined |

*The `issuer` field is optional. The bridge will attempt to discover it dynamically from the server URL if not provided.

**Security Note**: The `verify_ssl` option controls SSL certificate verification. It is enabled by default for security. Only disable this for development environments with self-signed certificates.

### Bridge-Level OAuth Settings

```json
{
  "bridge": {
    "oauth_port": 8090,  // Dedicated OAuth callback port
    "host": "127.0.0.1"  // Callback host
  }
}
```

## OAuth Issuer Discovery

The bridge uses dynamic discovery to automatically find OAuth configuration from the MCP server:

### Automatic Discovery

When connecting to a remote MCP server, the bridge attempts discovery in this order:

1. **Server-Specific Discovery**: Checks the exact server URL first
   - `https://mcp.example.com/sse/.well-known/openid_configuration`
   - `https://mcp.example.com/sse/.well-known/oauth-authorization-server`

2. **Base URL Discovery**: Falls back to the base domain
   - `https://mcp.example.com/.well-known/openid_configuration`
   - `https://mcp.example.com/.well-known/oauth-authorization-server`

3. **Issuer Field**: Uses the configured `issuer` field if discovery fails

This dynamic approach ensures OAuth works with various server configurations without manual mapping.

### Manual Issuer Configuration

If auto-discovery fails or is not supported by the OAuth server, you can specify the issuer manually:

```json
{
  "mcpServers": {
    "remote-server": {
      "url": "https://mcp.example.com/sse",
      "transport": "sse",
      "oauth": {
        "enabled": true,
        "issuer": "https://auth.example.com",
        "verify_ssl": true  // Keep enabled for production
      }
    },
    "dev-server": {
      "url": "https://dev.example.com/sse",
      "transport": "sse",
      "oauth": {
        "enabled": true,
        "issuer": "https://dev-auth.example.com",
        "verify_ssl": false  // Only for development with self-signed certs
      }
    }
  }
}
```

## Authentication Flow

### First-Time Setup

1. **Start Bridge**: Run with OAuth-enabled configuration
2. **Preflight Check**: Bridge validates OAuth configuration immediately
3. **Automatic Flow**: Bridge detects missing tokens and initiates OAuth flow
4. **Browser Opens**: Default browser opens to OAuth authorization page
5. **User Authentication**: User logs in and authorizes the application
6. **Callback Handling**: Bridge receives authorization code via callback
7. **Token Exchange**: Bridge exchanges code for access/refresh tokens using PKCE
8. **Token Storage**: Tokens are stored in `~/.foxxy-bridge/auth/`

**Note**: OAuth errors are detected immediately during preflight checks, providing clear error messages before the bridge fully starts.

### Subsequent Usage

- **Automatic**: Bridge automatically uses stored tokens
- **Refresh**: Tokens are refreshed automatically when needed
- **Re-authentication**: User is prompted if refresh fails
- **CLI Management**: Use CLI commands to manage OAuth sessions:
  ```bash
  foxxy-bridge oauth login <server>     # Manually initiate OAuth flow
  foxxy-bridge oauth logout <server>    # Clear stored tokens
  foxxy-bridge oauth status [server]    # Check OAuth status
  ```

## Token Management

### Token Storage

Tokens are stored in the user's home directory:

```
~/.foxxy-bridge/auth/
├── server-hash-123456.json  # Tokens for specific server
└── server-hash-789012.json  # Tokens for another server
```

### Token File Format

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "refresh_token": "def50200...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "read:repositories",
  "created_at": 1640995200
}
```

### Token Security

- Files are created with restricted permissions (600)
- Tokens are never logged or exposed in error messages
- Storage location is configurable via config directory
- Scopes are dynamically determined from server requirements (no hardcoded scopes)
- OAuth differentiation between SSE and HTTP streaming transports

## Examples

### Remote MCP Server with OAuth

```json
{
  "mcpServers": {
    "enterprise-mcp": {
      "enabled": true,
      "url": "https://mcp.company.com/sse",
      "transport": "sse",
      "oauth": {
        "enabled": true,
        "issuer": "https://auth.company.com",
        "verify_ssl": true  // Default: secure SSL verification
      },
      "toolNamespace": "enterprise"
    }
  },
  "bridge": {
    "oauth_port": 8090,
    "conflictResolution": "namespace"
  }
}
```

### HTTP Streaming with OAuth

```json
{
  "mcpServers": {
    "cloud-mcp": {
      "enabled": true,
      "url": "https://api.example.com/mcp",
      "transport": "streamablehttp",
      "oauth": {
        "enabled": true,
        "issuer": "https://oauth.example.com",
        "client_name": "My MCP Bridge",
        "verify_ssl": true  // Always verify SSL in production
      },
      "toolNamespace": "cloud"
    }
  }
}
```

### Multiple OAuth Servers

```json
{
  "mcpServers": {
    "service-a": {
      "url": "https://mcp-a.example.com/sse",
      "transport": "sse",
      "oauth": {
        "enabled": true,
        "issuer": "https://auth-a.example.com"
      },
      "toolNamespace": "service-a"
    },
    "service-b": {
      "url": "https://mcp-b.example.com/mcp",
      "transport": "streamablehttp",
      "oauth": {
        "enabled": true,
        "issuer": "https://auth-b.example.com"
      },
      "toolNamespace": "service-b"
    },
    "local-service": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "./"],
      "toolNamespace": "local"
      // Note: No OAuth config - this is a local stdio server
    }
  },
  "bridge": {
    "oauth_port": 8090
  }
}
```

## Troubleshooting

### Common Issues

#### 1. Browser Doesn't Open

**Problem**: OAuth flow initiated but browser doesn't open automatically.

**Solutions**:
- Manually navigate to the URL shown in logs
- Check if running in headless environment
- Verify `DISPLAY` environment variable (Linux)

#### 2. Callback Port Issues

**Problem**: OAuth callback fails with connection errors.

**Solutions**:
```json
{
  "bridge": {
    "oauth_port": 8091  // Try different port
  }
}
```

Or check for port conflicts:
```bash
lsof -i :8090
netstat -tlnp | grep 8090
```

#### 3. Issuer Discovery Fails

**Problem**: Bridge cannot discover OAuth configuration.

**Solutions**:
1. **Check Discovery Attempts**: The bridge tries multiple discovery URLs:
   ```bash
   # Server-specific discovery
   curl https://mcp.example.com/sse/.well-known/openid_configuration
   curl https://mcp.example.com/sse/.well-known/oauth-authorization-server

   # Base URL discovery
   curl https://mcp.example.com/.well-known/openid_configuration
   curl https://mcp.example.com/.well-known/oauth-authorization-server
   ```

2. **Manual Configuration** (if discovery fails):
   ```json
   {
     "oauth": {
       "enabled": true,
       "issuer": "https://oauth.yourservice.com"
     }
   }
   ```

3. **Enable Debug Mode**: See all discovery attempts:
   ```bash
   foxxy-bridge --debug server start
   ```

#### 4. Token Refresh Fails

**Problem**: Stored tokens are invalid or expired.

**Solutions**:
1. **Delete stored tokens** (forces re-authentication):
   ```bash
   rm ~/.foxxy-bridge/auth/server-hash-*.json
   ```

2. **Check token permissions**:
   ```bash
   ls -la ~/.foxxy-bridge/auth/
   ```

#### 5. PKCE Verification Fails

**Problem**: OAuth server rejects PKCE verification.

**Solution**: Ensure OAuth server supports PKCE. Some older servers may not support it.

### Debug Mode

Enable debug logging for OAuth troubleshooting:

```bash
mcp-foxxy-bridge --bridge-config config.json --debug
```

Debug logs include:
- OAuth discovery attempts
- Token storage/retrieval operations
- Authorization flow progress
- Error details with context

### Log Messages

**Successful OAuth Flow**:
```
INFO: OAuth-enabled server detected. Running OAuth preflight check.
DEBUG: Attempting OAuth discovery for URL: https://mcp.example.com/sse
DEBUG: Trying discovery endpoint: https://mcp.example.com/sse/.well-known/openid_configuration
DEBUG: Trying discovery endpoint: https://mcp.example.com/.well-known/openid_configuration
INFO: Successfully discovered OAuth issuer: https://auth.example.com
INFO: OAuth preflight check passed for server 'example'
INFO: OAuth flow initiated for server 'example'. Please check your browser to complete authorization.
INFO: OAuth flow completed successfully for server 'example'
INFO: OAuth tokens loaded successfully for server URL hash: 123456789
```

**OAuth Errors (with immediate detection)**:
```
ERROR: OAuth preflight check failed for server 'example'
ERROR: OAuth discovery failed for all endpoints:
  - https://mcp.example.com/sse/.well-known/openid_configuration (404)
  - https://mcp.example.com/sse/.well-known/oauth-authorization-server (404)
  - https://mcp.example.com/.well-known/openid_configuration (404)
  - https://mcp.example.com/.well-known/oauth-authorization-server (404)
ERROR: No issuer configured and discovery failed for server 'example'
```

**CLI OAuth Management**:
```
$ foxxy-bridge oauth status
╭─────────────┬──────────────┬─────────────────────╮
│ Server      │ OAuth Status │ Token Expiry        │
├─────────────┼──────────────┼─────────────────────┤
│ production  │ ✓ Valid      │ 2024-01-15 14:30:00 │
│ staging     │ ⚠ Expired    │ 2024-01-10 10:15:00 │
│ development │ ✗ No tokens  │ -                   │
╰─────────────┴──────────────┴─────────────────────╯
```

## Security Considerations

### SSL/TLS Verification

The bridge provides configurable SSL certificate verification:
- **Default Behavior**: SSL verification is **enabled by default** for security
- **Development Mode**: Can be disabled with `"verify_ssl": false` for self-signed certificates
- **HTTP/2 Support**: Automatically uses HTTP/2 when available for improved performance
- **Security Headers**: Includes security headers in all HTTP requests

**⚠️ Warning**: Only disable SSL verification in development environments. Never disable it in production.

### PKCE Security

The bridge uses PKCE for enhanced security:
- **Code Challenge**: Generated using SHA256 hash
- **Code Verifier**: High-entropy random string
- **State Parameter**: Prevents CSRF attacks

### Token Security

- **Secure Storage**: Tokens stored with restricted file permissions
- **No Network Exposure**: Tokens never sent over unencrypted connections
- **Automatic Cleanup**: Expired tokens are removed automatically
- **Scope Limitation**: Only request necessary OAuth scopes

### Network Security

- **Localhost Callback**: OAuth callbacks only accepted on localhost
- **Port Restrictions**: OAuth port separate from main bridge port
- **HTTPS Validation**: OAuth endpoints must use HTTPS
- **SSL Verification**: Enabled by default with configurable override for development
- **HTTP/2 Support**: Automatic protocol upgrade for better performance
- **Connection Limits**: Built-in connection pooling and rate limiting

## Integration with MCP Servers

### Server Requirements

For an MCP server to work with OAuth:

1. **OAuth Support**: Server must support OAuth 2.0 authentication
2. **Token Headers**: Server must accept tokens via `Authorization: Bearer <token>` header
3. **Discovery Metadata**: Server should provide OAuth discovery endpoints (recommended)

### Creating OAuth-Compatible MCP Servers

When building MCP servers that support OAuth:

1. **Implement OAuth Discovery**:
   ```javascript
   app.get('/.well-known/openid_configuration', (req, res) => {
     res.json({
       issuer: 'https://your-oauth-server.com',
       authorization_endpoint: 'https://your-oauth-server.com/auth',
       token_endpoint: 'https://your-oauth-server.com/token',
       // ... other OAuth metadata
     });
   });
   ```

2. **Accept Bearer Tokens**:
   ```javascript
   app.use((req, res, next) => {
     const token = req.headers.authorization?.replace('Bearer ', '');
     if (token) {
       // Validate token and set user context
       req.user = validateToken(token);
     }
     next();
   });
   ```

3. **Support PKCE**: Ensure OAuth server supports PKCE for enhanced security

## CLI OAuth Commands

The bridge provides CLI commands for managing OAuth authentication:

### Login Command
```bash
# Initiate OAuth flow for a specific server
foxxy-bridge oauth login <server>

# Example
foxxy-bridge oauth login production-api
```

### Logout Command
```bash
# Clear stored tokens for a server
foxxy-bridge oauth logout <server>

# Example
foxxy-bridge oauth logout staging-api
```

### Status Command
```bash
# Check OAuth status for all servers
foxxy-bridge oauth status

# Check status for a specific server
foxxy-bridge oauth status production-api
```

## Advanced Configuration

### Custom OAuth Client Configuration

```json
{
  "oauth": {
    "enabled": true,
    "issuer": "https://oauth.mycompany.com",
    "client_name": "My Custom MCP Bridge",
    "client_uri": "https://mycompany.com/tools/mcp-bridge",
    "verify_ssl": true,  // Keep enabled for production
    "scopes": ["read:data", "write:data"],  // Optional: specific scopes
    "additional_params": {
      "audience": "https://api.mycompany.com",
      "resource": "myapp"
    }
  }
}
```

**Note**: Scopes are typically discovered dynamically from the server. Only specify them if you need specific scopes that differ from the server's defaults.

### Development with Self-Signed Certificates

For development environments using self-signed certificates:

```json
{
  "oauth": {
    "enabled": true,
    "issuer": "https://dev.local:8443",
    "verify_ssl": false  // ONLY for development
  }
}
```

**Note**: A warning will be logged when SSL verification is disabled to remind you this is insecure.

### Environment-Specific Configuration

**Development**:
```json
{
  "bridge": {
    "oauth_port": 8090,
    "host": "127.0.0.1"
  }
}
```

**Production** (with reverse proxy):
```json
{
  "bridge": {
    "oauth_port": 8090,
    "host": "127.0.0.1"  // Still localhost, proxy handles external access
  }
}
```

## Best Practices

1. **Use Namespaces**: Prevent tool conflicts when using multiple OAuth servers
2. **Monitor Token Expiration**: Set up monitoring for token refresh failures
3. **Rotate Tokens**: Regularly refresh OAuth tokens for security
4. **Secure Configuration**: Store OAuth configuration securely
5. **Audit Access**: Regularly audit OAuth token usage and access patterns
6. **Keep SSL Verification Enabled**: Only disable for development with self-signed certificates
7. **Use HTTP/2**: Leverage automatic HTTP/2 support for better performance
8. **Monitor SSL Warnings**: Pay attention to SSL verification warnings in logs

## Next Steps

- See [Security Guide](security.md) for OAuth security best practices
- Check [Configuration Guide](configuration.md) for complete configuration options
- Review [Troubleshooting Guide](troubleshooting.md) for common OAuth issues
