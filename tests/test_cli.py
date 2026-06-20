import json

from nps.cli import _game_json
from nps.models import ContentType, Game, Platform

_CTX = {"platform": Platform.PSV, "content_type": ContentType.GAMES}


def test_game_json_downloadable():
    g = Game(title_id="PCSA1", region="US", name="Alpha", content_id="UP-A",
             file_size=100, sha256="ABC", pkg_direct_link="http://e/a.pkg", **_CTX)

    row = _game_json(g)

    assert row["url"] == "http://e/a.pkg" and row["downloadable"] is True
    assert row["platform"] == "PSV" and row["content_type"] == "GAMES"
    assert row["file_size"] == 100
    json.dumps(row)  # must be JSON-serializable (no enums/None surprises)


def test_game_json_non_downloadable_has_null_url():
    g = Game(title_id="PCSA2", region="EU", name="Beta", pkg_direct_link="MISSING", **_CTX)

    row = _game_json(g)

    assert row["downloadable"] is False and row["url"] is None
