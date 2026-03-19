"""Assistant configuration abstraction for Switchboard (ARCH H2/H3).

Centralizes all assistant-specific behavior in a single data structure.
Adding a new assistant requires only adding a new entry to ASSISTANT_CONFIGS.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .paths import SYSTEM, get_appdata, get_home


class ToggleMethod(Enum):
    """Method used to toggle servers on/off for an assistant."""

    NATIVE_DISABLED = "native_disabled"  # Uses 'disabled' field in config
    NATIVE_ENABLED = "native_enabled"  # Uses 'enabled' field in config
    STASH = "stash"  # Moves config to/from state file


@dataclass(frozen=True)
class AssistantConfig:
    """Configuration for a single AI assistant (immutable).

    This centralizes all assistant-specific behavior:
    - Config file paths
    - JSON key for servers
    - Toggle method
    - Skill directories

    Adding a new assistant requires only adding a new entry to ASSISTANT_CONFIGS.
    """

    servers_key: str
    toggle_method: ToggleMethod
    is_toml: bool = False
    skill_dirs: tuple[tuple[str, Path], ...] = field(default_factory=tuple)

    def get_config_paths(self) -> list[Path]:
        """Get config file paths for this assistant.

        Must be called after module initialization to ensure HOME is validated.
        """
        # This is overridden per-assistant in ASSISTANT_CONFIGS
        return []


def _build_assistant_configs() -> dict[str, AssistantConfig]:
    """Build assistant configurations lazily to allow HOME validation."""
    # Import here to avoid circular imports
    from ..models import Assistant, ItemKind

    home = get_home()
    appdata = get_appdata()

    # Helper to create config with paths
    @dataclass(frozen=True)
    class _AssistantConfigWithPaths(AssistantConfig):
        _paths: tuple[Path, ...] = field(default_factory=tuple)

        def get_config_paths(self) -> list[Path]:
            return list(self._paths)

    configs: dict[str, AssistantConfig] = {}

    # Cursor
    cursor_paths = [home / ".cursor" / "mcp.json"]
    if SYSTEM == "Windows":
        cursor_paths.append(appdata / "Cursor" / "mcp.json")
    configs[Assistant.CURSOR.value] = _AssistantConfigWithPaths(
        servers_key="mcpServers",
        toggle_method=ToggleMethod.STASH,
        _paths=tuple(cursor_paths),
    )

    # VS Code
    configs[Assistant.VSCODE.value] = _AssistantConfigWithPaths(
        servers_key="servers",
        toggle_method=ToggleMethod.STASH,
        _paths=(home / ".vscode" / "mcp.json",),
    )

    # Claude
    configs[Assistant.CLAUDE.value] = _AssistantConfigWithPaths(
        servers_key="mcpServers",
        toggle_method=ToggleMethod.STASH,
        _paths=(home / ".claude.json",),
    )

    # Cline
    configs[Assistant.CLINE.value] = _AssistantConfigWithPaths(
        servers_key="mcpServers",
        toggle_method=ToggleMethod.NATIVE_DISABLED,
        _paths=(
            appdata
            / "Code"
            / "User"
            / "globalStorage"
            / "saoudrizwan.claude-dev"
            / "settings"
            / "cline_mcp_settings.json",
        ),
    )

    # RooCode
    configs[Assistant.ROOCODE.value] = _AssistantConfigWithPaths(
        servers_key="mcpServers",
        toggle_method=ToggleMethod.NATIVE_DISABLED,
        _paths=(
            appdata
            / "Code"
            / "User"
            / "globalStorage"
            / "rooveterinaryinc.roo-cline"
            / "settings"
            / "mcp_settings.json",
        ),
    )

    # OpenCode
    configs[Assistant.OPENCODE.value] = _AssistantConfigWithPaths(
        servers_key="mcp",
        toggle_method=ToggleMethod.NATIVE_ENABLED,
        _paths=(home / ".config" / "opencode" / "opencode.json",),
        skill_dirs=(
            (ItemKind.AGENT.value, home / ".config" / "opencode" / "agents"),
            (ItemKind.SKILL.value, home / ".config" / "opencode" / "skills"),
        ),
    )

    # Gemini
    configs[Assistant.GEMINI.value] = _AssistantConfigWithPaths(
        servers_key="mcpServers",
        toggle_method=ToggleMethod.NATIVE_DISABLED,
        _paths=(
            home / ".gemini" / "settings.json",
            home / ".gemini" / "antigravity" / "mcp_config.json",
        ),
        skill_dirs=(
            (ItemKind.SKILL.value, home / ".gemini" / "antigravity" / "skills"),
            (ItemKind.SKILL.value, home / ".gemini" / "skills"),
        ),
    )

    # Codex
    configs[Assistant.CODEX.value] = _AssistantConfigWithPaths(
        servers_key="mcp_servers",
        toggle_method=ToggleMethod.NATIVE_ENABLED,
        is_toml=True,
        _paths=(home / ".codex" / "config.toml",),
    )

    return configs


# Lazy initialization to allow HOME validation on first access
_assistant_configs: dict[str, AssistantConfig] | None = None


def get_assistant_configs() -> dict[str, AssistantConfig]:
    """Get assistant configurations (lazy initialization)."""
    global _assistant_configs
    if _assistant_configs is None:
        _assistant_configs = _build_assistant_configs()
    return _assistant_configs


# For backward compatibility - this is a property-like access
class _AssistantConfigsProxy:
    def __getitem__(self, key: str) -> AssistantConfig:
        return get_assistant_configs()[key]

    def __contains__(self, key: str) -> bool:
        return key in get_assistant_configs()

    def items(self):
        return get_assistant_configs().items()

    def values(self):
        return get_assistant_configs().values()

    def keys(self):
        return get_assistant_configs().keys()

    def get(self, key: str, default=None):
        return get_assistant_configs().get(key, default)


ASSISTANT_CONFIGS = _AssistantConfigsProxy()
