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

**MCP Foxxy Bridge** is a one-to-many proxy for the Model Context Protocol (MCP). It lets you aggregate and route requests to multiple MCP servers through a single endpoint, so you can:

- Centralize configuration for all your MCP servers
- Expose all tools, resources, and prompts from connected servers
- Route requests transparently to the right backend
- Use a single MCP endpoint in your AI tools (Claude Desktop, VS Code, etc.)

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

## ⚖️ License

This project is licensed under the GNU Affero General Public License v3.0 or later (AGPLv3+). See the [LICENSE](LICENSE) file for details.

---
