"""Configuration management subpackage for Switchboard."""

from .assistants import ASSISTANT_CONFIGS, AssistantConfig, ToggleMethod
from .io import read_json, read_toml, write_json, write_toml
from .paths import (
    cleanup_staging_dir,
    get_appdata,
    get_disabled_skills_dir,
    get_home,
    get_staging_dir,
    get_state_dir,
    get_state_file,
)
from .security import (
    MAX_NAME_LENGTH,
    VALID_NAME_PATTERN,
    is_path_safe,
    is_valid_name,
    validate_config_structure,
)
from .state import load_state, save_state

__all__ = [
    "ASSISTANT_CONFIGS",
    "AssistantConfig",
    "ToggleMethod",
    "read_json",
    "write_json",
    "read_toml",
    "write_toml",
    "get_home",
    "get_appdata",
    "get_state_dir",
    "get_state_file",
    "get_staging_dir",
    "get_disabled_skills_dir",
    "cleanup_staging_dir",
    "is_valid_name",
    "validate_config_structure",
    "is_path_safe",
    "VALID_NAME_PATTERN",
    "MAX_NAME_LENGTH",
    "load_state",
    "save_state",
]
