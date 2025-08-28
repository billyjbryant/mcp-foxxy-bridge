# Installation Guide

## Prerequisites

- Python 3.10+
- Node.js 18+ (for npm-based MCP servers)
- Docker (optional, for containerized deployment)

## Installation

### UV Tool (Recommended)

```bash
# Install
uv tool install mcp-foxxy-bridge

# Install from GitHub (latest)
uv tool install git+https://github.com/billyjbryant/mcp-foxxy-bridge

# Verify installation
foxxy-bridge --version
```

### Local Development

```bash
# Clone repository
git clone https://github.com/billyjbryant/mcp-foxxy-bridge
cd mcp-foxxy-bridge

# Install dependencies
uv sync

# Run from source
uv run foxxy-bridge --debug
```

### Docker

```bash
# Run from GitHub Container Registry
docker run -p 8080:8080 \
  -v ./config.json:/app/config.json:ro \
  -e GITHUB_TOKEN=$GITHUB_TOKEN \
  ghcr.io/billyjbryant/mcp-foxxy-bridge:latest

# Or build locally
docker build -t mcp-foxxy-bridge .
docker run -p 8080:8080 mcp-foxxy-bridge
```

### Pipx (Alternative)

```bash
pipx install mcp-foxxy-bridge
foxxy-bridge --version
```

## Quick Setup

### 1. Initialize Configuration

```bash
# Create default configuration
foxxy-bridge config init

# View the created configuration
foxxy-bridge config config-show
```

### 2. Add MCP Servers

```bash
# Add GitHub server (requires GITHUB_TOKEN)
foxxy-bridge mcp add github "npx" "-y" "@modelcontextprotocol/server-github" \
  --env GITHUB_TOKEN "${GITHUB_TOKEN}" \
  --tags development git

# Add filesystem server for local files
foxxy-bridge mcp add filesystem "npx" "-y" "@modelcontextprotocol/server-filesystem" "./" \
  --tags local files

# Add fetch server for web content
foxxy-bridge mcp add fetch "uvx" "mcp-server-fetch" \
  --tags web remote

# List configured servers
foxxy-bridge mcp mcp-list
```

### 3. Start the Bridge

```bash
# Start bridge server
foxxy-bridge server start

# Or start as background daemon
foxxy-bridge server start --daemon

# Check status
foxxy-bridge server server-status
```

### 4. Connect Your Client

Point your MCP client to: `http://localhost:8080/sse`

Test the connection:
```bash
curl http://localhost:8080/status
```

## Environment Variables

```bash
# Set required variables
export GITHUB_TOKEN=ghp_your_token_here
export BRAVE_API_KEY=your_api_key_here

# Variables are expanded in config
foxxy-bridge config set mcpServers.github.env.GITHUB_TOKEN '${GITHUB_TOKEN}'
```

## Legacy Mode (Backward Compatibility)

The traditional command-line interface is still supported:

```bash
# Run with config file
mcp-foxxy-bridge --bridge-config config.json

# Run with named servers
mcp-foxxy-bridge --port 8080 \
  --named-server github 'npx -y @modelcontextprotocol/server-github' \
  --named-server fetch 'uvx mcp-server-fetch'
```

## Next Steps

- [Configuration Guide](configuration.md) - Detailed configuration options
- [Example Configurations](examples/README.md) - Ready-to-use configs
- [Troubleshooting](troubleshooting.md) - Common issues and solutions
