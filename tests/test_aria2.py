from pathlib import Path

import pytest

from nps import aria2
from nps.models import ContentType, Game, Platform

_CTX = {"platform": Platform.PSV, "content_type": ContentType.GAMES}


def _game() -> Game:
    return Game(title_id="PCSA1", region="US", name="Alpha", content_id="UP-A",
                sha256="ABC", pkg_direct_link="http://e/a.pkg", **_CTX)


def test_run_aria2c_missing_binary(monkeypatch, tmp_path):
    monkeypatch.setattr(aria2.shutil, "which", lambda _: None)
    with pytest.raises(FileNotFoundError):
        aria2.run_aria2c([_game()], tmp_path)


def test_run_aria2c_invokes_aria2c(monkeypatch, tmp_path):
    monkeypatch.setattr(aria2.shutil, "which", lambda _: "/usr/bin/aria2c")
    seen = {}

    class _Proc:
        returncode = 0

    def fake_run(cmd, *a, **k):
        seen["cmd"] = cmd
        idx = cmd.index("-i")  # the temp input file must exist and hold the URL now
        assert Path(cmd[idx + 1]).read_text(encoding="utf-8").startswith("http://e/a.pkg")
        return _Proc()

    monkeypatch.setattr(aria2.subprocess, "run", fake_run)

    assert aria2.run_aria2c([_game()], tmp_path, concurrency=5) == 0
    assert seen["cmd"][0] == "/usr/bin/aria2c"
    assert "-j5" in seen["cmd"] and "-c" in seen["cmd"]
