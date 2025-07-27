# MCP Foxxy Bridge

[![CI/CD Pipeline](https://github.com/billyjbryant/mcp-foxxy-bridge/workflows/CI/CD%20Pipeline/badge.svg)](https://github.com/billyjbryant/mcp-foxxy-bridge/actions)
[![Release](https://github.com/billyjbryant/mcp-foxxy-bridge/workflows/CI/CD%20Pipeline/badge.svg?branch=main&event=release)](https://github.com/billyjbryant/mcp-foxxy-bridge/releases)
[![PyPI version](https://badge.fury.io/py/mcp-foxxy-bridge.svg)](https://badge.fury.io/py/mcp-foxxy-bridge)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

A **MCP Forward Proxy Bridge** designed to be a one-to-many bridge that allows you to use a single MCP server to communicate with many MCP servers transparently.

## Overview

The MCP Foxxy Bridge solves the problem of having to configure multiple MCP servers across different AI tools by providing a centralized proxy that:

- **Aggregates multiple MCP servers** into a single interface
- **Exposes all tools, resources, and prompts** from configured MCP servers
- **Routes requests transparently** to the appropriate underlying MCP server
- **Allows you to configure your MCPs in one place** for use across all AI tools

## Quick Start

### Installation

**Recommended: Install via uv**
```bash
uv tool install mcp-foxxy-bridge
```

**Alternative: Install via pipx**
```bash
pipx install mcp-foxxy-bridge
```

**Install latest from git**
```bash
uv tool install git+https://github.com/billyjbryant/mcp-foxxy-bridge
```

### Basic Usage

**Start bridge with multiple servers:**
```bash
mcp-foxxy-bridge --port 8080 \
  --named-server fetch 'uvx mcp-server-fetch' \
  --named-server github 'npx -y @modelcontextprotocol/server-github' \
  --named-server filesystem 'npx -y @modelcontextprotocol/server-filesystem'
```

**Start bridge with configuration file:**
```bash
mcp-foxxy-bridge --port 8080 --named-server-config ./servers.json
```

**Connect AI tools to the bridge:**
Your bridge will be available at `http://localhost:8080/sse`

### Claude Desktop Configuration

Add this to your Claude Desktop MCP configuration:

```json
{
  "mcpServers": {
    "foxxy-bridge": {
      "command": "mcp-foxxy-bridge",
      "args": ["http://localhost:8080/sse"]
    }
  }
}
```

## Architecture

```
AI Tools (Claude Desktop, VS Code, etc.)
    ↓ (SSE/stdio)
MCP Foxxy Bridge
    ↓ (stdio to multiple servers)
MCP Server 1, MCP Server 2, MCP Server N
```

The Foxxy Bridge acts as a transparent forward proxy between AI tools and multiple MCP servers, providing:

- **Tool Aggregation**: Unified access to tools from all connected servers
- **Resource Aggregation**: Access to resources across multiple servers
- **Namespace Management**: Automatic tool/resource namespacing to prevent conflicts
- **Request Routing**: Intelligent routing of requests to appropriate servers
- **Health Monitoring**: Built-in status endpoint for monitoring server health

## Key Features

- ✅ **One-to-Many Bridge**: Connect multiple MCP servers through a single endpoint
- ✅ **Tool Aggregation**: Unified access to tools from all connected servers
- ✅ **Resource Subscription**: Full support for resource subscriptions and forwarding
- ✅ **Logging Coordination**: Centralized logging level management across all servers
- ✅ **Progress Notifications**: Transparent progress forwarding from managed servers
- ✅ **Completion Aggregation**: Combined autocomplete suggestions from all servers
- ✅ **Namespace Management**: Automatic tool namespacing to prevent conflicts
- ✅ **Environment Variables**: Support for `${VAR_NAME}` expansion in configs
- ✅ **Multiple Deployment Options**: Local process, Docker container, or UV tool
- ✅ **Health Monitoring**: Built-in status endpoint for monitoring

## Documentation

📚 **[Complete Documentation](docs/README.md)**

- [Installation Guide](docs/installation.md) - Detailed installation instructions
- [Configuration Guide](docs/configuration.md) - Configuration options and examples
- [Deployment Guide](docs/deployment.md) - Docker, local, and UV deployment
- [API Reference](docs/api.md) - Endpoints and programmatic usage
- [Architecture Overview](docs/architecture.md) - Technical architecture and design
- [Troubleshooting Guide](docs/troubleshooting.md) - Common issues and solutions

## Development

### Requirements

- Python 3.11+
- uv package manager
- Node.js (for MCP servers that require it)

### Development Setup

```bash
# Clone the repository
git clone https://github.com/billyjbryant/mcp-foxxy-bridge.git
cd mcp-foxxy-bridge

# Install dependencies
uv sync --dev

# Run tests
uv run pytest

# Run linting
uv run ruff check

# Run type checking
uv run mypy src/

# Run the bridge in development
uv run -m mcp_foxxy_bridge --port 8080
```

### Docker Development

```bash
# Build Docker image
docker build -t mcp-foxxy-bridge .

# Run with Docker
docker run --rm -p 8080:8080 mcp-foxxy-bridge
```

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details on:

- Development setup
- Code style and linting
- Testing requirements
- Pull request process

## License

This project is licensed under the GNU Affero General Public License v3.0 or later (AGPLv3+). See the [LICENSE](LICENSE) file for details.

## Support

- 📖 [Documentation](docs/README.md)
- 🐛 [Issue Tracker](https://github.com/billyjbryant/mcp-foxxy-bridge/issues)
- 💬 [Discussions](https://github.com/billyjbryant/mcp-foxxy-bridge/discussions)

---

**MCP Foxxy Bridge** - Bridging the gap between AI tools and multiple MCP servers.
