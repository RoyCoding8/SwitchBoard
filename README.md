# Switchboard — Unified AI Tool Manager

> One-stop TUI for managing MCP servers, skills, and agents across all your AI assistants.

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)
[![CI](https://github.com/RoyCoding8/SwitchBoard/actions/workflows/ci.yml/badge.svg)](https://github.com/RoyCoding8/SwitchBoard/actions/workflows/ci.yml)

## Motivation

Managing Model Context Protocol (MCP) servers, agents, and skills is currently fragmented. Every tool — Cursor, Claude Code, Gemini, OpenCode — has its own config file, its own discovery path, and its own way of disabling tools. 

**Switchboard** provides a unified terminal interface to:
- **Discover** all installed MCP servers, agents, and skills automatically.
- **Toggle** tools on/off with a single keypress, across all assistants.
- **Sync** state automatically using native config flags or a centralized state stashing mechanism.

## Quick Start

**Switchboard** is built with Python and [Textual](https://textual.textualize.io/). We recommend using [`uv`](https://github.com/astral-sh/uv) for the best experience.

```powershell
# Clone and run immediately
git clone https://github.com/RoyCoding8/SwitchBoard
cd switchboard
./run.bat  # On Windows
# OR
uv run switchboard
```

## Features

- **Unified MCP Management**: Support for 8+ AI assistants and counting.
- **Agent & Skill Discovery**: Automatically finds `.md` agents and `SKILL.md` directories (OpenCode, Gemini/Antigravity).
- **Toggle All**: Enable or disable entire sections (Servers/Agents/Skills) or entire assistant profiles instantly.
- **Auto-Save**: Every change is written immediately to your native config files.
- **Native Support**: Uses native `enabled: false` or `disabled: true` flags where supported; uses smart stashing for everything else.

## Support Matrix

| Assistant | Config Target | Persistence Method |
| :--- | :--- | :--- |
| **Cursor** | `mcp.json` | State Stashing |
| **VS Code** | `mcp.json` | State Stashing |
| **Claude Code** | `.claude.json` | State Stashing |
| **Cline** | `cline_mcp_settings.json` | Native `disabled` flag |
| **RooCode** | `mcp_settings.json` | Native `disabled` flag |
| **OpenCode** | `opencode.json` | Native `enabled` flag |
| **Gemini** | `settings.json` | Native `disabled` flag |
| **Codex CLI** | `config.toml` | Native `enabled` flag |

## Keyboard Shortcuts

| Key | Action |
| :--- | :--- |
| `r` | Refresh (re-scan filesystem) |
| `e` | **Enable All** in current tab |
| `d` | **Disable All** in current tab |
| `q` | Quit |

## Installation

### Prerequisites
- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (recommended)

### Manual Setup
```bash
git clone https://github.com/yourusername/switchboard
cd switchboard
uv sync
uv run switchboard
```

### Development Setup
```bash
# Install with dev dependencies
uv sync --dev

# Run tests
uv run pytest tests/ -v

# Run linting
uv tool run ruff check src/ tests/
```

## Architecture

Switchboard uses a modular architecture designed for maintainability and extensibility:

```
src/switchboard/
├── __init__.py           # Package marker
├── __main__.py           # CLI entry point
├── models.py             # Immutable domain objects (MCPServer, Skill, AppState)
├── config_manager.py     # High-level API for discovery and toggling
├── app.py                # Textual TUI application
└── config/               # Configuration subpackage
    ├── __init__.py       # Package exports
    ├── paths.py          # Platform paths, HOME validation, XDG support
    ├── security.py       # Input validation, path safety checks
    ├── io.py             # JSON/TOML I/O with atomic writes
    ├── assistants.py     # AssistantConfig abstraction
    └── state.py          # Persistent state management
```

### Key Design Decisions

- **Immutable Domain Objects**: `MCPServer` and `Skill` are frozen dataclasses with `with_enabled()` methods for safe state transitions.
- **Assistant Abstraction**: Adding a new assistant requires only adding a single entry to `ASSISTANT_CONFIGS`.
- **Security-First**: Path containment checks, input validation, and file locking prevent common vulnerabilities.
- **Async Support**: All I/O operations have async versions to keep the TUI responsive.

## How It Works

Switchboard maps the known configuration paths for various tools and parses their JSON/TOML. When you toggle a server:
1. If the tool supports a **native toggle** (like Cline's `disabled` flag), Switchboard edits the native config directly.
2. If the tool lacks a toggle, Switchboard **stashes** the server configuration into the Switchboard state file in the Switchboard state directory (Linux: `~/.local/share/switchboard/state.json`, macOS: `~/Library/Application Support/switchboard/state.json`, Windows: `%LOCALAPPDATA%\switchboard\state.json`) and removes it from the assistant's config, "disabling" it effectively. Restoring it moves the config back.

For skills and agents, toggling works by moving the folder/file out of the assistant's watched directory into Switchboard's disabled store (under the Switchboard state directory at `disabled/<assistant>/<kind>/`), and moving it back to re-enable.

## Security

Switchboard includes several security measures:
- **Path containment**: Prevents path traversal attacks when toggling skills/agents
- **Input validation**: Rejects invalid server/skill names
- **Atomic writes**: Prevents config corruption from interrupted writes
- **Atomic moves**: Uses a staging directory during skill/agent moves to avoid partial reads
- **File locking**: Prevents race conditions during concurrent operations
- **HOME validation**: Validates HOME environment variable ownership (Unix)

## License

Apache-2.0 © [Shashwata Roy](https://github.com/Roycoding8)
