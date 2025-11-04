# CLAUDE.md

AI assistant reference for MCP Foxxy Bridge development.

## 📋 Quick Reference

**Common:**

- Setup: `uv sync`
- Run SSE: `uv run foxxy-bridge --config config.json`
- Run stdio: `uv run foxxy-bridge server start --stdio` or `uvx mcp-foxxy-bridge server start --stdio`
- Test: `pytest`
- Lint: `ruff check --fix && mypy src/`
- Format: `ruff format`

**Security:**

- Enable cmd substitution: `--allow-command-substitution`
- ⚠️ NEVER use `--allow-dangerous-commands` in production

## Commands

**Run SSE Mode:** `uv run foxxy-bridge --config config.json` (primary), `uv run mcp-foxxy-bridge` (alias), `uv run -m mcp_foxxy_bridge` (legacy)

**Run stdio Mode:** `uv run mcp-foxxy-bridge server start --stdio` (CLI flag), or set `"stdio": true` in bridge config

**Test:** `pytest`, `pytest -v`, `pytest tests/test_config_loader.py`, `coverage run -m pytest && coverage report`

**Quality:** `ruff check`, `ruff format`, `ruff check --fix`, `mypy src/`

**Debug:** Add `--debug` flag. Security flags: `--allow-command-substitution`, `--allow-dangerous-commands` (testing only)

## Commit Guidelines

Enhanced conventional commit types for granular release control:

**Features:**
- `feat(major):` → minor release (significant features)
- `feat(minor):` → patch release (incremental features)
- `feat!:` → major release (breaking changes)
- `feat:` → minor release (default features)

**Fixes:**
- `fix(security):` → minor release (security fixes)
- `fix(critical):` → minor release (critical fixes)
- `fix(major):` → minor release (major bug fixes)
- `fix:` → patch release (standard fixes)

**Scopes:** `cli`, `core`, `api`, `bridge`, `oauth`, `config`, `server`, `client`, `auth`, `logging`

**Examples:**
- `feat(major): add environment variable expansion` → 1.5.0
- `feat(minor): enhance CLI output formatting` → 1.4.1
- `fix(security): resolve token exposure vulnerability` → 1.4.5
- `fix(critical): resolve connection timeout` → 1.4.4
- `fix(server): resolve case-sensitivity issues` → 1.4.3

**API Endpoints (port 9000):**

- Status: `/status`, `/sse/servers`, `/sse/tags`, `/sse/mcp/{server}/status`
- Tools: `/sse/list_tools`, `/sse/mcp/{server}/list_tools`, `/sse/tag/{tags}/list_tools`
- Mgmt: POST `/sse/mcp/{server}/reconnect`, `/sse/tools/rescan`
- OAuth: `/oauth/{server}/status`
- Tag syntax: `tag/dev+local` (AND), `tag/web,api` (OR)

## Architecture

One-to-many MCP proxy aggregating multiple servers through single endpoint.

**Core Files:**

- `mcp_server.py` - HTTP/SSE client endpoints
- `bridge_server.py` - MCP protocol & tool aggregation
- `server_manager.py` - Backend server lifecycle
- `config_loader.py` - Config parsing, env expansion, security
- `sse_client_wrapper.py` - OAuth-aware SSE client
- `oauth/` - OAuth 2.0 + PKCE

**Patterns:**

- `AsyncExitStack` for async lifecycle management
- Namespacing prevents tool/resource conflicts
- Auto retry/failover, exponential backoff health monitoring
- Command substitution security validation
- OAuth 2.0 + PKCE with auto token management

**Flow:** Client → SSE endpoint → Bridge aggregates → Server Manager routes → Backend server → Response

**Config Features:**

- JSON with `${VAR}` env expansion, `$(cmd)` substitution
- Conflict resolution, failover strategies
- Health ops: `list_tools`, `list_resources`, `list_prompts`, `call_tool`, `read_resource`, `get_prompt`, `ping`, `health`, `status`
- Keep-alive with intervals/timeouts, auto-restart on failure
- OAuth with issuer discovery, secure token storage

**States:** CONNECTING → CONNECTED → FAILED/DISCONNECTED/DISABLED

## Testing

- `pytest` with `pytest-asyncio`, tests in `tests/`, `asyncio_mode = "auto"`
- Port 9090 for future testing

## Configuration

JSON config (default: `config.json`) with `${VAR}` env expansion, `$(cmd)` substitution.

**Minimal:**

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

**With Security/OAuth:**

```json
{
  "servers": {
    "secure-app": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {"GITHUB_TOKEN": "$(op read op://Private/GitHub/token)"},
      "oauth": {
        "enabled": true,
        "issuer": "https://auth.atlassian.com",
        "verify_ssl": true
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

**With stdio Transport:**

```json
{
  "servers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "./"]
    }
  },
  "bridge": {
    "stdio": true
  }
}
```

## Future Improvements

### v1.5.0 - Process Isolation (chroot)

- **Goal:** Per-server filesystem isolation
- **Benefits:** Isolated environments, reduced attack surface, defense-in-depth
- **Tech:** Platform-specific chroot (Linux/macOS/Windows), config validation, error handling
- **Priority:** High (security) | **Complexity:** High (OS-level)

### Auth Migration to mcp-auth

- **Current:** Custom OAuth 2.0 + PKCE working
- **Plan:** Phase 1: Server auth, Phase 2: Replace client code, Phase 3: Context-based tokens
- **Benefits:** OAuth 2.1 (RFC 9728), provider-agnostic, `TokenVerifier` protocol, auto-discovery
- **Refs:** [mcp-auth/python](https://github.com/mcp-auth/python), [mcp-auth.dev](https://mcp-auth.dev/docs)

## Dev Notes

- Always specify timeout/background when running bridge (avoid getting stuck)
- Don't add emojis to logs (logging module handles this)
- NEVER ADD MANUAL OAUTH MAPPINGS TO "FIX" DYNAMIC OAUTH! DYNAMIC OAUTH ISNT DYNAMIC IF YOU ARE OVERRIDING IT WITH A MANUAL MAP
- Always update the configuration schema if we make changes to the configuration management

## Backlog TODOs

- **Config reload bug**: `mcp restart` command doesn't reload configuration from disk, uses cached config in memory. Need to implement config reload in the `/sse/mcp/{server}/reconnect` API endpoint.
- **Bearer token OAuth**: Complete HTTP OAuth implementation to use Bearer tokens instead of SSE OAuth flow for HTTP/streamablehttp transports.
