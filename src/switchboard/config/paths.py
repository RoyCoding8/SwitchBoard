"""Platform-aware path resolution for Switchboard.

Handles HOME validation, XDG base directory support, and platform-specific paths.
"""

from __future__ import annotations

import logging
import os
import platform
from pathlib import Path

logger = logging.getLogger(__name__)

SYSTEM = platform.system()

_validated_home: Path | None = None


def get_home() -> Path:
    """Get validated home directory with security checks.

    Security measures:
    - Validates HOME is an actual directory
    - On Unix, verifies ownership matches current user
    - Caches result to avoid repeated validation

    Raises:
        RuntimeError: If HOME is invalid or not owned by current user.
    """
    global _validated_home

    if _validated_home is not None:
        return _validated_home

    home = Path.home()

    if not home.is_dir():
        raise RuntimeError(f"HOME is not a valid directory: {home}")

    if os.name != "nt":
        try:
            home_stat = home.stat()
            if home_stat.st_uid != os.getuid():
                raise RuntimeError(
                    f"HOME directory not owned by current user: {home} "
                    f"(owned by uid {home_stat.st_uid}, current uid {os.getuid()})"
                )
        except OSError as e:
            raise RuntimeError(f"Cannot verify HOME directory ownership: {e}") from e

    _validated_home = home
    return home


def get_appdata() -> Path:
    """Get platform-specific application data directory."""
    home = get_home()
    if SYSTEM == "Windows":
        return Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
    return home / "Library" / "Application Support" if SYSTEM == "Darwin" else home / ".config"


def get_state_dir() -> Path:
    """Get Switchboard state directory with XDG support (ARCH M3).

    Follows XDG Base Directory Specification on Linux:
    - Linux: $XDG_DATA_HOME/switchboard or ~/.local/share/switchboard
    - macOS: ~/Library/Application Support/switchboard
    - Windows: %LOCALAPPDATA%/switchboard or ~/AppData/Local/switchboard
    """
    home = get_home()

    if SYSTEM == "Linux":
        xdg_data = os.environ.get("XDG_DATA_HOME")
        if xdg_data:
            return Path(xdg_data) / "switchboard"
        return home / ".local" / "share" / "switchboard"
    elif SYSTEM == "Darwin":
        return home / "Library" / "Application Support" / "switchboard"
    else:  # Windows
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            return Path(local_appdata) / "switchboard"
        return home / "AppData" / "Local" / "switchboard"


def get_state_file() -> Path:
    """Get path to Switchboard state file."""
    return get_state_dir() / "state.json"


def get_staging_dir() -> Path:
    """Get temporary staging directory for atomic file moves.

    Used during skill/agent toggling to prevent AI tools from reading
    files mid-rename. Files are moved here first, then to final destination.

    This ensures the file completely disappears from its source location
    before appearing at the destination, preventing partial/corrupt reads.

    Returns:
        Path to staging directory within Switchboard state directory.
    """
    return get_state_dir() / ".staging"


def get_disabled_skills_dir() -> Path:
    """Get directory for storing disabled skills/agents.

    Disabled skills are moved here instead of being renamed with a suffix.
    This prevents AI tools (like OpenCode) from reading disabled skills,
    as they only watch the active skills directories.

    Returns:
        Path to disabled skills directory within Switchboard state directory.
    """
    return get_state_dir() / "disabled"


def cleanup_staging_dir() -> None:
    """Clean up any leftover files in the staging directory.

    Called on startup to handle interrupted operations. Any files found
    in staging are orphans from failed operations and should be removed.

    Security: Refuses to follow symlinks to prevent symlink attacks where
    an attacker plants a symlink that would cause deletion of arbitrary files.
    """
    staging = get_staging_dir()
    if not staging.exists():
        return

    import shutil

    for item in staging.iterdir():
        try:
            if item.is_symlink():
                logger.warning(f"Refusing to follow symlink in staging, removing: {item}")
                item.unlink()  # Remove the symlink itself, not the target
            elif item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            logger.info(f"Cleaned up orphaned staging item: {item}")
        except OSError as e:
            logger.warning(f"Failed to clean staging item {item}: {e}")


# Legacy compatibility - some code may still import these directly
HOME = property(lambda self: get_home())
