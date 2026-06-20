import pytest

from nps.models import ContentType, Game, Platform
from nps.tui import app as tui_app


def _game(tid, region, name, *, link=True):
    return Game(
        title_id=tid, region=region, name=name,
        pkg_direct_link=f"http://e/{tid}.pkg" if link else "MISSING",
        file_size=1288490188, content_id=tid,
        platform=Platform.PSV, content_type=ContentType.GAMES,
    )


CATALOG = {
    Platform.PSV: [
        _game("PCSA00099", "US", "Tearaway"),
        _game("PCSF00214", "EU", "Tearaway"),
        _game("PCSC00048", "JP", "Tearaway X"),
        _game("PCSB00264", "US", "Gravity Rush"),
        _game("PCSA00111", "US", "Trial Only", link=False),
    ],
    Platform.PS3: [_game("NPUB30910", "US", "Demon's Souls")],
}


@pytest.fixture
def app(monkeypatch):
    async def fake_load(platform, content_type, **kw):
        return list(CATALOG.get(platform, []))

    monkeypatch.setattr(tui_app, "load_games", fake_load)
    return tui_app.TroveApp()


async def test_loads_on_mount(app):
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.query_one("#table").row_count == 5


async def test_search_focus_flow(app):
    """The real loop: '/' -> type -> Enter -> action keys act on the table."""
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("/")                       # focus search
        assert app.focused.id == "search"
        await pilot.press("t", "e", "a", "r")        # filter
        await pilot.pause(0.3)
        assert app.query_one("#table").row_count == 3
        await pilot.press("enter")                   # back to the list
        assert app.focused.id == "table"
        await pilot.press("a")                       # select-all now works
        assert len(app.selected) == 3


async def test_selection_survives_search(app):
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_select_all()
        assert len(app.selected) == 4                # 4 downloadable, trial excluded
        app._search = "gravity"
        app.apply_filter()
        assert app.query_one("#table").row_count == 1
        assert len(app.selected) == 4                # persists


async def test_space_toggle_and_clear(app):
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("space")
        assert len(app.selected) == 1
        await pilot.press("space")
        assert len(app.selected) == 0
        app.action_select_all()
        await pilot.press("c")
        assert len(app.selected) == 0


async def test_non_downloadable_not_selected(app):
    async with app.run_test() as pilot:
        await pilot.pause()
        app._search = "trial"
        app.apply_filter()
        await pilot.press("space")                   # cursor on the only (non-dl) row
        assert len(app.selected) == 0


async def test_platform_switch_reloads(app):
    async with app.run_test() as pilot:
        await pilot.pause()
        app.query_one("#platform").value = Platform.PS3
        await pilot.pause()
        assert app.query_one("#table").row_count == 1


async def test_download_action_switches_tab(app, monkeypatch):
    seen = {}

    async def fake_download(games, output_dir, **kw):
        seen["n"] = len(games)
        return list(range(len(games)))

    monkeypatch.setattr(tui_app, "download_games", fake_download)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_select_all()
        await pilot.press("d")
        await pilot.pause()
        assert app.query_one(tui_app.TabbedContent).active == "downloads"
        assert seen["n"] == 4


async def test_download_nothing_selected_is_safe(app):
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_clear_select()
        # cursor sits on row 0 (downloadable) -> downloads the current row, no crash
        assert app.is_running


async def test_aria2_without_url_is_safe(app, monkeypatch):
    monkeypatch.delenv("ARIA2_RPC_URL", raising=False)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_select_all()
        await pilot.press("g")
        await pilot.pause()
        assert app.is_running                        # notified, did not crash


def test_human_size():
    assert tui_app.human_size(None) == ""
    assert tui_app.human_size(0) == ""
    assert tui_app.human_size(1024) == "1.0KB"
    assert tui_app.human_size(1288490188) == "1.2GB"


async def test_region_filter(app):
    async with app.run_test() as pilot:
        await pilot.pause()
        app._region = "jp"
        app.apply_filter()
        assert app.query_one("#table").row_count == 1


async def test_selection_persists_across_datasets(app):
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_select_all()
        assert len(app.selected) == 4
        app.query_one("#platform").value = Platform.PS3
        await pilot.pause()
        assert app.query_one("#table").row_count == 1     # PS3 view
        assert len(app.selected) == 4                      # cart persists
        assert len(app._to_download()) == 4


async def test_empty_view_download_is_safe(app):
    async with app.run_test() as pilot:
        await pilot.pause()
        app._search = "zzz-no-match"
        app.apply_filter()
        assert app.query_one("#table").row_count == 0
        await pilot.press("d")                              # nothing to do, no crash
        await pilot.pause()
        assert app.is_running


async def test_duplicate_identity_rows_dont_crash(app):
    async with app.run_test() as pilot:
        await pilot.pause()
        dup = _game("PCSA00099", "US", "Tearaway")  # same identity as CATALOG[0]
        app.games = CATALOG[Platform.PSV] + [dup]
        app.apply_filter()
        assert app.query_one("#table").row_count == 5  # collapsed, no DuplicateKey


async def test_progress_sink_drives_bar(app):
    g = CATALOG[Platform.PSV][0]
    async with app.run_test() as pilot:
        await pilot.pause()
        row = tui_app.DownloadRow(g)
        await app.query_one("#dl-list").mount(row)
        await pilot.pause()
        sink = tui_app._TextualSink({g.filename: row})
        sink.start(g.filename, g.name, 1000, initial=200)
        sink.advance(g.filename, 300)
        await pilot.pause()
        bar = row.query_one(tui_app.ProgressBar)
        assert bar.total == 1000
        assert bar.progress == 500
        sink.finish(g.filename)
        await pilot.pause()
        assert bar.progress == 1000
