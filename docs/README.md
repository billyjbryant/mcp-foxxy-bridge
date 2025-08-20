# MCP Foxxy Bridge Documentation

Welcome to the comprehensive documentation for MCP Foxxy Bridge! Whether you're just getting started or diving deep into advanced configurations, you'll find everything you need here.

## 🎯 Choose Your Path

### 🆕 New to MCP Foxxy Bridge?
Start with our **[Installation Guide](installation.md)** and follow the beginner-friendly setup process.

### ⚡ Quick Setup
Jump to **[Example Configurations](examples/README.md)** for ready-to-use config files.

### 🏢 Production Deployment
Review **[Security Guide](security.md)** → **[OAuth Guide](oauth.md)** → **[Deployment Guide](deployment.md)**

### 🔧 Developer/Contributor
Check **[Architecture Overview](architecture.md)** → **[Contributing Guide](../CONTRIBUTING.md)**

---

## 📚 Complete Documentation Index

### 🚀 Getting Started
- **[Installation Guide](installation.md)** - Multiple installation methods (uv, pip, Docker)
- **[Configuration Guide](configuration.md)** - Complete configuration reference
- **[Example Configurations](examples/README.md)** - Ready-to-use setups for common scenarios

### 🏗️ Advanced Setup
- **[Deployment Guide](deployment.md)** - Production deployments with Docker and orchestration
- **[Architecture Overview](architecture.md)** - Technical deep dive into system design
- **[API Reference](api.md)** - REST endpoints and programmatic integration

### 🛡️ Security & Production
- **[Security Guide](security.md)** - Comprehensive security best practices
- **[OAuth Authentication](oauth.md)** - Enterprise authentication setup

### 🔧 Operations & Maintenance
- **[Troubleshooting Guide](troubleshooting.md)** - Common issues and solutions
- **[Maintenance Guide](maintenance.md)** - Automated maintenance and updates
- **[Release Process](releasing.md)** - How releases are created and published

### 👥 Contributing
- **[Contributing Guide](../CONTRIBUTING.md)** - Development setup and contribution guidelines

## Quick Start

1. **Install**: `uv tool install mcp-foxxy-bridge`
2. **Configure**: Create a bridge configuration file
3. **Run**: `mcp-foxxy-bridge --bridge-config config.json`
4. **Connect**: Point your MCP client to `http://localhost:8080/sse`

## Key Features

- **One-to-Many Bridge**: Connect multiple MCP servers through a single endpoint
- **Tool Aggregation**: Unified access to tools from all connected servers
- **Namespace Management**: Automatic tool namespacing to prevent conflicts
- **Environment Variables**: Support for `${VAR_NAME}` expansion in configs
- **Multiple Deployment Options**: Local process, Docker container, or UV tool
- **Health Monitoring**: Built-in status endpoint for monitoring

## Getting Help

- Review [Configuration Guide](configuration.md) for setup patterns
- Check [Troubleshooting Guide](troubleshooting.md) for common issues
- Check [API Reference](api.md) for detailed endpoint documentation
- Check the [Contributing Guide](../CONTRIBUTING.md) for development setup
