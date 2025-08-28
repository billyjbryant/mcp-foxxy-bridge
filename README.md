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

## Documentation

**📖 Getting Started:**

- **[Installation Guide](docs/installation.md)** - Detailed setup and configuration
- **[Configuration Guide](docs/configuration.md)** - Configuration options and examples
- **[CLI Reference](docs/cli-reference.md)** - Complete command reference

**🔧 Advanced Topics:**

- **[API Reference](docs/api.md)** - REST API endpoints
- **[OAuth Authentication](docs/oauth.md)** - OAuth setup and security
- **[Daemon Management](docs/daemon-management.md)** - Background process management
- **[Troubleshooting](docs/troubleshooting.md)** - Common issues and solutions

---

## Contributing & Support

- [Contributing Guide](CONTRIBUTING.md)
- [Issue Tracker](https://github.com/billyjbryant/mcp-foxxy-bridge/issues)
- [Discussions](https://github.com/billyjbryant/mcp-foxxy-bridge/discussions)

---

## License

AGPL-3.0-or-later - See [LICENSE](LICENSE) file for details.

---
