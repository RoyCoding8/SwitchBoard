"""File I/O utilities for Switchboard.

Provides atomic read/write operations for JSON and TOML files.
Includes async versions for non-blocking UI operations.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import stat
import tempfile
import tomllib
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
from typing import Any

from .security import validate_config_structure

logger = logging.getLogger(__name__)

_io_executor: ThreadPoolExecutor | None = None


def _get_io_executor() -> ThreadPoolExecutor:
    """Get or create the shared I/O thread pool."""
    global _io_executor
    if _io_executor is None:
        _io_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="switchboard-io")
    return _io_executor


def read_json(p: Path, validate: bool = True) -> dict:
    """Read JSON file safely, returning empty dict on error.

    Args:
        p: Path to JSON file.
        validate: If True, validates structure against DoS limits.

    Returns:
        Parsed JSON as dict, or empty dict on error.
    """
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text("utf-8", errors="replace"))
        if validate and isinstance(data, dict) and not validate_config_structure(data):
            logger.warning(f"Config in {p} exceeds structure limits, returning empty")
            return {}
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError as e:
        # Log only error type and position, not content (SECURITY: avoid log leakage)
        logger.warning(f"Malformed JSON in {p}: {type(e).__name__} at line {e.lineno}")
        return {}


def write_json(p: Path, data: dict) -> None:
    """Write JSON atomically using temp file + rename pattern.

    Security measures:
    - Creates temp file in same directory (ensures same filesystem for atomic rename)
    - Sets restrictive permissions (0600) before writing
    - Cleans up temp file on failure

    Args:
        p: Path to write to.
        data: Data to serialize as JSON.
    """
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
    try:
        # Ensure restrictive permissions (owner read/write only)
        os.chmod(fd, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        Path(temp_path).replace(p)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def read_toml(p: Path, validate: bool = True) -> dict:
    """Read TOML file safely, returning empty dict on error.

    Args:
        p: Path to TOML file.
        validate: If True, validates structure against DoS limits.

    Returns:
        Parsed TOML as dict, or empty dict on error.
    """
    if not p.exists():
        return {}
    try:
        with open(p, "rb") as f:
            data = tomllib.load(f)
        if validate and not validate_config_structure(data):
            logger.warning(f"Config in {p} exceeds structure limits, returning empty")
            return {}
        return data
    except tomllib.TOMLDecodeError as e:
        logger.warning(f"Malformed TOML in {p}: {type(e).__name__}")
        return {}


def _toml_val(v: Any) -> str:
    """Convert a Python value to TOML string representation with proper escaping."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        escaped = (
            v.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
        )
        return f'"{escaped}"'
    if isinstance(v, list):
        return "[" + ", ".join(_toml_val(i) for i in v) + "]"
    if isinstance(v, (int, float)):
        return str(v)
    # For unknown types, convert to string with escaping
    return _toml_val(str(v))


def write_toml(p: Path, data: dict) -> None:
    """Write TOML atomically using temp file + rename pattern.

    Args:
        p: Path to write to.
        data: Data to serialize as TOML.
    """
    lines: list[str] = []
    for section, entries in data.items():
        if isinstance(entries, dict) and all(isinstance(v, dict) for v in entries.values()):
            for name, cfg in entries.items():
                lines.append(f"\n[{section}.{name}]")
                for k, v in cfg.items():
                    if isinstance(v, dict):
                        lines.append(f"\n[{section}.{name}.{k}]")
                        for dk, dv in v.items():
                            lines.append(f"{dk} = {_toml_val(dv)}")
                    else:
                        lines.append(f"{k} = {_toml_val(v)}")
        else:
            lines.append(f"\n[{section}]")
            for k, v in entries.items():
                lines.append(f"{k} = {_toml_val(v)}")

    p.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
    try:
        os.chmod(fd, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(lines).strip() + "\n")
        Path(temp_path).replace(p)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


# Async versions of I/O functions (ARCH M4)


async def read_json_async(p: Path, validate: bool = True) -> dict:
    """Async version of read_json - runs in thread pool to avoid blocking."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_get_io_executor(), partial(read_json, p, validate))


async def write_json_async(p: Path, data: dict) -> None:
    """Async version of write_json - runs in thread pool to avoid blocking."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(_get_io_executor(), partial(write_json, p, data))


async def read_toml_async(p: Path, validate: bool = True) -> dict:
    """Async version of read_toml - runs in thread pool to avoid blocking."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_get_io_executor(), partial(read_toml, p, validate))


async def write_toml_async(p: Path, data: dict) -> None:
    """Async version of write_toml - runs in thread pool to avoid blocking."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(_get_io_executor(), partial(write_toml, p, data))
