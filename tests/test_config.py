from __future__ import annotations

import sys
from pathlib import Path

from crate.config import Settings, discover_ffmpeg


def test_from_env_reads_overrides(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CRATE_LIBRARY", str(tmp_path / "media"))
    monkeypatch.setenv("CRATE_DB", str(tmp_path / "state" / "crate.db"))
    monkeypatch.setenv("CRATE_TOKEN", " s3cret ")
    monkeypatch.setenv("CRATE_ALLOW_PRIVATE_URLS", "yes")
    monkeypatch.setenv("CRATE_SECURE_COOKIES", "1")
    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / "index.html").write_text("<!doctype html>", encoding="utf-8")
    monkeypatch.setenv("CRATE_FRONTEND", str(ui))

    settings = Settings.from_env(tmp_path)

    assert settings.library == (tmp_path / "media").resolve()
    assert settings.db_path == (tmp_path / "state" / "crate.db").resolve()
    assert settings.token == "s3cret"
    assert settings.auth_required is True
    assert settings.allow_private_urls is True
    assert settings.secure_cookies is True
    assert settings.frontend == (tmp_path / "ui").resolve()
    assert settings.audio_dir == settings.library / "audio"
    assert settings.video_dir == settings.library / "video"


def test_from_env_defaults_to_cwd(tmp_path: Path, monkeypatch) -> None:
    for name in (
        "CRATE_LIBRARY",
        "CRATE_DB",
        "CRATE_TOKEN",
        "CRATE_ALLOW_PRIVATE_URLS",
        "CRATE_SECURE_COOKIES",
        "CRATE_FRONTEND",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_env(tmp_path)

    assert settings.library == (tmp_path / "library").resolve()
    assert settings.db_path == (tmp_path / "data" / "crate.db").resolve()
    assert settings.auth_required is False
    assert settings.allow_private_urls is False


def test_discover_ffmpeg_prefers_explicit_file(tmp_path: Path, monkeypatch) -> None:
    binary = tmp_path / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    binary.write_bytes(b"binary")
    monkeypatch.setenv("CRATE_FFMPEG", str(binary))

    assert discover_ffmpeg() == str(binary)


def test_discover_ffmpeg_ignores_missing_explicit_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CRATE_FFMPEG", str(tmp_path / "nope"))

    found = discover_ffmpeg()

    assert found is None or Path(found).name.startswith("ffmpeg")
