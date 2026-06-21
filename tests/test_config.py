from nps.config import Settings, load_settings, save_settings


def test_defaults_when_missing(tmp_path):
    s = load_settings(tmp_path / "nope.json")
    assert s.download_dir == "downloads" and s.concurrency == 3 and s.verify is True


def test_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    saved = save_settings(Settings(download_dir="/games", concurrency=8, verify=False), path)
    assert saved == path
    loaded = load_settings(path)
    assert loaded.download_dir == "/games" and loaded.concurrency == 8 and loaded.verify is False


def test_malformed_falls_back_to_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{ not json", encoding="utf-8")
    assert load_settings(path).concurrency == 3


def test_out_of_range_concurrency_rejected(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"concurrency": 999}', encoding="utf-8")
    assert load_settings(path).concurrency == 3  # invalid -> defaults
