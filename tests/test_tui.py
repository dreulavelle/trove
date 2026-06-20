from nps.models import ContentType, Game, Platform
from nps.tui import app as tui_app


def _games() -> list[Game]:
    common = {"platform": Platform.PSV, "content_type": ContentType.GAMES}
    return [
        Game(title_id="PCSA0001", region="US", name="Alpha", pkg_direct_link="http://e/a.pkg",
             file_size=1024, content_id="UP-A", **common),
        Game(title_id="PCSA0002", region="EU", name="Beta", pkg_direct_link="http://e/b.pkg",
             file_size=2048, content_id="UP-B", **common),
        Game(title_id="PCSA0003", region="US", name="Gamma", pkg_direct_link="MISSING",
             content_id="UP-C", **common),
    ]


async def test_tui_filter_select_and_persistence(monkeypatch):
    async def _no_network(*a, **k):
        return []

    monkeypatch.setattr(tui_app, "load_games", _no_network)  # mount worker is harmless
    app = tui_app.TroveApp()

    async with app.run_test():
        app.games = _games()
        app.apply_filter()
        table = app.query_one("#table")
        assert table.row_count == 3

        # select-all picks only downloadable items (Gamma excluded)
        app.action_select_all()
        assert len(app.selected) == 2

        # searching narrows the view but keeps selections intact
        app._search = "alpha"
        app.apply_filter()
        assert table.row_count == 1
        assert len(app.selected) == 2  # persisted across search

        app.action_clear_select()
        assert len(app.selected) == 0
