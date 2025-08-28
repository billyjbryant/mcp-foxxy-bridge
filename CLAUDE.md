# CLAUDE.md

This file provides comprehensive guidance to Claude Code (claude.ai/code) when working with this repository. It serves as a development reference for AI assistants working on MCP Foxxy Bridge.

## 📋 Quick Reference

**🚀 Common Tasks:**
- Setup: `uv sync`
- Run: `uv run mcp-foxxy-bridge --bridge-config config.json`
- Test: `pytest`
- Lint: `ruff check --fix && mypy src/`
- Format: `ruff format`

**🔒 Security Testing:**
- Enable command substitution: `--allow-command-substitution`
- ⚠️ **NEVER** use `--allow-dangerous-commands` in production

## Development Commands

**Dependencies:**
```bash
uv sync                    # Install development dependencies
```

**Running the application:**
```bash
uv run foxxy-bridge --bridge-config config.json       # Primary command
uv run mcp-foxxy-bridge --bridge-config config.json   # Backward compatible alias
uv run -m mcp_foxxy_bridge                            # Run as module (legacy)
```

**Testing:**
```bash
pytest                     # Run all tests
pytest -v                  # Run with verbose output
pytest tests/test_config_loader.py  # Run specific test file
coverage run -m pytest     # Run tests with coverage
coverage report            # Show coverage report
```

**Code Quality:**
```bash
ruff check                 # Lint code
ruff format               # Format code
ruff check --fix          # Auto-fix issues
mypy src/                 # Type checking
```

**Development mode:**
```bash
uv run foxxy-bridge --bridge-config config.json --debug  # Run with debug logging

# Security features
uv run foxxy-bridge --bridge-config config.json --allow-command-substitution  # Enable command substitution
uv run foxxy-bridge --bridge-config config.json --allow-dangerous-commands   # UNSAFE: Allow any command (testing only)
```

**REST API Endpoints:**
```bash
# Server discovery and status
curl http://localhost:9000/status                           # Global bridge status and health
curl http://localhost:9000/sse/servers                      # List all available servers
curl http://localhost:9000/sse/tags                         # List all available tags and servers
curl http://localhost:9000/sse/mcp/filesystem/status        # Individual server status and health

# Tool discovery and listing
curl http://localhost:9000/sse/list_tools                    # List all tools from all servers
curl http://localhost:9000/sse/mcp/filesystem/list_tools     # List tools for specific server
curl http://localhost:9000/sse/tag/development/list_tools    # List tools by single tag
curl http://localhost:9000/sse/tag/dev+local/list_tools      # List tools by intersection (AND)
curl http://localhost:9000/sse/tag/web,api/list_tools        # List tools by union (OR)

# Server management
curl -X POST http://localhost:9000/sse/mcp/filesystem/reconnect  # Force server reconnection
curl -X POST http://localhost:9000/sse/tools/rescan             # Refresh all server capabilities

# OAuth status (for servers with OAuth enabled)
curl http://localhost:9000/oauth/filesystem/status          # OAuth authentication status
```

## Architecture Overview

MCP Foxxy Bridge is a one-to-many proxy for the Model Context Protocol (MCP) that aggregates multiple MCP servers through a single endpoint.

**Core Components:**
- `mcp_server.py` - HTTP/SSE server providing client endpoints
- `bridge_server.py` - MCP protocol implementation and tool aggregation
- `server_manager.py` - Backend MCP server lifecycle and connection management
- `config_loader.py` - Configuration parsing with environment variable expansion and security validation
- `sse_client_wrapper.py` - OAuth-aware SSE client with automatic authentication
- `oauth/` - OAuth 2.0 + PKCE authentication implementation

**Key Architecture Patterns:**
- Uses `AsyncExitStack` for managing async context lifecycles
- Implements namespacing to prevent tool/resource conflicts between servers
- Provides fault tolerance with automatic retry and failover
- Maintains server health monitoring with exponential backoff
- Implements comprehensive security validation for command substitution
- Provides OAuth 2.0 + PKCE authentication with automatic token management

**Request Flow:**
1. Client connects to SSE endpoint (`/sse`)
2. Bridge Server aggregates capabilities from all configured MCP servers
3. Tool calls are routed to appropriate backend server via Server Manager
4. Responses are forwarded back through the bridge to the client

**Configuration:**
- Uses JSON configuration files with `${VAR_NAME}` environment variable expansion and `$(command)` command substitution
- Supports both named servers and default server configurations
- Bridge configuration includes conflict resolution strategies and failover settings
- Enhanced health checking with configurable operations and automatic restart
- Comprehensive security controls for command substitution with allow-lists and validation
- OAuth configuration with automatic issuer discovery and secure token storage

**Health Check System:**
- Configurable health check operations: `list_tools`, `list_resources`, `list_prompts`, `call_tool`, `read_resource`, `get_prompt`, `ping`, `health`, `status`
- Keep-alive functionality with separate intervals and timeouts
- Automatic server restart on failure with configurable retry limits
- Operation-specific validation against server capabilities

**Server States:** CONNECTING → CONNECTED → FAILED/DISCONNECTED/DISABLED

## Testing Approach

- Uses `pytest` with `pytest-asyncio` for async testing
- Place tests in `tests/` directory
- Mock external dependencies appropriately
- Tests use `asyncio_mode = "auto"` for async fixtures

## Configuration Files

The bridge expects a JSON configuration file (default: `config.json`) defining:
- `servers` - Map of server name to configuration
- Bridge settings like conflict resolution and namespacing
- Environment variables are expanded using `${VAR_NAME}` syntax

Example minimal config structure:
```json
{
  "servers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "./"]
    }
  }
}
```

Example with security features:
```json
{
  "servers": {
    "secure-app": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "$(op read op://Private/GitHub/token)"
      },
      "oauth": {
        "enabled": true,
        "issuer": "https://auth.atlassian.com",
        "verify_ssl": true  // Default: true for security
      }
    },
    "dev-app": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-dev"],
      "oauth": {
        "enabled": true,
        "issuer": "https://dev.local:8443",
        "verify_ssl": false  // Only for development with self-signed certificates
      }
    }
  },
  "bridge": {
    "allow_command_substitution": true,
    "allowed_commands": ["op", "vault"],
    "oauth_port": 8090
  }
}
```

## Testing Configuration

- Use port 9090 for testing in the future

## Future Improvements

### v1.5.0 Release - Process Isolation (chroot)
Investigate implementing chroot-based isolation for each MCP server to provide execution isolation between servers:

**Security Benefits:**
- Each MCP server runs in its own isolated file system environment
- Prevents servers from accessing files outside their designated directory tree
- Reduces attack surface if one server is compromised
- Adds defense-in-depth security layer

**Implementation Considerations:**
- Research chroot setup requirements and limitations on different platforms
- Investigate alternative isolation mechanisms (containers, namespaces) for cross-platform support
- Design configuration schema for per-server chroot directories
- Evaluate impact on existing functionality (file system access, environment variables)
- Consider privilege requirements and security implications
- Plan migration path for existing configurations

**Technical Requirements:**
- Platform-specific chroot implementation (Linux/macOS/Windows alternatives)
- Configuration validation for chroot paths
- Error handling for chroot setup failures
- Documentation for security administrators
- Testing framework for isolated execution scenarios

**Priority:** High - Security enhancement for production deployments
**Complexity:** High - Requires OS-level integration and comprehensive testing

### Authentication Migration to mcp-auth
The current custom OAuth 2.0 implementation should be migrated to use the standardized `mcp-auth` library for better standards compliance and cleaner code organization:

**Current Status:**
- Custom OAuth 2.0 + PKCE implementation working correctly
- Manual token storage and state management
- Browser-based authentication flows functional

**Migration Plan:**
1. **Phase 1**: Adopt mcp-auth for server-side authentication (protecting bridge endpoints)
2. **Phase 2**: Replace custom OAuth client code with mcp-auth patterns
3. **Phase 3**: Standardize token storage using context variables instead of global state

**Benefits of Migration:**
- OAuth 2.1 standards compliance (RFC 9728)
- Provider-agnostic authentication
- Cleaner architecture with `TokenVerifier` protocol
- Automatic metadata discovery via well-known endpoints
- Reduced boilerplate code

**Resources:**
- mcp-auth library: https://github.com/mcp-auth/python
- Documentation: https://mcp-auth.dev/docs

## Development Warnings

- When running the bridge, always specify a timeout or background the task, otherwise you get stuck and never continue planning
- │ # Don't put emojis into log messages our logging module handles that for us                                                                                               │
