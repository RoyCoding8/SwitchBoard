"""Security utilities for Switchboard.

Provides input validation, path safety checks, and config structure validation.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Pattern for valid server/skill names (alphanumeric, dash, underscore, dot)
VALID_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.]+$")
MAX_NAME_LENGTH = 128

# Limits for config validation (DoS prevention)
MAX_CONFIG_DEPTH = 10
MAX_ARRAY_LENGTH = 1000
MAX_DICT_KEYS = 500


def is_valid_name(name: str) -> bool:
    """Validate a server or skill name contains only safe characters.

    Uses whitelist approach: only allows alphanumeric, dash, underscore, dot.
    Also enforces maximum length to prevent DoS.

    Args:
        name: The name to validate.

    Returns:
        True if name is valid, False otherwise.
    """
    if not name or not isinstance(name, str):
        return False
    return bool(VALID_NAME_PATTERN.match(name)) and len(name) <= MAX_NAME_LENGTH


def validate_config_structure(
    obj: Any,
    depth: int = 0,
    max_depth: int = MAX_CONFIG_DEPTH,
    max_array: int = MAX_ARRAY_LENGTH,
    max_keys: int = MAX_DICT_KEYS,
) -> bool:
    """Validate config structure to prevent DoS attacks (SECURITY M-4).

    Checks:
    - Maximum nesting depth
    - Maximum array length
    - Maximum dictionary keys

    Args:
        obj: The object to validate.
        depth: Current nesting depth.
        max_depth: Maximum allowed nesting depth.
        max_array: Maximum allowed array length.
        max_keys: Maximum allowed dictionary keys.

    Returns:
        True if structure is valid, False if it exceeds limits.
    """
    if depth > max_depth:
        logger.warning(f"Config exceeds max depth of {max_depth}")
        return False

    if isinstance(obj, dict):
        if len(obj) > max_keys:
            logger.warning(f"Config dict has {len(obj)} keys, exceeds limit of {max_keys}")
            return False
        return all(
            validate_config_structure(v, depth + 1, max_depth, max_array, max_keys)
            for v in obj.values()
        )

    if isinstance(obj, list):
        if len(obj) > max_array:
            logger.warning(f"Config array has {len(obj)} items, exceeds limit of {max_array}")
            return False
        return all(
            validate_config_structure(v, depth + 1, max_depth, max_array, max_keys) for v in obj
        )

    # Primitive types are always valid
    return True


def is_path_safe(path: Path, allowed_parents: list[Path]) -> bool:
    """Check if path is safely contained within allowed directories (SECURITY M-1).

    Uses proper path relationship checking instead of string prefix matching.
    This prevents bypasses via:
    - Case differences on case-insensitive filesystems
    - Similar path prefixes (e.g., /skills vs /skills-evil)

    Args:
        path: The path to check.
        allowed_parents: List of allowed parent directories.

    Returns:
        True if path is safely contained within an allowed parent.
    """
    try:
        resolved = path.resolve()
        for parent in allowed_parents:
            if not parent.exists():
                continue
            resolved_parent = parent.resolve()
            try:
                # relative_to() raises ValueError if path is not relative to parent
                resolved.relative_to(resolved_parent)
                return True
            except ValueError:
                continue
        return False
    except OSError as e:
        logger.warning(f"Cannot resolve path {path}: {e}")
        return False
