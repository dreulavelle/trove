import time

from nps import catalog
from nps.models import ContentType, Platform

# A synthetic dataset exercising the real-world quirks the parser must survive:
# duplicate FW headers, a junk file size, a Unicode name, and a header-less row.
_TSV = (
    "Title ID\tRegion\tName\tPKG direct link\tzRIF\tContent ID\t"
    "Last Modification Date\tFile Size\tSHA256\tRequired FW\n"
    "PCSA1\tUS\tAlpha\thttp://e/a.pkg\tKEY\tUP-A\t2020\t100\tABC\t3.60\n"
    "PCSA2\tJP\tテスト\thttp://e/b.pkg\tKEY\tUP-B\t2020\t4.7\tDEF\t3.60\n"  # junk size
    "\tUS\tNoTitle\thttp://e/c.pkg\t\t\t\t\t\t\n"  # missing title -> skipped
)


def test_parse_tsv_handles_quirks(tmp_path):
    p = tmp_path / "PSV_GAMES.tsv"
    p.write_text(_TSV, encoding="utf-8")

    games = catalog.parse_tsv(p, Platform.PSV, ContentType.GAMES)

    assert len(games) == 2  # header-less row dropped
    a, b = games
    assert a.title_id == "PCSA1" and a.file_size == 100
    assert b.name == "テスト" and b.file_size is None  # junk size -> None, row kept
    assert all(g.platform is Platform.PSV for g in games)
    assert all(g.content_type is ContentType.GAMES for g in games)


def test_dataset_name():
    assert catalog.dataset_name(Platform.PS3, ContentType.DLCS) == "PS3_DLCS"


def test_is_fresh_window():
    assert catalog._is_fresh({"fetched_at": time.time()})
    assert not catalog._is_fresh({"fetched_at": time.time() - catalog.CACHE_TTL - 1})
    assert not catalog._is_fresh({})


def test_reset_cache_removes_files(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, "CACHE_DIR", tmp_path)
    (tmp_path / "PSV_GAMES.tsv").write_text("x", encoding="utf-8")
    (tmp_path / "PSV_GAMES.meta.json").write_text("{}", encoding="utf-8")
    assert catalog.reset_cache() == 2
    assert not list(tmp_path.iterdir())
