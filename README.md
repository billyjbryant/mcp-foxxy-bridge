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

**MCP Foxxy Bridge** is a secure, feature-rich one-to-many proxy for the Model Context Protocol (MCP). It lets you aggregate and route requests to multiple MCP servers through a single endpoint, with enterprise-grade security features:

## 🔒 Security Features
- **Command substitution security** with allow-lists and validation
- **OAuth 2.0 + PKCE authentication** for secure server connections
- **Shell injection protection** with comprehensive input validation
- **Localhost-only binding** by default for maximum security

## 🚀 Core Capabilities
- Centralize configuration for all your MCP servers
- Expose all tools, resources, and prompts from connected servers
- Route requests transparently to the right backend
- Use a single MCP endpoint in your AI tools (Claude Desktop, VS Code, etc.)
- Support for command substitution with secure credential retrieval

---

## 🚀 Quickstart

See the [Installation Guide](docs/installation.md) for full details.

### 1. Choose one of the following installation methods

**A. Install via uv (Recommended):**

```bash
uv tool install mcp-foxxy-bridge
```

**B. Install latest from GitHub:**

```bash
uv tool install git+https://github.com/billyjbryant/mcp-foxxy-bridge
```

**C. Run with Docker (from GHCR):**

```bash
docker run --rm -p 8080:8080 ghcr.io/billyjbryant/mcp-foxxy-bridge:latest --bridge-config /app/config.json
```

---

### 2. Run the Bridge

**With config file:**

```bash
mcp-foxxy-bridge --bridge-config config.json
```

**Or with named servers:**

```bash
mcp-foxxy-bridge --port 8080 \
  --named-server fetch 'uvx mcp-server-fetch' \
  --named-server github 'npx -y @modelcontextprotocol/server-github' \
  --named-server filesystem 'npx -y @modelcontextprotocol/server-filesystem'

# With security features
mcp-foxxy-bridge --bridge-config config.json \
  --allow-command-substitution  # Enable secure command substitution
```

See [Configuration Guide](docs/configuration.md) for config file examples.

---

### 3. Connect Your AI Tool

Point your MCP-compatible client to:

```
http://localhost:8080/sse
```

See [API Reference](docs/api.md) for integration details.

---

## 📚 Documentation

- [Overview & Features](docs/README.md)
- [Installation Guide](docs/installation.md)
- [Configuration Guide](docs/configuration.md)
- [Security Guide](docs/security.md) 🔒
- [OAuth Authentication](docs/oauth.md) 🔐
- [Deployment Guide](docs/deployment.md)
- [API Reference](docs/api.md)
- [Architecture Overview](docs/architecture.md)
- [Troubleshooting Guide](docs/troubleshooting.md)
- [Example Configurations](docs/examples/README.md)

---

## 🛠️ Development

- [Development Setup](docs/README.md#development)
- [Contributing Guide](CONTRIBUTING.md)

---

## 🤝 Contributing & Support

- [Contributing Guide](CONTRIBUTING.md)
- [Issue Tracker](https://github.com/billyjbryant/mcp-foxxy-bridge/issues)
- [Discussions](https://github.com/billyjbryant/mcp-foxxy-bridge/discussions)

---

## 🔒 Security

MCP Foxxy Bridge implements comprehensive security measures:

### Network Security
- **Default binding**: Bridge binds to `127.0.0.1:8080` (localhost-only) by default
- **MCP server isolation**: Individual MCP servers communicate via local stdio pipes, never network ports
- **OAuth port separation**: Dedicated OAuth callback port (8090) independent of main bridge port
- **Configurable access**: Host and port settings can be configured via config file or CLI arguments

### Command Substitution Security
- **Allow-list approach**: Only pre-approved commands can be executed via `$(command)` syntax
- **Shell injection protection**: Blocks dangerous shell operators (`|`, `&`, `;`, etc.)
- **Argument validation**: Validates arguments for sensitive commands (git, vault, op, gh)
- **Read-only enforcement**: Prevents write/delete operations in command substitution

### Authentication Security
- **OAuth 2.0 + PKCE**: Secure authentication with Proof Key for Code Exchange
- **Automatic discovery**: OAuth endpoints discovered from server metadata
- **Secure token storage**: Tokens stored with restricted file permissions
- **Token refresh**: Automatic token renewal when possible

### Configuration Priority
1. Command-line arguments (`--host`, `--port`, `--allow-command-substitution`) - highest priority
2. Configuration file bridge settings (`bridge.host`, `bridge.port`, `bridge.allow_command_substitution`)
3. Environment variables (`MCP_ALLOW_COMMAND_SUBSTITUTION`, `MCP_ALLOWED_COMMANDS`)
4. Secure defaults (`127.0.0.1:8080`, command substitution disabled) - lowest priority

### Security Recommendations
- Keep the default `127.0.0.1` binding unless external access is required
- Only enable command substitution when needed, with minimal command allow-lists
- Use OAuth authentication for production deployments with sensitive data
- Regularly update MCP server dependencies and review access logs
- See [Security Guide](docs/security.md) for comprehensive security practices

---

## ⚖️ License

This project is licensed under the GNU Affero General Public License v3.0 or later (AGPLv3+). See the [LICENSE](LICENSE) file for details.

---
