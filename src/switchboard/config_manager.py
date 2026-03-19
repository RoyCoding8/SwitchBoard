"""Config discovery, parsing, and mutation for all supported AI assistants — Switchboard.

This module provides the main API for discovering and toggling MCP servers and skills.
Implementation details are delegated to the config subpackage.

Async versions of discovery functions are provided for non-blocking UI operations.
"""

from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path

from .config import (
    ASSISTANT_CONFIGS,
    ToggleMethod,
    get_disabled_skills_dir,
    get_staging_dir,
    get_state_file,
    is_path_safe,
    is_valid_name,
    load_state,
    read_json,
    read_toml,
    save_state,
    write_json,
    write_toml,
)
from .models import Assistant, ItemKind, MCPServer, Skill

logger = logging.getLogger(__name__)

DISABLED_SUFFIX = ".disabled"  # Legacy suffix; ignored during discovery.
STATE_FILE = get_state_file()
_executor: ThreadPoolExecutor | None = None


def _get_executor() -> ThreadPoolExecutor:
    """Get or create the shared thread pool."""
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="switchboard")
    return _executor


class ServerNotFoundError(Exception):
    """Server not found in configuration."""


def discover_servers() -> list[MCPServer]:
    """Discover all MCP servers from all assistant configuration files.

    Returns:
        List of MCPServer instances representing all configured servers.
    """
    state = load_state()
    servers: list[MCPServer] = []

    for asst in Assistant:
        asst_config = ASSISTANT_CONFIGS.get(asst.value)
        if asst_config is None:
            continue

        for p in asst_config.get_config_paths():
            if not p.exists():
                continue

            data = read_toml(p) if asst_config.is_toml else read_json(p)
            block = data.get(asst_config.servers_key, {})
            if not isinstance(block, dict):
                continue

            for name, cfg in block.items():
                if not is_valid_name(name):
                    logger.warning(f"Skipping server with invalid name: {name!r}")
                    continue
                if isinstance(cfg, dict):
                    enabled = _is_enabled(asst, asst_config.toggle_method, cfg)
                    servers.append(
                        MCPServer(
                            name=name,
                            assistant=asst,
                            config=cfg,
                            source_file=p,
                            enabled=enabled,
                        )
                    )

        for name, cfg in state.disabled.get(asst.value, {}).items():
            if not is_valid_name(name):
                logger.warning(f"Skipping stashed server with invalid name: {name!r}")
                continue
            if not any(s.name == name and s.assistant == asst for s in servers):
                paths = asst_config.get_config_paths() if asst_config else []
                if not paths:
                    logger.warning(
                        f"No config path for {asst.value}, skipping stashed server {name!r}"
                    )
                    continue
                servers.append(
                    MCPServer(
                        name=name,
                        assistant=asst,
                        config=cfg,
                        source_file=paths[0],
                        enabled=False,
                    )
                )

    return servers


def _is_enabled(asst: Assistant, toggle_method: ToggleMethod, cfg: dict) -> bool:
    """Determine if a server is enabled based on its config and toggle method."""
    if toggle_method == ToggleMethod.NATIVE_DISABLED:
        return not cfg.get("disabled", False)
    if toggle_method == ToggleMethod.NATIVE_ENABLED:
        return cfg.get("enabled", True)
    return True


def _get_skill_dirs() -> list[tuple[Assistant, ItemKind, Path]]:
    """Get list of all skill directories from assistant configs."""
    result = []
    for asst in Assistant:
        asst_config = ASSISTANT_CONFIGS.get(asst.value)
        if asst_config and asst_config.skill_dirs:
            for kind_str, path in asst_config.skill_dirs:
                kind = ItemKind(kind_str) if isinstance(kind_str, str) else kind_str
                result.append((asst, kind, path))
    return result


def _read_desc_from_skill_md(path: Path) -> str:
    """Extract description from a SKILL.md file."""
    try:
        for line in path.read_text("utf-8", errors="replace").splitlines()[:10]:
            if line.startswith("description:"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return ""


def discover_skills() -> list[Skill]:
    """Discover skills/agents from all known directories.

    Skills can be in two states:
    - Enabled: in the assistant's skill directory (e.g., ~/.config/opencode/skills/my-skill/)
    - Disabled: in the central disabled folder (e.g., ~/.local/share/switchboard/disabled/opencode/skills/my-skill/)

    Returns:
        List of Skill instances.
    """
    result: list[Skill] = []
    skill_dirs = _get_skill_dirs()
    disabled_base = get_disabled_skills_dir()

    for asst, kind, d in skill_dirs:
        if not d.exists():
            continue
        try:
            entries = sorted(d.iterdir())
        except OSError as e:
            logger.warning(f"Cannot read skills directory {d}: {e}")
            continue

        for entry in entries:
            if entry.name.startswith(".") or entry.name.endswith(DISABLED_SUFFIX):
                continue

            if entry.is_dir():
                sk_file = entry / "SKILL.md"
                if not sk_file.exists():
                    continue
                actual_name = entry.name
            elif entry.is_file() and entry.suffix == ".md":
                sk_file = entry
                actual_name = entry.stem  # removes .md
            else:
                continue

            desc = _read_desc_from_skill_md(sk_file) if sk_file.exists() else ""
            result.append(
                Skill(
                    name=actual_name,
                    path=entry,
                    assistant=asst,
                    kind=kind,
                    description=desc,
                    enabled=True,
                )
            )

    for asst, kind, _original_dir in skill_dirs:
        # Structure: disabled/<assistant>/<kind>/<skill-name>
        disabled_dir = disabled_base / asst.value / kind.value
        if not disabled_dir.exists():
            continue

        try:
            entries = sorted(disabled_dir.iterdir())
        except OSError as e:
            logger.warning(f"Cannot read disabled skills directory {disabled_dir}: {e}")
            continue

        for entry in entries:
            if entry.name.startswith("."):
                continue

            if entry.is_dir():
                sk_file = entry / "SKILL.md"
                if not sk_file.exists():
                    continue
                actual_name = entry.name
            elif entry.is_file() and entry.suffix == ".md":
                sk_file = entry
                actual_name = entry.stem
            else:
                continue

            desc = _read_desc_from_skill_md(sk_file) if sk_file.exists() else ""
            result.append(
                Skill(
                    name=actual_name,
                    path=entry,
                    assistant=asst,
                    kind=kind,
                    description=desc,
                    enabled=False,
                )
            )

    return result


def toggle_server(server: MCPServer, enable: bool) -> MCPServer:
    """Toggle an MCP server on or off.

    Uses different strategies depending on the assistant:
    - Native disabled flag: Sets 'disabled' field (Cline, RooCode, Gemini)
    - Native enabled flag: Sets 'enabled' field (OpenCode, Codex)
    - State stashing: Moves config to/from state file (Cursor, VS Code, Claude)

    Args:
        server: The server to toggle.
        enable: True to enable, False to disable.

    Returns:
        New MCPServer instance with updated enabled state.

    Raises:
        ServerNotFoundError: If server not found in config when trying to toggle.
    """
    if server.enabled == enable:
        return server  # No change needed

    asst_config = ASSISTANT_CONFIGS.get(server.assistant.value)
    if asst_config is None:
        raise ServerNotFoundError(f"Unknown assistant: {server.assistant}")

    state = load_state()
    data = read_toml(server.source_file) if asst_config.is_toml else read_json(server.source_file)
    key = asst_config.servers_key
    block = data.setdefault(key, {})

    if asst_config.toggle_method == ToggleMethod.NATIVE_DISABLED:
        if server.name in block:
            block[server.name]["disabled"] = not enable
        else:
            logger.warning(f"Server {server.name!r} not found in config, cannot toggle")
            raise ServerNotFoundError(f"Server '{server.name}' not found in {server.source_file}")

    elif asst_config.toggle_method == ToggleMethod.NATIVE_ENABLED:
        if server.name in block:
            block[server.name]["enabled"] = enable
        else:
            logger.warning(f"Server {server.name!r} not found in config, cannot toggle")
            raise ServerNotFoundError(f"Server '{server.name}' not found in {server.source_file}")

    else:
        stash = state.disabled.setdefault(server.assistant.value, {})
        if enable:
            if server.name in stash:
                block[server.name] = stash.pop(server.name)
            elif server.name not in block:
                block[server.name] = server.config
        else:
            if server.name in block:
                stash[server.name] = block.pop(server.name)
            else:
                stash[server.name] = server.config
        save_state(state)

    (write_toml if asst_config.is_toml else write_json)(server.source_file, data)

    return server.with_enabled(enable)


def _get_allowed_skill_parents() -> list[Path]:
    """Get list of allowed parent directories for skills."""
    parents = [d for _, _, d in _get_skill_dirs()]
    disabled_base = get_disabled_skills_dir()
    if disabled_base.exists():
        parents.append(disabled_base)
    return parents


def _get_original_skill_dir(skill: Skill) -> Path:
    """Get the original skill directory for an assistant/kind combination."""
    for asst, kind, d in _get_skill_dirs():
        if asst == skill.assistant and kind == skill.kind:
            return d
    raise ValueError(f"No skill directory found for {skill.assistant}/{skill.kind}")


def toggle_skill(skill: Skill, enable: bool) -> Skill:
    """Toggle a skill/agent on or off by moving to/from disabled folder.

    Uses file locking to prevent TOCTOU race conditions (SECURITY M-2).

    Disabling: moves skill to ~/.local/share/switchboard/disabled/<assistant>/<kind>/
    Enabling: moves skill back to its original location

    This approach completely removes skills from the watched directory, preventing
    AI tools like OpenCode from reading them at all when disabled.

    Args:
        skill: The skill to toggle.
        enable: True to enable, False to disable.

    Returns:
        New Skill instance with updated enabled state and path.

    Raises:
        FileNotFoundError: If skill path doesn't exist.
        FileExistsError: If target path already exists.
        ValueError: If path is a symlink or escapes allowed directories.
    """
    if skill.enabled == enable:
        return skill  # No change needed

    current_path = skill.path

    if not current_path.exists():
        raise FileNotFoundError(f"Skill not found: {current_path}")

    if current_path.is_symlink():
        logger.warning(f"Rejecting symlink skill path: {current_path}")
        raise ValueError(f"Cannot toggle symlink: {current_path}")

    allowed_parents = _get_allowed_skill_parents()
    if not is_path_safe(current_path, allowed_parents):
        logger.warning(f"Skill path escapes allowed directories: {current_path}")
        raise ValueError(f"Path escapes skills directory: {current_path}")

    disabled_base = get_disabled_skills_dir()

    if enable:
        original_dir = _get_original_skill_dir(skill)
        new_path = original_dir / current_path.name
    else:
        disabled_dir = disabled_base / skill.assistant.value / skill.kind.value
        disabled_dir.mkdir(parents=True, exist_ok=True)
        new_path = disabled_dir / current_path.name

    lock_path = current_path.parent / ".switchboard.lock"
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(lock_path, "w") as lock_file:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                try:
                    _perform_skill_move(current_path, new_path)
                finally:
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    _perform_skill_move(current_path, new_path)
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    except (ImportError, OSError) as e:
        logger.warning(f"Could not acquire lock, proceeding without: {e}")
        _perform_skill_move(current_path, new_path)

    return skill.with_enabled(enable, new_path)


def _perform_skill_move(current_path: Path, new_path: Path) -> None:
    """Perform the actual move operation for a skill using staging directory.

    To prevent AI tools from reading corrupted/partial files during the move,
    we use a two-phase move operation:
    1. Move the file/folder to a staging directory (completely out of watched locations)
    2. Move from staging to the final destination

    This ensures the file completely disappears from its source before appearing
    at its destination, preventing any tool from reading an intermediate state.

    Security measures:
    - Symlink check before move (validated in toggle_skill before lock)
    - Symlink check after move to staging (TOCTOU defense)
    - Restrictive permissions on staging directory (Unix)

    Args:
        current_path: Current path of the skill.
        new_path: Target path for the skill.

    Raises:
        FileExistsError: If target path already exists.
        OSError: If move operation fails.
        ValueError: If symlink attack detected.
    """
    import shutil
    import uuid

    if current_path.is_symlink():
        raise ValueError(f"Cannot toggle symlink: {current_path}")

    if new_path.exists():
        raise FileExistsError(f"Cannot toggle: {new_path} already exists")

    staging_dir = get_staging_dir()
    if not staging_dir.exists():
        staging_dir.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            staging_dir.chmod(0o700)

    staging_name = f"{current_path.name}.{uuid.uuid4().hex[:8]}"
    staging_path = staging_dir / staging_name

    try:
        shutil.move(str(current_path), str(staging_path))
    except OSError as e:
        logger.error(f"Failed to move {current_path} to staging: {e}")
        raise

    if staging_path.is_symlink():
        logger.error(f"Symlink detected after move to staging: {staging_path}")
        staging_path.unlink()
        raise ValueError(f"Symlink attack detected: {current_path}")

    try:
        shutil.move(str(staging_path), str(new_path))
    except OSError as e:
        logger.error(f"Failed to move from staging to {new_path}: {e}")
        try:
            shutil.move(str(staging_path), str(current_path))
            logger.info(f"Restored {current_path} after failed move")
        except OSError as restore_err:
            logger.error(f"Failed to restore {current_path}: {restore_err}")
        raise


# Async versions of functions (ARCH M4 - non-blocking UI)


async def discover_servers_async() -> list[MCPServer]:
    """Async version of discover_servers - runs in thread pool to avoid blocking UI."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_get_executor(), discover_servers)


async def discover_skills_async() -> list[Skill]:
    """Async version of discover_skills - runs in thread pool to avoid blocking UI."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_get_executor(), discover_skills)


async def toggle_server_async(server: MCPServer, enable: bool) -> MCPServer:
    """Async version of toggle_server - runs in thread pool to avoid blocking UI."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_get_executor(), partial(toggle_server, server, enable))


async def toggle_skill_async(skill: Skill, enable: bool) -> Skill:
    """Async version of toggle_skill - runs in thread pool to avoid blocking UI."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_get_executor(), partial(toggle_skill, skill, enable))
