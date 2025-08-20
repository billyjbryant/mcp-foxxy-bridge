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
2. **Discovery**: Bridge auto-discovers OAuth endpoints from the server
3. **Authorization**: User authenticates via browser
4. **Token Exchange**: Bridge exchanges authorization code for tokens using PKCE
5. **Token Storage**: Tokens are stored securely for future use
6. **Auto-Refresh**: Tokens are automatically refreshed when needed

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
        "client_uri": "https://github.com/billyjbryant/mcp-foxxy-bridge"
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

*The `issuer` field is optional if the OAuth server supports dynamic registration and discovery.

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

The bridge can automatically discover OAuth configuration from the MCP server using standard mechanisms:

### Automatic Discovery

When connecting to a remote MCP server, the bridge attempts to discover OAuth endpoints:

1. **OpenID Connect Discovery**: `/.well-known/openid_configuration`
2. **OAuth Authorization Server Metadata**: `/.well-known/oauth-authorization-server`

The discovery is attempted on the base URL of the MCP server endpoint.

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
        "issuer": "https://auth.example.com"
      }
    }
  }
}
```

## Authentication Flow

### First-Time Setup

1. **Start Bridge**: Run with OAuth-enabled configuration
2. **Automatic Flow**: Bridge detects missing tokens and initiates OAuth flow
3. **Browser Opens**: Default browser opens to OAuth authorization page
4. **User Authentication**: User logs in and authorizes the application
5. **Callback Handling**: Bridge receives authorization code via callback
6. **Token Exchange**: Bridge exchanges code for access/refresh tokens using PKCE
7. **Token Storage**: Tokens are stored in `~/.foxxy-bridge/auth/`

### Subsequent Usage

- **Automatic**: Bridge automatically uses stored tokens
- **Refresh**: Tokens are refreshed automatically when needed
- **Re-authentication**: User is prompted if refresh fails

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
        "issuer": "https://auth.company.com"
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
        "client_name": "My MCP Bridge"
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
1. **Manual Configuration**:
   ```json
   {
     "oauth": {
       "enabled": true,
       "issuer": "https://oauth.yourservice.com"
     }
   }
   ```

2. **Check Discovery Endpoints**:
   ```bash
   curl https://yourservice.com/.well-known/openid_configuration
   curl https://yourservice.com/.well-known/oauth-authorization-server
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
INFO: OAuth-enabled server detected. Checking for existing OAuth tokens.
DEBUG: Trying OAuth discovery endpoint: https://auth.atlassian.com/.well-known/openid_configuration
INFO: Discovered OAuth issuer via https://auth.atlassian.com/.well-known/openid_configuration: https://auth.atlassian.com
INFO: 🌐 OAuth flow initiated for server 'atlassian'. Please check your browser to complete authorization.
INFO: OAuth flow completed successfully for server 'atlassian'
INFO: OAuth tokens loaded successfully for server URL hash: 123456789
```

**OAuth Errors**:
```
ERROR: OAuth discovery failed for all endpoints for server URL: https://mcp.example.com
WARNING: OAuth tokens missing for server 'example', initiating automatic flow
ERROR: OAuth callback failed: Token exchange error
```

## Security Considerations

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

## Advanced Configuration

### Custom OAuth Client Configuration

```json
{
  "oauth": {
    "enabled": true,
    "issuer": "https://oauth.mycompany.com",
    "client_name": "My Custom MCP Bridge",
    "client_uri": "https://mycompany.com/tools/mcp-bridge",
    "additional_params": {
      "audience": "https://api.mycompany.com",
      "resource": "myapp"
    }
  }
}
```

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

## Next Steps

- See [Security Guide](security.md) for OAuth security best practices
- Check [Configuration Guide](configuration.md) for complete configuration options
- Review [Troubleshooting Guide](troubleshooting.md) for common OAuth issues
