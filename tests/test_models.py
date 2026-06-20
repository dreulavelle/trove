from nps.models import ContentType, Filter, Game, Platform


def test_identity_fields_survive_blank_normalization():
    g = Game(title_id="PCSA00001", region="US", name="Demo")
    assert g.region == "US" and g.name == "Demo"


def test_missing_marker_becomes_none():
    g = Game(title_id="X", pkg_direct_link="MISSING", zrif="")
    assert g.pkg_direct_link is None
    assert g.zrif is None


def test_downloadable_and_download_url():
    ok = Game(title_id="X", pkg_direct_link="http://e/x.pkg")
    assert ok.downloadable
    assert ok.download_url == "http://e/x.pkg"

    bad = Game(title_id="X", pkg_direct_link="MISSING")
    assert not bad.downloadable


def test_download_url_raises_when_unavailable():
    g = Game(title_id="X")
    try:
        _ = g.download_url
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_filename_prefers_content_id():
    assert Game(title_id="T", region="US", content_id="UP-ABC").filename == "UP-ABC.pkg"
    assert Game(title_id="T", region="US").filename == "T_US.pkg"


def test_junk_file_size_is_none_not_error():
    assert Game(title_id="X", file_size="4.7").file_size is None
    assert Game(title_id="X", file_size="123").file_size == 123
    assert Game(title_id="X", file_size="MISSING").file_size is None


def test_filter_query_region_and_downloadable():
    games = [
        Game(title_id="A1", region="US", name="Alpha", pkg_direct_link="http://e/a.pkg"),
        Game(title_id="B2", region="EU", name="Beta", pkg_direct_link="http://e/b.pkg"),
        Game(title_id="C3", region="US", name="Gamma", pkg_direct_link="MISSING"),
    ]
    assert {g.title_id for g in Filter(query="alpha").apply(games)} == {"A1"}
    assert {g.title_id for g in Filter(regions=["us"]).apply(games)} == {"A1"}  # C3 not downloadable
    assert {g.title_id for g in Filter(regions={"us"}, downloadable_only=False).apply(games)} == {"A1", "C3"}


def test_platform_and_content_type_enums_assignable():
    g = Game(title_id="X", platform=Platform.PS3, content_type=ContentType.DLCS)
    assert g.platform is Platform.PS3 and g.content_type is ContentType.DLCS
