# MCP Foxxy Bridge

<!-- BADGIE TIME -->

[![CI/CD Pipeline](https://img.shields.io/github/actions/workflow/status/billyjbryant/mcp-foxxy-bridge/main.yml?branch=main&logo=github&label=CI%2FCD&style=for-the-badge)](https://github.com/billyjbryant/mcp-foxxy-bridge/actions/workflows/main.yml)
[![Release Version](https://img.shields.io/github/v/release/billyjbryant/mcp-foxxy-bridge?logo=github&style=for-the-badge)](https://github.com/billyjbryant/mcp-foxxy-bridge/releases)
[![PyPI Version](https://img.shields.io/pypi/v/mcp-foxxy-bridge?logo=pypi&logoColor=white&style=for-the-badge)](https://pypi.org/project/mcp-foxxy-bridge/)
[![Code Coverage](https://img.shields.io/codecov/c/github/billyjbryant/mcp-foxxy-bridge?logo=codecov&style=for-the-badge)](https://codecov.io/gh/billyjbryant/mcp-foxxy-bridge)

[![Python Version](https://img.shields.io/pypi/pyversions/mcp-foxxy-bridge?logo=python&logoColor=white&style=for-the-badge)](https://pypi.org/project/mcp-foxxy-bridge/)
[![License](https://img.shields.io/badge/license-AGPL--3.0--or--later-blue?logo=gnu&style=for-the-badge)](https://github.com/billyjbryant/mcp-foxxy-bridge/blob/main/LICENSE)
[![Development Status](https://img.shields.io/pypi/status/mcp-foxxy-bridge?style=for-the-badge)](https://pypi.org/project/mcp-foxxy-bridge/)

[![PyPI Downloads](https://img.shields.io/pypi/dm/mcp-foxxy-bridge?logo=pypi&logoColor=white&style=for-the-badge)](https://pypi.org/project/mcp-foxxy-bridge/)
[![GitHub Stars](https://img.shields.io/github/stars/billyjbryant/mcp-foxxy-bridge?logo=github&style=for-the-badge)](https://github.com/billyjbryant/mcp-foxxy-bridge/stargazers)
[![GitHub Issues](https://img.shields.io/github/issues/billyjbryant/mcp-foxxy-bridge?logo=github&style=for-the-badge)](https://github.com/billyjbryant/mcp-foxxy-bridge/issues)
[![GitHub Forks](https://img.shields.io/github/forks/billyjbryant/mcp-foxxy-bridge?logo=github&style=for-the-badge)](https://github.com/billyjbryant/mcp-foxxy-bridge/network/members)

[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&style=for-the-badge)](https://github.com/pre-commit/pre-commit)
[![Documentation](https://img.shields.io/badge/docs-available-brightgreen?logo=gitbook&style=for-the-badge)](https://github.com/billyjbryant/mcp-foxxy-bridge/tree/main/docs)
[![MCP Protocol](https://img.shields.io/badge/MCP-Protocol-orange?logo=data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjQiIGhlaWdodD0iMjQiIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHBhdGggZD0iTTEyIDJMMTMuMDkgOC4yNkwyMCA5TDEzLjA5IDE1Ljc0TDEyIDIyTDEwLjkxIDE1Ljc0TDQgOUwxMC45MSA4LjI2TDEyIDJaIiBmaWxsPSJ3aGl0ZSIvPgo8L3N2Zz4K&style=for-the-badge)](https://modelcontextprotocol.io)
[![Uvicorn](https://img.shields.io/badge/server-Uvicorn-green?logo=uvicorn&style=for-the-badge)](https://www.uvicorn.org/)

<!-- END BADGIE TIME -->

<p align="center">
  <img src="media/mcp-foxxy-bridge_logo_trimmed.webp" alt="MCP Foxxy Bridge Logo" width="300">
</p>

## Overview

**MCP Foxxy Bridge** is a secure one-to-many proxy for the Model Context Protocol (MCP). Connect multiple MCP servers through a single endpoint with enterprise-grade security.

**Key Features:**
- Single endpoint for all MCP servers
- OAuth 2.0 + PKCE authentication
- Enhanced CLI with daemon management
- REST API for operational control
- Secure command substitution
- HTTP/2 support

---

## Quickstart

### Installation

```bash
# Install via uv (recommended)
uv tool install mcp-foxxy-bridge

# Or install from GitHub
uv tool install git+https://github.com/billyjbryant/mcp-foxxy-bridge
```

---

### Quick Setup

```bash
# Initialize configuration
foxxy-bridge config init

# Add MCP servers
foxxy-bridge mcp add github "npx -y @modelcontextprotocol/server-github"
foxxy-bridge mcp add filesystem "npx -y @modelcontextprotocol/server-filesystem" --path ./

# Start the bridge server
foxxy-bridge server start

# Check status
foxxy-bridge server status
```

---

### Connect Your AI Tool

Point your MCP-compatible client to: `http://localhost:8080/sse`

---

## CLI Commands

### Server Management
```bash
foxxy-bridge server start [--port 8080] [--host 127.0.0.1]
foxxy-bridge server stop
foxxy-bridge server restart
foxxy-bridge server status
foxxy-bridge server list
```

### MCP Server Configuration
```bash
foxxy-bridge mcp list                    # List all configured servers
foxxy-bridge mcp add <name> <command>    # Add new server
foxxy-bridge mcp remove <name>           # Remove server
foxxy-bridge mcp show <name>             # Show server details
foxxy-bridge mcp restart <name>          # Restart specific server
```

### Configuration Management
```bash
foxxy-bridge config init [--force]       # Initialize configuration
foxxy-bridge config validate             # Validate configuration
foxxy-bridge config get <key>            # Get configuration value
foxxy-bridge config set <key> <value>    # Set configuration value
foxxy-bridge config unset <key>          # Remove configuration key
```

### Tool Discovery
```bash
foxxy-bridge tool list [--server NAME]   # List available tools
foxxy-bridge tool list --tag development # Filter by tag
```

### Security & OAuth
```bash
foxxy-bridge security show               # Show security settings
foxxy-bridge security set <key> <value>  # Configure security
foxxy-bridge oauth status [SERVER]       # Check OAuth status
```

### Monitoring
```bash
foxxy-bridge logs [--follow] [--tail N]  # View bridge logs
```

## REST API Endpoints

**Status & Discovery:**
- `GET /status` - Bridge health and server status
- `GET /sse/servers` - List all configured servers
- `GET /sse/tags` - List all available tags
- `GET /sse/mcp/{server}/status` - Individual server status

**Tool Management:**
- `GET /sse/list_tools` - List all tools
- `GET /sse/mcp/{server}/list_tools` - Server-specific tools
- `GET /sse/tag/{tags}/list_tools` - Filter by tags (+ for AND, , for OR)
- `POST /sse/tools/rescan` - Refresh tool capabilities

**Server Control:**
- `POST /sse/mcp/{server}/reconnect` - Force reconnection
- `GET /oauth/{server}/status` - OAuth authentication status

## Documentation

**Getting Started:**
- [Installation Guide](docs/installation.md) - Detailed setup instructions
- [Configuration Guide](docs/configuration.md) - Configuration options
- [Example Configurations](docs/examples/README.md) - Ready-to-use configs

**Advanced Topics:**
- [Security Guide](docs/security.md) - Security best practices
- [OAuth Authentication](docs/oauth.md) - OAuth setup
- [API Reference](docs/api.md) - Complete API documentation
- [Architecture Overview](docs/architecture.md) - Technical details
- [Deployment Guide](docs/deployment.md) - Production deployment

**Support:**
- [Troubleshooting](docs/troubleshooting.md) - Common issues
- [Contributing](CONTRIBUTING.md) - Development guide

---

## Configuration Examples

**Basic Configuration:**
```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {"GITHUB_TOKEN": "${GITHUB_TOKEN}"},
      "toolNamespace": "github"
    }
  },
  "bridge": {
    "port": 8080,
    "conflictResolution": "namespace"
  }
}
```

**With OAuth (SSE/HTTP servers only):**
```json
{
  "mcpServers": {
    "remote-mcp": {
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

---

## Contributing & Support

- [Contributing Guide](CONTRIBUTING.md)
- [Issue Tracker](https://github.com/billyjbryant/mcp-foxxy-bridge/issues)
- [Discussions](https://github.com/billyjbryant/mcp-foxxy-bridge/discussions)

---

## License

AGPL-3.0-or-later - See [LICENSE](LICENSE) file for details.

---
