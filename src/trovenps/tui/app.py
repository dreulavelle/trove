"""Trove — a Textual TUI for browsing and downloading the NoPayStation catalog."""

from __future__ import annotations

import os
import time
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ProgressBar,
    Select,
    Static,
    Switch,
    TabbedContent,
    TabPane,
)

from ..aria2 import add_to_aria2_rpc
from ..catalog import DATASETS, load_games
from ..config import Settings, load_settings, save_settings
from ..download import download_games
from ..models import ContentType, Filter, Game, Platform


def human_size(num: int | None) -> str:
    if not num:
        return ""
    size = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def game_key(game: Game) -> str:
    """Row/selection key — stable so selection survives re-filtering."""
    return game.identity


class DownloadRow(Static):
    """One transfer: title, progress bar, and a live speed / size readout."""

    def __init__(self, game: Game) -> None:
        super().__init__()
        self._game = game
        self._total: int | None = None
        self._done = 0
        self._mark = 0       # bytes seen at the last tick
        self._t = 0.0        # monotonic time at the last tick
        self._speed = 0.0    # smoothed bytes/sec
        self._finished = False

    def compose(self) -> ComposeResult:
        yield Label(f"{self._game.title_id}  {self._game.name}"[:60], classes="dl-title")
        yield ProgressBar(total=None, show_eta=True)
        yield Label("queued…", classes="dl-stats")

    def on_mount(self) -> None:
        self._t = time.monotonic()
        self.set_interval(1.0, self._tick)

    def set_total(self, total: int | None, initial: int) -> None:
        self._total = total
        self._done = self._mark = initial
        self.query_one(ProgressBar).update(total=total, progress=initial)

    def advance(self, amount: int) -> None:
        self._done += amount
        self.query_one(ProgressBar).advance(amount)

    def complete(self) -> None:
        self._finished = True
        bar = self.query_one(ProgressBar)
        if bar.total is not None:
            bar.update(progress=bar.total)
        self.query_one(".dl-stats", Label).update(f"done · {human_size(self._total or self._done)}")

    def _tick(self) -> None:
        if self._finished:
            return
        now = time.monotonic()
        dt = now - self._t
        if dt > 0:
            inst = max(0.0, (self._done - self._mark) / dt)
            self._speed = inst if self._speed == 0 else 0.6 * self._speed + 0.4 * inst
        self._mark, self._t = self._done, now
        size = human_size(self._done) or "0B"
        total = human_size(self._total) if self._total else "?"
        rate = f"{human_size(int(self._speed))}/s" if self._speed >= 1 else "—"
        self.query_one(".dl-stats", Label).update(f"{rate}    {size} / {total}")


class _TextualSink:
    def __init__(self, rows: dict[str, DownloadRow]) -> None:
        self._rows = rows

    def start(self, key: str, desc: str, total: int | None, initial: int = 0) -> None:
        if row := self._rows.get(key):
            row.set_total(total, initial)

    def advance(self, key: str, amount: int) -> None:
        if row := self._rows.get(key):
            row.advance(amount)

    def finish(self, key: str) -> None:
        if row := self._rows.get(key):
            row.complete()


class TroveApp(App):
    TITLE = "Trove"
    SUB_TITLE = "NoPayStation"
    CSS_PATH = "app.tcss"
    MAX_ROWS = 1000  # cap rendered rows so huge datasets stay snappy; refine to narrow

    BINDINGS = [
        Binding("/", "focus_search", "Search"),
        Binding("space", "toggle_select", "Select"),
        Binding("a", "select_all", "Select all"),
        Binding("c", "clear_select", "Clear"),
        Binding("d", "download", "Download"),
        Binding("g", "grab_aria2", "→ aria2"),
        Binding("r", "refresh", "Refresh"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, output_dir: Path | None = None) -> None:
        super().__init__()
        self.settings = load_settings()
        base = Path(output_dir) if output_dir else Path(self.settings.download_dir)
        self.output_dir = base.expanduser()
        self.concurrency = self.settings.concurrency
        self.verify = self.settings.verify
        self.organize = self.settings.organize_by_platform
        self.games: list[Game] = []
        self.view: list[Game] = []
        self.selected: dict[str, Game] = {}
        self._by_key: dict[str, Game] = {}
        self._search = ""
        self._region = self.settings.region
        self._refresh = False

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(initial="browse"):
            with TabPane("Browse", id="browse"):
                with Horizontal(id="filters"):
                    yield Select(
                        [(p.value, p) for p in Platform],
                        value=Platform.PSV, allow_blank=False, id="platform",
                    )
                    yield Select(
                        [(t.value, t) for t in DATASETS[Platform.PSV]],
                        value=ContentType.GAMES, allow_blank=False, id="type",
                    )
                    yield Input(value=self._region, placeholder="region", id="region")
                    yield Input(placeholder="search title or ID…", id="search")
                yield DataTable(id="table", cursor_type="row")
            with TabPane("Downloads", id="downloads"):
                yield VerticalScroll(id="dl-list")
            with TabPane("Settings", id="settings"):
                with VerticalScroll(id="settings-form"):
                    yield Label("Download folder", classes="set-label")
                    yield Input(value=self.settings.download_dir, id="set-dir")
                    yield Label("", id="current-dest")
                    with Horizontal(classes="set-row"):
                        yield Switch(value=self.organize, id="set-organize")
                        yield Label("Organize into per-console folders (downloads/psvita …)",
                                    classes="set-switch-label")
                    yield Label("Concurrent downloads (1–16)", classes="set-label")
                    yield Input(value=str(self.concurrency), id="set-concurrency", type="integer")
                    yield Label("Default region filter", classes="set-label")
                    yield Input(value=self._region, placeholder="e.g. US — blank for all", id="set-region")
                    with Horizontal(classes="set-row"):
                        yield Switch(value=self.verify, id="set-verify")
                        yield Label("Verify SHA-256 after each download", classes="set-switch-label")
                    yield Label("aria2 instance — optional; used by default when set", classes="set-section")
                    yield Label("RPC URL", classes="set-label")
                    yield Input(value=self.settings.aria2_rpc_url,
                                placeholder="http://localhost:6800/jsonrpc", id="set-aria2-url")
                    yield Label("RPC secret", classes="set-label")
                    yield Input(value=self.settings.aria2_rpc_secret, password=True, id="set-aria2-secret")
                    yield Label("Remote download dir", classes="set-label")
                    yield Input(value=self.settings.aria2_dir,
                                placeholder="dir on the aria2 host", id="set-aria2-dir")
                    yield Button("Save settings", id="set-save", variant="primary")
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        self._columns = table.add_columns("", "Title ID", "Region", "Name", "Size")
        table.focus()  # action keys act on the list by default; "/" jumps to search
        self._update_dest()
        self.load_dataset()

    def _update_dest(self) -> None:
        raw = self.query_one("#set-dir", Input).value.strip() or "downloads"
        try:
            dest = str(Path(raw).expanduser().resolve())
        except OSError:
            dest = raw
        self.query_one("#current-dest", Label).update(f"Current Download Location:  {dest}")

    @on(Input.Changed, "#set-dir")
    def _dest_changed(self) -> None:
        self._update_dest()

    @property
    def platform(self) -> Platform:
        return self.query_one("#platform", Select).value  # type: ignore[return-value]

    @property
    def content_type(self) -> ContentType:
        return self.query_one("#type", Select).value  # type: ignore[return-value]

    @work(exclusive=True, group="load")
    async def load_dataset(self) -> None:
        platform, content_type = self.platform, self.content_type
        self.sub_title = f"loading {platform.value} {content_type.value}…"
        self.games = await load_games(platform, content_type, refresh=self._refresh)
        self._refresh = False
        self.apply_filter()
        self.sub_title = f"{platform.value} {content_type.value} — {len(self.games):,} items"

    def apply_filter(self) -> None:
        flt = Filter(
            query=self._search or None,
            regions={self._region.upper()} if self._region else None,
            downloadable_only=False,
        )
        self.view = flt.apply(self.games)
        self._by_key = {}
        table = self.query_one(DataTable)
        table.clear()
        for g in self.view:
            if len(self._by_key) >= self.MAX_ROWS:
                break
            key = game_key(g)
            if key in self._by_key:  # a DataTable row key must be unique
                continue
            self._by_key[key] = g
            mark = "✓" if key in self.selected else ("" if g.downloadable else "·")
            table.add_row(mark, g.title_id, g.region, g.name, human_size(g.file_size), key=key)
        self.update_status()

    def update_status(self) -> None:
        matches, rendered = len(self.view), len(self._by_key)
        more = f"  (+{matches - rendered:,} — refine)" if matches > rendered else ""
        self.query_one("#status", Static).update(
            f" selected: {len(self.selected)}    shown: {rendered:,} / {matches:,}{more}"
        )

    @on(Select.Changed, "#platform")
    def _platform_changed(self, event: Select.Changed) -> None:
        type_select = self.query_one("#type", Select)
        types = DATASETS[event.value]  # type: ignore[index]
        type_select.set_options([(t.value, t) for t in types])
        type_select.value = types[0]
        self.load_dataset()

    @on(Select.Changed, "#type")
    def _type_changed(self, event: Select.Changed) -> None:
        if event.value is not Select.BLANK:
            self.load_dataset()

    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()

    @on(Input.Submitted, "#search")
    def _search_submitted(self) -> None:
        self.query_one(DataTable).focus()  # Enter commits the filter, back to the list

    @on(Input.Changed, "#search")
    def _search_changed(self, event: Input.Changed) -> None:
        self._search = event.value
        self._debounce()

    @on(Input.Changed, "#region")
    def _region_changed(self, event: Input.Changed) -> None:
        self._region = event.value
        self._debounce()

    def _debounce(self) -> None:
        if timer := getattr(self, "_filter_timer", None):
            timer.stop()
        self._filter_timer = self.set_timer(0.18, self.apply_filter)

    def _cursor_key(self) -> str | None:
        table = self.query_one(DataTable)
        if table.row_count == 0:
            return None
        return table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value

    def action_toggle_select(self) -> None:
        key = self._cursor_key()
        if key is None or (game := self._by_key.get(key)) is None:
            return
        if key in self.selected:
            del self.selected[key]
        elif not game.downloadable:
            self.notify(f"{game.title_id} has no download link", severity="warning")
            return
        else:
            self.selected[key] = game
        self.query_one(DataTable).update_cell(
            key, self._columns[0], "✓" if key in self.selected else ""
        )
        self.update_status()

    def action_select_all(self) -> None:
        # operate on the full match set, not just the capped rendered rows
        self.selected.update({game_key(g): g for g in self.view if g.downloadable})
        self.apply_filter()

    def action_clear_select(self) -> None:
        self.selected.clear()
        self.apply_filter()

    def _to_download(self) -> list[Game]:
        if self.selected:
            return list(self.selected.values())
        key = self._cursor_key()
        game = self._by_key.get(key) if key else None
        return [game] if game and game.downloadable else []

    def action_refresh(self) -> None:
        self._refresh = True
        self.load_dataset()

    def action_download(self) -> None:
        if not (games := self._to_download()):
            self.notify("Nothing selected to download.", severity="warning")
            return
        self.query_one(TabbedContent).active = "downloads"
        self.run_downloads(games)

    def action_grab_aria2(self) -> None:
        if not (games := self._to_download()):
            self.notify("Nothing selected.", severity="warning")
            return
        self.push_aria2(games)

    @on(Button.Pressed, "#set-save")
    def _save_settings(self) -> None:
        dir_in = self.query_one("#set-dir", Input).value.strip() or "downloads"
        conc_in = self.query_one("#set-concurrency", Input).value.strip()
        region_in = self.query_one("#set-region", Input).value.strip()
        verify_in = self.query_one("#set-verify", Switch).value
        organize_in = self.query_one("#set-organize", Switch).value
        try:
            conc = max(1, min(16, int(conc_in))) if conc_in else 3
        except ValueError:
            conc = self.concurrency
        self.settings = Settings(
            download_dir=dir_in, concurrency=conc, verify=verify_in, region=region_in,
            organize_by_platform=organize_in,
            aria2_rpc_url=self.query_one("#set-aria2-url", Input).value.strip(),
            aria2_rpc_secret=self.query_one("#set-aria2-secret", Input).value.strip(),
            aria2_dir=self.query_one("#set-aria2-dir", Input).value.strip(),
        )
        path = save_settings(self.settings)
        self.output_dir = Path(dir_in).expanduser()
        self.concurrency, self.verify, self.organize = conc, verify_in, organize_in
        self._region = region_in
        self.query_one("#region", Input).value = region_in  # reflect in the Browse filter
        self._update_dest()
        self.notify(f"Saved to {path}")

    @work(exclusive=True, group="download")
    async def run_downloads(self, games: list[Game]) -> None:
        container = self.query_one("#dl-list", VerticalScroll)
        await container.remove_children()
        rows: dict[str, DownloadRow] = {}
        for g in games:
            row = DownloadRow(g)
            await container.mount(row)
            rows[g.filename] = row
        results = await download_games(
            games, self.output_dir, concurrency=self.concurrency, verify=self.verify,
            organize=self.organize, sink=_TextualSink(rows),
        )
        self.notify(f"Downloaded {len(results)}/{len(games)} to {self.output_dir}")

    @work(exclusive=True, group="aria2")
    async def push_aria2(self, games: list[Game]) -> None:
        url = self.settings.aria2_rpc_url or os.getenv("ARIA2_RPC_URL")
        if not url:
            self.notify("No aria2 RPC URL — set one in Settings or ARIA2_RPC_URL", severity="error")
            return
        secret = self.settings.aria2_rpc_secret or os.getenv("ARIA2_RPC_SECRET")
        gids = await add_to_aria2_rpc(
            games, url, secret=secret, remote_dir=self.settings.aria2_dir or None, organize=self.organize
        )
        self.notify(f"Queued {len(gids)}/{len(games)} to aria2")
