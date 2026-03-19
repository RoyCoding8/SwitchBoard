"""Data models for Switchboard.

Domain objects are immutable (frozen dataclass) to prevent accidental mutation.
Toggle operations return new instances rather than mutating in place.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any


class Assistant(Enum):
    """Supported AI assistants."""

    CURSOR = "cursor"
    VSCODE = "vscode"
    CLAUDE = "claude"
    CLINE = "cline"
    ROOCODE = "roocode"
    OPENCODE = "opencode"
    GEMINI = "gemini"
    CODEX = "codex"


class ItemKind(Enum):
    """Type of skill/agent item."""

    SKILL = "skill"
    AGENT = "agent"


@dataclass(frozen=True)
class MCPServer:
    """Immutable representation of an MCP server configuration.

    Use with_enabled() to create a new instance with different enabled state.
    """

    name: str
    assistant: Assistant
    config: dict[str, Any]
    source_file: Path
    enabled: bool = True

    @property
    def command(self) -> str:
        """Extract command from config."""
        cmd = self.config.get("command", "")
        if self.assistant == Assistant.OPENCODE:
            return cmd[0] if isinstance(cmd, list) and cmd else str(cmd)
        return str(cmd)

    @property
    def args(self) -> list[str]:
        """Extract arguments from config."""
        if self.assistant == Assistant.OPENCODE:
            cmd = self.config.get("command", [])
            return cmd[1:] if isinstance(cmd, list) else []
        return self.config.get("args", [])

    @property
    def summary(self) -> str:
        """Human-readable summary for display."""
        return f"{self.command} {' '.join(self.args[:2])}".strip()

    def with_enabled(self, enabled: bool) -> MCPServer:
        """Return new instance with different enabled state."""
        return replace(self, enabled=enabled)

    def with_path(self, path: Path) -> MCPServer:
        """Return new instance with different source file path."""
        return replace(self, source_file=path)


@dataclass(frozen=True)
class Skill:
    """Immutable representation of a skill/agent.

    Use with_enabled() to create a new instance with different enabled state.
    """

    name: str
    path: Path
    assistant: Assistant
    kind: ItemKind = ItemKind.SKILL
    description: str = ""
    enabled: bool = True

    def with_enabled(self, enabled: bool, new_path: Path | None = None) -> Skill:
        """Return new instance with different enabled state and optionally new path."""
        if new_path is not None:
            return replace(self, enabled=enabled, path=new_path)
        return replace(self, enabled=enabled)


@dataclass
class AppState:
    """Persistent state stored in state file.

    This is mutable as it represents application state that changes over time.

    Attributes:
        disabled: Stashed MCP server configs for assistants without native toggle.
                  Structure: {assistant_name: {server_name: server_config}}
        disabled_skills: DEPRECATED - kept for backward compatibility.
                        Skills are now disabled via filesystem rename (.disabled suffix).
    """

    disabled: dict[str, dict[str, dict]] = field(default_factory=dict)
    disabled_skills: list[str] = field(default_factory=list)  # Legacy, unused
