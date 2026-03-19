"""State persistence for Switchboard.

Handles loading and saving application state to the state file.
"""

from __future__ import annotations

from ..models import AppState
from .io import read_json, write_json
from .paths import get_state_file


def load_state() -> AppState:
    """Load application state from state file.

    Returns:
        AppState with loaded data, or default empty state if file doesn't exist.
    """
    state_file = get_state_file()
    raw = read_json(state_file, validate=True)
    return AppState(
        disabled=raw.get("disabled", {}),
        disabled_skills=raw.get("disabled_skills", []),
    )


def save_state(state: AppState) -> None:
    """Save application state to state file.

    Args:
        state: The AppState to persist.
    """
    state_file = get_state_file()
    write_json(
        state_file,
        {"disabled": state.disabled, "disabled_skills": state.disabled_skills},
    )
