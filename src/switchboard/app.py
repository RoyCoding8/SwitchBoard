"""Switchboard — Textual TUI Application.

Uses async workers for non-blocking file operations.
"""

from __future__ import annotations

import logging

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import (
    Footer,
    Header,
    Label,
    Static,
    Switch,
    TabbedContent,
    TabPane,
)

from . import config_manager as cm
from .config import cleanup_staging_dir
from .config_manager import ServerNotFoundError
from .models import Assistant, ItemKind, MCPServer, Skill

logger = logging.getLogger(__name__)

DESCRIPTION_MAX_LENGTH = 60

ROW_CSS = """
height: 3; padding: 0 1; background: $surface; margin-bottom: 1;
&:hover { background: $surface-lighten-1; }
.name { width: 1fr; content-align: left middle; }
.info { width: 2fr; color: $text-muted; content-align: left middle; }
Switch { width: auto; }
"""


class ServerRow(Horizontal):
    """Row widget for displaying and toggling an MCP server."""

    DEFAULT_CSS = "ServerRow { " + ROW_CSS + " }"

    def __init__(self, srv: MCPServer):
        super().__init__()
        self._srv = srv

    @property
    def srv(self) -> MCPServer:
        """Get current server state."""
        return self._srv

    def compose(self) -> ComposeResult:
        yield Label(self._srv.name, classes="name")
        yield Label(self._srv.summary, classes="info")
        yield Switch(value=self._srv.enabled)

    @on(Switch.Changed)
    async def on_toggle(self, event: Switch.Changed):
        try:
            self._srv = await cm.toggle_server_async(self._srv, event.value)
            action = "Enabled" if event.value else "Disabled"
            self.notify(f"{action} {self._srv.name}")
        except ServerNotFoundError:
            switch = self.query_one(Switch)
            switch.value = not event.value
            self.notify(
                f"Server not found: {self._srv.name} - try refreshing (r)",
                severity="error",
            )
        except PermissionError:
            switch = self.query_one(Switch)
            switch.value = not event.value
            self.notify(
                f"Permission denied: cannot modify config for {self._srv.name}",
                severity="error",
            )
        except Exception as e:
            logger.exception(f"Unexpected error toggling server {self._srv.name}")
            switch = self.query_one(Switch)
            switch.value = not event.value
            self.notify(f"Error toggling {self._srv.name}: {e}", severity="error")


class SkillRow(Horizontal):
    """Row widget for displaying and toggling a skill/agent."""

    DEFAULT_CSS = "SkillRow { " + ROW_CSS + " }"

    def __init__(self, sk: Skill):
        super().__init__()
        self._sk = sk

    @property
    def sk(self) -> Skill:
        """Get current skill state."""
        return self._sk

    def compose(self) -> ComposeResult:
        tag = f"[{self._sk.kind.value}] " if self._sk.kind == ItemKind.AGENT else ""
        yield Label(f"{tag}{self._sk.name}", classes="name")
        yield Label(self._sk.description[:DESCRIPTION_MAX_LENGTH], classes="info")
        yield Switch(value=self._sk.enabled)

    @on(Switch.Changed)
    async def on_toggle(self, event: Switch.Changed):
        try:
            self._sk = await cm.toggle_skill_async(self._sk, event.value)
            action = "Enabled" if event.value else "Disabled"
            self.notify(f"{action} {self._sk.kind.value}: {self._sk.name}")
        except FileNotFoundError:
            switch = self.query_one(Switch)
            switch.value = not event.value
            self.notify(
                f"Skill not found: {self._sk.name} - try refreshing (r)",
                severity="error",
            )
        except FileExistsError as e:
            switch = self.query_one(Switch)
            switch.value = not event.value
            self.notify(f"Error: {e}", severity="error")
        except ValueError as e:
            switch = self.query_one(Switch)
            switch.value = not event.value
            self.notify(f"Security error: {e}", severity="error")
        except PermissionError:
            switch = self.query_one(Switch)
            switch.value = not event.value
            self.notify(f"Permission denied: cannot modify {self._sk.name}", severity="error")
        except Exception as e:
            logger.exception(f"Unexpected error toggling skill {self._sk.name}")
            switch = self.query_one(Switch)
            switch.value = not event.value
            self.notify(f"Error toggling {self._sk.name}: {e}", severity="error")


class ToggleAllRow(Horizontal):
    """Row widget for toggling all items in a section."""

    DEFAULT_CSS = """
    ToggleAllRow {
        height: 3; padding: 0 1; background: $primary-background; margin-bottom: 1;
        .label { width: 1fr; content-align: left middle; text-style: bold; color: $accent; }
        Switch { width: auto; }
    }
    """

    def __init__(self, label: str, section: str):
        super().__init__()
        self._label = label
        self.section = section

    def compose(self) -> ComposeResult:
        yield Label(self._label, classes="label")
        yield Switch(value=True, id=f"ta-{self.section}")


class SectionType:
    SERVER = "srv-"
    AGENT = "agt-"
    SKILL = "skl-"


LABELS = {
    Assistant.CURSOR: "Cursor",
    Assistant.VSCODE: "VS Code",
    Assistant.CLAUDE: "Claude Code",
    Assistant.CLINE: "Cline",
    Assistant.ROOCODE: "RooCode",
    Assistant.OPENCODE: "OpenCode",
    Assistant.GEMINI: "Gemini",
    Assistant.CODEX: "Codex",
}


class SwitchboardApp(App):
    """Main Switchboard TUI application."""

    CSS = """
    TabbedContent { height: 1fr; }
    #status { dock: bottom; height: 1; padding: 0 1; color: $text-muted; background: $surface; }
    .empty { color: $text-muted; padding: 2 4; text-style: italic; }
    .section-label { padding: 1 1 0 1; text-style: bold; color: $accent; }
    """
    TITLE, BINDINGS = (
        "Switchboard — AI Tool Manager",
        [
            Binding("q", "quit", "Quit"),
            Binding("r", "refresh", "Refresh"),
            Binding("e", "enable_all", "Enable All"),
            Binding("d", "disable_all", "Disable All"),
        ],
    )

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            for a in Assistant:
                with TabPane(LABELS[a], id=f"t-{a.value}"):
                    yield VerticalScroll(id=f"l-{a.value}")
        yield Static("r: refresh | e: enable all | d: disable all | q: quit", id="status")
        yield Footer()

    def on_mount(self):
        cleanup_staging_dir()
        self._load()

    def _load(self):
        """Load and display all servers and skills."""
        srvs = cm.discover_servers()
        skills = cm.discover_skills()
        for a in Assistant:
            c = self.query_one(f"#l-{a.value}", VerticalScroll)
            c.remove_children()
            a_srvs = [s for s in srvs if s.assistant == a]
            a_skills = [s for s in skills if s.assistant == a]
            if not a_srvs and not a_skills:
                c.mount(Label("Nothing found", classes="empty"))
                continue
            if a_srvs:
                c.mount(
                    ToggleAllRow(
                        f"MCP Servers — Toggle All ({len(a_srvs)})",
                        f"{SectionType.SERVER}{a.value}",
                    )
                )
                for s in a_srvs:
                    c.mount(ServerRow(s))
            a_agents = [s for s in a_skills if s.kind == ItemKind.AGENT]
            a_sk = [s for s in a_skills if s.kind == ItemKind.SKILL]
            if a_agents:
                c.mount(
                    ToggleAllRow(
                        f"Agents — Toggle All ({len(a_agents)})",
                        f"{SectionType.AGENT}{a.value}",
                    )
                )
                for s in a_agents:
                    c.mount(SkillRow(s))
            if a_sk:
                c.mount(
                    ToggleAllRow(
                        f"Skills — Toggle All ({len(a_sk)})",
                        f"{SectionType.SKILL}{a.value}",
                    )
                )
                for s in a_sk:
                    c.mount(SkillRow(s))

    @on(Switch.Changed, "ToggleAllRow Switch")
    def on_toggle_all(self, event: Switch.Changed):
        row = event.control.parent
        if not isinstance(row, ToggleAllRow):
            return
        section = row.section
        container = row.parent
        if container is None:
            return
        target = event.value
        if section.startswith(SectionType.SERVER):
            for w in container.query(ServerRow):
                if w.srv.enabled != target:
                    w.query_one(Switch).value = target
        else:
            for w in container.query(SkillRow):
                kind_match = (
                    section.startswith(SectionType.AGENT) and w.sk.kind == ItemKind.AGENT
                ) or (section.startswith(SectionType.SKILL) and w.sk.kind == ItemKind.SKILL)
                if kind_match and w.sk.enabled != target:
                    w.query_one(Switch).value = target
        tag = "Enabled" if target else "Disabled"
        self.notify(f"{tag} all in {section}")

    def _toggle_tab(self, enable: bool):
        """Toggle all items in the currently active tab."""
        tc = self.query_one(TabbedContent)
        active_id = tc.active
        if not active_id:
            return
        pane = self.query_one(f"#{active_id}", TabPane)
        for w in pane.query(ServerRow):
            if w.srv.enabled != enable:
                w.query_one(Switch).value = enable
        for w in pane.query(SkillRow):
            if w.sk.enabled != enable:
                w.query_one(Switch).value = enable
        for ta in pane.query(ToggleAllRow):
            ta.query_one(Switch).value = enable
        self.notify(f"{'Enabled' if enable else 'Disabled'} all in current tab")

    def action_enable_all(self):
        self._toggle_tab(True)

    def action_disable_all(self):
        self._toggle_tab(False)

    def action_refresh(self):
        self._load()
        self.notify("Refreshed")
