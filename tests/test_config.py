"""Unit tests for Switchboard config management."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from unittest.mock import patch

import pytest

# Test I/O utilities
from switchboard.config.io import read_json, write_json

# Test security utilities
from switchboard.config.security import (
    MAX_ARRAY_LENGTH,
    MAX_CONFIG_DEPTH,
    is_path_safe,
    is_valid_name,
    validate_config_structure,
)

# Test models
from switchboard.models import Assistant, ItemKind, MCPServer, Skill


class TestIsValidName:
    """Tests for name validation."""

    def test_valid_names(self):
        assert is_valid_name("my-server")
        assert is_valid_name("my_server")
        assert is_valid_name("MyServer123")
        assert is_valid_name("server.v2")
        assert is_valid_name("a")

    def test_invalid_names(self):
        assert not is_valid_name("")
        assert not is_valid_name(None)  # type: ignore
        assert not is_valid_name("my server")  # space
        assert not is_valid_name("my/server")  # path separator
        assert not is_valid_name("my\\server")  # backslash
        assert not is_valid_name("server$")  # special char
        assert not is_valid_name("../escape")  # path traversal

    def test_length_limit(self):
        assert is_valid_name("a" * 128)
        assert not is_valid_name("a" * 129)


class TestValidateConfigStructure:
    """Tests for config structure validation (DoS prevention)."""

    def test_simple_config(self):
        config = {"key": "value", "nested": {"a": 1}}
        assert validate_config_structure(config)

    def test_exceeds_depth(self):
        # Create deeply nested structure
        config = {"level": {}}
        current = config["level"]
        for _ in range(MAX_CONFIG_DEPTH + 5):
            current["next"] = {}
            current = current["next"]
        assert not validate_config_structure(config)

    def test_exceeds_array_length(self):
        config = {"data": list(range(MAX_ARRAY_LENGTH + 100))}
        assert not validate_config_structure(config)

    def test_valid_array(self):
        config = {"data": list(range(100))}
        assert validate_config_structure(config)


class TestIsPathSafe:
    """Tests for path safety checks."""

    def test_path_within_allowed(self, tmp_path):
        allowed = [tmp_path / "skills"]
        allowed[0].mkdir()
        test_path = allowed[0] / "my-skill"
        test_path.mkdir()
        assert is_path_safe(test_path, allowed)

    def test_path_outside_allowed(self, tmp_path):
        allowed = [tmp_path / "skills"]
        allowed[0].mkdir()
        test_path = tmp_path / "other" / "my-skill"
        test_path.parent.mkdir()
        test_path.mkdir()
        assert not is_path_safe(test_path, allowed)

    def test_path_traversal_attempt(self, tmp_path):
        allowed = [tmp_path / "skills"]
        allowed[0].mkdir()
        # Attempt to escape via ..
        test_path = allowed[0] / ".." / "other"
        assert not is_path_safe(test_path, allowed)

    def test_similar_prefix_not_allowed(self, tmp_path):
        """Ensure skills-evil doesn't match skills prefix."""
        allowed = [tmp_path / "skills"]
        allowed[0].mkdir()
        evil_path = tmp_path / "skills-evil" / "my-skill"
        evil_path.parent.mkdir()
        evil_path.mkdir()
        assert not is_path_safe(evil_path, allowed)


class TestReadWriteJson:
    """Tests for JSON I/O."""

    def test_write_and_read(self, tmp_path):
        test_file = tmp_path / "test.json"
        data = {"key": "value", "nested": {"a": 1}}
        write_json(test_file, data)
        result = read_json(test_file)
        assert result == data

    def test_read_nonexistent(self, tmp_path):
        test_file = tmp_path / "nonexistent.json"
        result = read_json(test_file)
        assert result == {}

    def test_read_malformed(self, tmp_path):
        test_file = tmp_path / "malformed.json"
        test_file.write_text("{ invalid json }")
        result = read_json(test_file)
        assert result == {}

    def test_atomic_write(self, tmp_path):
        """Verify atomic write doesn't leave partial files."""
        test_file = tmp_path / "atomic.json"
        data = {"key": "value"}
        write_json(test_file, data)

        # Check no temp files left behind
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0


class TestMCPServer:
    """Tests for MCPServer model."""

    def test_immutable(self):
        server = MCPServer(
            name="test",
            assistant=Assistant.CURSOR,
            config={"command": "echo"},
            source_file=Path("/test"),
            enabled=True,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            server.enabled = False  # type: ignore

    def test_with_enabled(self):
        server = MCPServer(
            name="test",
            assistant=Assistant.CURSOR,
            config={"command": "echo"},
            source_file=Path("/test"),
            enabled=True,
        )
        disabled = server.with_enabled(False)
        assert disabled.enabled is False
        assert server.enabled is True  # Original unchanged

    def test_summary(self):
        server = MCPServer(
            name="test",
            assistant=Assistant.CURSOR,
            config={"command": "npx", "args": ["-y", "some-package"]},
            source_file=Path("/test"),
        )
        assert "npx" in server.summary
        assert "-y" in server.summary


class TestSkill:
    """Tests for Skill model."""

    def test_immutable(self):
        skill = Skill(
            name="test",
            path=Path("/test"),
            assistant=Assistant.OPENCODE,
            enabled=True,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            skill.enabled = False  # type: ignore

    def test_with_enabled(self):
        skill = Skill(
            name="test",
            path=Path("/test/skill"),
            assistant=Assistant.OPENCODE,
            enabled=True,
        )
        new_path = Path("/test/skill.disabled")
        disabled = skill.with_enabled(False, new_path)
        assert disabled.enabled is False
        assert disabled.path == new_path
        assert skill.enabled is True  # Original unchanged
        assert skill.path == Path("/test/skill")  # Original unchanged


# Integration tests that require more setup
class TestToggleServerIntegration:
    """Integration tests for server toggling."""

    def test_toggle_native_disabled(self, tmp_path, monkeypatch):
        """Test toggling server with native disabled flag (Cline style)."""
        # Create a mock config file
        config_file = tmp_path / "cline_mcp_settings.json"
        config_data = {"mcpServers": {"test-server": {"command": "echo", "args": ["hello"]}}}
        config_file.write_text(json.dumps(config_data))

        # Mock the config paths to use our temp file
        from switchboard.config import assistants

        original_configs = assistants._assistant_configs
        assistants._assistant_configs = None

        try:
            # Create server pointing to our test file
            server = MCPServer(
                name="test-server",
                assistant=Assistant.CLINE,
                config={"command": "echo", "args": ["hello"]},
                source_file=config_file,
                enabled=True,
            )

            # Import after mocking
            from switchboard import config_manager as cm

            # Toggle off
            updated = cm.toggle_server(server, False)
            assert updated.enabled is False

            # Verify file was updated
            result = json.loads(config_file.read_text())
            assert result["mcpServers"]["test-server"]["disabled"] is True

            # Toggle back on
            updated2 = cm.toggle_server(updated, True)
            assert updated2.enabled is True

            result2 = json.loads(config_file.read_text())
            assert result2["mcpServers"]["test-server"]["disabled"] is False
        finally:
            assistants._assistant_configs = original_configs

    def test_toggle_native_enabled(self, tmp_path):
        """Test toggling server with native enabled flag (OpenCode style)."""
        config_file = tmp_path / "opencode.json"
        # OpenCode uses "mcp" key with nested server configs
        config_data = {"mcp": {"test-server": {"command": ["npx", "-y", "test"], "enabled": True}}}
        config_file.write_text(json.dumps(config_data))

        server = MCPServer(
            name="test-server",
            assistant=Assistant.OPENCODE,
            config={"command": ["npx", "-y", "test"], "enabled": True},
            source_file=config_file,
            enabled=True,
        )

        from switchboard import config_manager as cm

        # Toggle off
        updated = cm.toggle_server(server, False)
        assert updated.enabled is False

        result = json.loads(config_file.read_text())
        assert result["mcp"]["test-server"]["enabled"] is False

        # Toggle back on
        updated2 = cm.toggle_server(updated, True)
        assert updated2.enabled is True

        result2 = json.loads(config_file.read_text())
        assert result2["mcp"]["test-server"]["enabled"] is True

    def test_toggle_stash_method(self, tmp_path):
        """Test toggling server with stash method (Cursor/VS Code/Claude style)."""
        config_file = tmp_path / "mcp.json"
        state_file = tmp_path / "state.json"
        config_data = {"mcpServers": {"test-server": {"command": "echo", "args": ["hello"]}}}
        config_file.write_text(json.dumps(config_data))
        state_file.write_text("{}")

        server = MCPServer(
            name="test-server",
            assistant=Assistant.CURSOR,
            config={"command": "echo", "args": ["hello"]},
            source_file=config_file,
            enabled=True,
        )

        from switchboard import config_manager as cm
        from switchboard.config import state as state_module

        # Mock state file location
        original_get_state_file = state_module.get_state_file
        state_module.get_state_file = lambda: state_file

        try:
            # Toggle off - should stash config and remove from file
            updated = cm.toggle_server(server, False)
            assert updated.enabled is False

            # Verify config was removed from file
            result = json.loads(config_file.read_text())
            assert "test-server" not in result.get("mcpServers", {})

            # Verify config was stashed (uses lowercase assistant value "cursor")
            state_data = json.loads(state_file.read_text())
            assert "cursor" in state_data.get("disabled", {})
            assert "test-server" in state_data["disabled"]["cursor"]

            # Toggle back on - should restore from stash
            updated2 = cm.toggle_server(updated, True)
            assert updated2.enabled is True

            result2 = json.loads(config_file.read_text())
            assert "test-server" in result2["mcpServers"]
            assert result2["mcpServers"]["test-server"]["command"] == "echo"

        finally:
            state_module.get_state_file = original_get_state_file

    def test_toggle_idempotent(self, tmp_path):
        """Test that toggling to same state is idempotent (no-op)."""
        config_file = tmp_path / "test.json"
        config_data = {"mcpServers": {"test-server": {"command": "echo"}}}
        config_file.write_text(json.dumps(config_data))

        server = MCPServer(
            name="test-server",
            assistant=Assistant.CLINE,
            config={"command": "echo"},
            source_file=config_file,
            enabled=True,
        )

        from switchboard import config_manager as cm

        # Toggle to same state should return same object (identity check)
        result = cm.toggle_server(server, True)
        assert result is server  # Same object, not a copy

    def test_toggle_server_not_found_raises(self, tmp_path):
        """Test that toggling non-existent server raises ServerNotFoundError."""
        config_file = tmp_path / "test.json"
        config_data = {"mcpServers": {}}
        config_file.write_text(json.dumps(config_data))

        server = MCPServer(
            name="nonexistent",
            assistant=Assistant.CLINE,  # Uses NATIVE_DISABLED
            config={"command": "echo"},
            source_file=config_file,
            enabled=True,
        )

        from switchboard import config_manager as cm

        with pytest.raises(cm.ServerNotFoundError):
            cm.toggle_server(server, False)


class TestToggleSkillIntegration:
    """Integration tests for skill toggling."""

    def test_toggle_skill_directory(self, tmp_path, monkeypatch):
        """Test toggling a skill directory moves it to disabled folder."""
        # Create a mock skills directory
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        skill_path = skills_dir / "my-skill"
        skill_path.mkdir()
        (skill_path / "SKILL.md").write_text("description: Test skill")

        # Create disabled directory structure
        disabled_dir = tmp_path / "disabled" / "opencode" / "skill"
        disabled_dir.mkdir(parents=True)

        # Create skill object
        skill = Skill(
            name="my-skill",
            path=skill_path,
            assistant=Assistant.OPENCODE,
            kind=ItemKind.SKILL,
            description="Test skill",
            enabled=True,
        )

        from switchboard import config_manager as cm

        # Mock functions to use our temp dirs
        with patch.object(
            cm, "_get_allowed_skill_parents", return_value=[skills_dir, disabled_dir.parent.parent]
        ):
            with patch.object(cm, "_get_original_skill_dir", return_value=skills_dir):
                with patch.object(
                    cm, "get_disabled_skills_dir", return_value=tmp_path / "disabled"
                ):
                    # Toggle off (should move to disabled folder)
                    disabled = cm.toggle_skill(skill, False)
                    assert disabled.enabled is False
                    assert disabled.path.name == "my-skill"
                    assert disabled.path.parent == disabled_dir
                    assert disabled.path.exists()
                    assert not skill_path.exists()

                    # Toggle back on (should move back to skills dir)
                    enabled = cm.toggle_skill(disabled, True)
                    assert enabled.enabled is True
                    assert enabled.path.name == "my-skill"
                    assert enabled.path.parent == skills_dir
                    assert enabled.path.exists()

    def test_toggle_skill_file(self, tmp_path):
        """Test toggling a single-file skill (.md file)."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        skill_file = skills_dir / "simple-skill.md"
        skill_file.write_text("description: A simple skill")

        # Create disabled directory structure
        disabled_dir = tmp_path / "disabled" / "opencode" / "skill"
        disabled_dir.mkdir(parents=True)

        skill = Skill(
            name="simple-skill",
            path=skill_file,
            assistant=Assistant.OPENCODE,
            kind=ItemKind.SKILL,
            description="A simple skill",
            enabled=True,
        )

        from switchboard import config_manager as cm

        with patch.object(
            cm, "_get_allowed_skill_parents", return_value=[skills_dir, disabled_dir.parent.parent]
        ):
            with patch.object(cm, "_get_original_skill_dir", return_value=skills_dir):
                with patch.object(
                    cm, "get_disabled_skills_dir", return_value=tmp_path / "disabled"
                ):
                    # Toggle off
                    disabled = cm.toggle_skill(skill, False)
                    assert disabled.enabled is False
                    assert disabled.path.name == "simple-skill.md"
                    assert disabled.path.parent == disabled_dir
                    assert disabled.path.exists()
                    assert not skill_file.exists()

                    # Toggle back on
                    enabled = cm.toggle_skill(disabled, True)
                    assert enabled.enabled is True
                    assert enabled.path.name == "simple-skill.md"
                    assert enabled.path.parent == skills_dir
                    assert enabled.path.exists()

    def test_toggle_skill_idempotent(self, tmp_path):
        """Test that toggling to same state is idempotent."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        skill_path = skills_dir / "test-skill"
        skill_path.mkdir()
        (skill_path / "SKILL.md").write_text("description: Test")

        skill = Skill(
            name="test-skill",
            path=skill_path,
            assistant=Assistant.OPENCODE,
            enabled=True,
        )

        from switchboard import config_manager as cm

        with patch.object(cm, "_get_allowed_skill_parents", return_value=[skills_dir]):
            # Toggle to same state should return same object
            result = cm.toggle_skill(skill, True)
            assert result is skill

    def test_toggle_skill_rejects_symlink(self, tmp_path, monkeypatch):
        """Test that symlink skills are rejected."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        real_skill = tmp_path / "real-skill"
        real_skill.mkdir()
        (real_skill / "SKILL.md").write_text("description: Real")

        # Create symlink
        symlink_path = skills_dir / "symlink-skill"
        try:
            symlink_path.symlink_to(real_skill)
        except OSError:
            pytest.skip("Symlinks not supported on this platform")

        skill = Skill(
            name="symlink-skill",
            path=symlink_path,
            assistant=Assistant.OPENCODE,
            enabled=True,
        )

        from switchboard import config_manager as cm

        with patch.object(cm, "_get_allowed_skill_parents", return_value=[skills_dir]):
            with pytest.raises(ValueError, match="symlink"):
                cm.toggle_skill(skill, False)

    def test_toggle_skill_rejects_path_escape(self, tmp_path):
        """Test that path traversal is rejected."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        evil_dir = tmp_path / "evil"
        evil_dir.mkdir()
        evil_skill = evil_dir / "bad-skill"
        evil_skill.mkdir()
        (evil_skill / "SKILL.md").write_text("description: Evil")

        skill = Skill(
            name="bad-skill",
            path=evil_skill,
            assistant=Assistant.OPENCODE,
            enabled=True,
        )

        from switchboard import config_manager as cm

        with patch.object(cm, "_get_allowed_skill_parents", return_value=[skills_dir]):
            with pytest.raises(ValueError, match="escapes"):
                cm.toggle_skill(skill, False)

    def test_toggle_skill_nonexistent_raises(self, tmp_path):
        """Test that toggling non-existent skill raises FileNotFoundError."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        skill = Skill(
            name="ghost",
            path=skills_dir / "ghost",
            assistant=Assistant.OPENCODE,
            enabled=True,
        )

        from switchboard import config_manager as cm

        with patch.object(cm, "_get_allowed_skill_parents", return_value=[skills_dir]):
            with pytest.raises(FileNotFoundError):
                cm.toggle_skill(skill, False)

    def test_toggle_skill_target_exists_raises(self, tmp_path):
        """Test that toggling to existing target raises FileExistsError."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        skill_path = skills_dir / "my-skill"
        skill_path.mkdir()
        (skill_path / "SKILL.md").write_text("description: Original")

        # Create the disabled target too (conflict)
        disabled_base = tmp_path / "state" / "disabled"
        disabled_dir = disabled_base / "opencode" / "skill"
        disabled_dir.mkdir(parents=True)
        disabled_path = disabled_dir / "my-skill"
        disabled_path.mkdir()
        (disabled_path / "SKILL.md").write_text("description: Conflicting")

        staging_dir = tmp_path / "state" / ".staging"

        skill = Skill(
            name="my-skill",
            path=skill_path,
            assistant=Assistant.OPENCODE,
            enabled=True,
        )

        from switchboard import config_manager as cm

        with (
            patch.object(
                cm, "_get_allowed_skill_parents", return_value=[skills_dir, disabled_base]
            ),
            patch.object(cm, "get_disabled_skills_dir", return_value=disabled_base),
            patch.object(cm, "get_staging_dir", return_value=staging_dir),
        ):
            with pytest.raises(FileExistsError):
                cm.toggle_skill(skill, False)


class TestAsyncFunctions:
    """Tests for async versions of functions."""

    @pytest.mark.asyncio
    async def test_discover_servers_async(self, tmp_path, monkeypatch):
        """Test async server discovery."""
        from switchboard import config_manager as cm

        # Just verify it runs without error
        servers = await cm.discover_servers_async()
        assert isinstance(servers, list)

    @pytest.mark.asyncio
    async def test_discover_skills_async(self):
        """Test async skill discovery."""
        from switchboard import config_manager as cm

        skills = await cm.discover_skills_async()
        assert isinstance(skills, list)

    @pytest.mark.asyncio
    async def test_toggle_server_async(self, tmp_path):
        """Test async server toggle."""
        config_file = tmp_path / "test.json"
        config_data = {"mcpServers": {"async-server": {"command": "echo"}}}
        config_file.write_text(json.dumps(config_data))

        server = MCPServer(
            name="async-server",
            assistant=Assistant.CLINE,
            config={"command": "echo"},
            source_file=config_file,
            enabled=True,
        )

        from switchboard import config_manager as cm

        updated = await cm.toggle_server_async(server, False)
        assert updated.enabled is False

        result = json.loads(config_file.read_text())
        assert result["mcpServers"]["async-server"]["disabled"] is True

    @pytest.mark.asyncio
    async def test_toggle_skill_async(self, tmp_path):
        """Test async skill toggle moves to disabled folder."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        skill_path = skills_dir / "async-skill"
        skill_path.mkdir()
        (skill_path / "SKILL.md").write_text("description: Async test")

        # Create disabled directory structure
        disabled_dir = tmp_path / "disabled" / "opencode" / "skill"
        disabled_dir.mkdir(parents=True)

        skill = Skill(
            name="async-skill",
            path=skill_path,
            assistant=Assistant.OPENCODE,
            kind=ItemKind.SKILL,
            enabled=True,
        )

        from switchboard import config_manager as cm

        with patch.object(
            cm, "_get_allowed_skill_parents", return_value=[skills_dir, disabled_dir.parent.parent]
        ):
            with patch.object(cm, "_get_original_skill_dir", return_value=skills_dir):
                with patch.object(
                    cm, "get_disabled_skills_dir", return_value=tmp_path / "disabled"
                ):
                    updated = await cm.toggle_skill_async(skill, False)
                    assert updated.enabled is False
                    assert updated.path.name == "async-skill"
                    assert updated.path.parent == disabled_dir


class TestStateManagement:
    """Tests for state file operations."""

    def test_load_state_creates_defaults(self, tmp_path):
        """Test that loading non-existent state returns defaults."""
        from switchboard.config import state as state_module

        original = state_module.get_state_file
        state_module.get_state_file = lambda: tmp_path / "nonexistent" / "state.json"

        try:
            from switchboard.config.state import load_state

            s = load_state()
            assert s.disabled == {}
        finally:
            state_module.get_state_file = original

    def test_save_and_load_state(self, tmp_path):
        """Test state persistence round-trip."""
        state_file = tmp_path / "state.json"

        from switchboard.config import state as state_module
        from switchboard.models import AppState

        original = state_module.get_state_file
        state_module.get_state_file = lambda: state_file

        try:
            from switchboard.config.state import load_state, save_state

            # Save state
            s = AppState(disabled={"cursor": {"test": {"cmd": "echo"}}})
            save_state(s)

            # Load it back
            loaded = load_state()
            assert loaded.disabled == {"cursor": {"test": {"cmd": "echo"}}}
        finally:
            state_module.get_state_file = original


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

    def test_save_and_load_state(self, tmp_path):
        """Test state persistence round-trip."""
        state_file = tmp_path / "state.json"

        from switchboard.config import state as state_module
        from switchboard.models import AppState

        original = state_module.get_state_file
        state_module.get_state_file = lambda: state_file

        try:
            from switchboard.config.state import load_state, save_state

            # Save state
            s = AppState(disabled={"cursor": {"test": {"cmd": "echo"}}})
            save_state(s)

            # Load it back
            loaded = load_state()
            assert loaded.disabled == {"cursor": {"test": {"cmd": "echo"}}}
        finally:
            state_module.get_state_file = original
