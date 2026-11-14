from __future__ import annotations

import json

import pytest
from helpers import write_media

from crate.config import Settings
from crate.db import Store
from crate.library import Library, clean_title, media_id_for, parse_ffmpeg_probe


def test_scan_indexes_audio_and_video(settings: Settings, store: Store, library: Library) -> None:
    write_media(
        settings,
        "audio",
        "night-drive.mp3",
        meta={"title": "Night Drive", "artist": "Kite", "duration": 215.5},
    )
    write_media(settings, "video", "first-light.mp4", meta={"title": "First Light"})

    result = library.scan()

    assert result == {"added": 2, "updated": 0, "removed": 0}
    rows = {row["title"]: row for row in store.list_media()}
    assert rows["Night Drive"]["kind"] == "audio"
    assert rows["Night Drive"]["artist"] == "Kite"
    assert rows["Night Drive"]["duration"] == 215.5
    assert rows["Night Drive"]["mime"] == "audio/mpeg"
    assert rows["First Light"]["kind"] == "video"
    assert rows["First Light"]["mime"] == "video/mp4"


def test_scan_uses_filename_when_no_sidecar(
    settings: Settings, store: Store, library: Library
) -> None:
    write_media(settings, "audio", "late_night_take [abc123].mp3")

    library.scan()
    row = store.list_media()[0]

    assert row["title"] == "late night take"
    assert row["duration"] is None


def test_scan_removes_rows_for_deleted_files(
    settings: Settings, store: Store, library: Library
) -> None:
    path = write_media(settings, "audio", "gone.mp3", meta={"title": "Gone"})
    library.scan()
    assert store.count_media()["audio"] == 1

    path.unlink()
    result = library.scan()

    assert result["removed"] == 1
    assert store.count_media()["total"] == 0


def test_scan_updates_size_for_changed_files(
    settings: Settings, store: Store, library: Library
) -> None:
    path = write_media(settings, "audio", "grow.mp3", meta={"title": "Grow"})
    library.scan()

    path.write_bytes(b"0123456789abcdef")
    result = library.scan()

    assert result["updated"] == 1
    assert store.list_media()[0]["size"] == 16


def test_scan_picks_up_sibling_thumbnail(
    settings: Settings, store: Store, library: Library
) -> None:
    path = write_media(settings, "video", "clip.mp4", meta={"title": "Clip"})
    path.with_suffix(".jpg").write_bytes(b"jpeg")

    library.scan()
    row = store.list_media()[0]

    assert row["thumbnail"] == "video/clip.jpg"
    assert library.has_thumb(row)


def test_register_download_writes_sidecar_and_moves_thumbnail(
    settings: Settings, store: Store, library: Library
) -> None:
    settings.ensure_dirs()
    path = settings.audio_dir / "Track [xyz].mp3"
    path.write_bytes(b"audio")
    cover = settings.root / "cover.webp"
    cover.write_bytes(b"image")

    media = library.register_download(
        path,
        {
            "title": "Track",
            "artist": "Artist",
            "duration": 12.5,
            "source_url": "https://example.com/watch?v=xyz",
            "source_id": "xyz",
        },
        cover,
    )

    assert media["id"] == media_id_for("audio/Track [xyz].mp3")
    assert media["thumbnail"] == f"thumbnails/{media['id']}.webp"
    assert (settings.library / media["thumbnail"]).read_bytes() == b"image"
    assert not cover.exists()
    sidecar = json.loads(
        (settings.audio_dir / "Track [xyz].crate.json").read_text(encoding="utf-8")
    )
    assert sidecar["source_id"] == "xyz"
    assert sidecar["duration"] == 12.5


def test_register_download_replaces_same_source_id(
    settings: Settings, store: Store, library: Library
) -> None:
    settings.ensure_dirs()
    first = settings.audio_dir / "Old [same].mp3"
    first.write_bytes(b"old")
    media = library.register_download(first, {"title": "Old", "source_id": "same", "duration": 10})
    store.touch_played(media["id"])

    second = settings.audio_dir / "New [same].mp3"
    second.write_bytes(b"new")
    replaced = library.register_download(
        second, {"title": "New", "source_id": "same", "duration": 11}
    )

    assert replaced["id"] == media["id"]
    assert replaced["title"] == "New"
    assert replaced["play_count"] == 1
    assert not first.exists()
    assert replaced["path"] == "audio/New [same].mp3"
    assert store.count_media()["audio"] == 1


def test_register_download_keeps_thumbnail_when_path_changes(
    settings: Settings, store: Store, library: Library
) -> None:
    settings.ensure_dirs()
    first = settings.audio_dir / "Old [same].wav"
    first.write_bytes(b"old")
    cover = settings.root / "cover.jpg"
    cover.write_bytes(b"image")
    media = library.register_download(first, {"title": "Old", "source_id": "same"}, cover)

    second = settings.audio_dir / "New [same].wav"
    second.write_bytes(b"new")
    replaced = library.register_download(second, {"title": "New", "source_id": "same"})

    assert replaced["thumbnail"] == media["thumbnail"]
    assert (settings.library / replaced["thumbnail"]).is_file()


def test_register_download_rejects_paths_outside_library(
    settings: Settings, store: Store, library: Library
) -> None:
    settings.ensure_dirs()
    outside = settings.root.parent / "elsewhere.mp3"
    outside.write_bytes(b"audio")

    with pytest.raises(ValueError):
        library.register_download(outside, {"title": "Nope"})


def test_delete_removes_files_and_playlist_entries(
    settings: Settings, store: Store, library: Library
) -> None:
    path = write_media(settings, "audio", "bye.mp3", meta={"title": "Bye"})
    path.with_suffix(".jpg").write_bytes(b"image")
    library.scan()
    media = store.list_media()[0]
    playlist = store.create_playlist("Mix")
    store.add_playlist_item(playlist["id"], media["id"])

    assert library.delete(media["id"]) is True

    assert not path.exists()
    assert not path.with_suffix(".jpg").exists()
    assert store.get_media(media["id"]) is None
    assert store.get_playlist(playlist["id"])["item_count"] == 0


def test_resolve_rejects_traversal(settings: Settings, store: Store, library: Library) -> None:
    with pytest.raises(ValueError):
        library.resolve("../escape.mp3")


def test_parse_ffmpeg_probe_reads_duration_and_size() -> None:
    output = """
Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'clip.mp4':
  Duration: 00:01:03.50, start: 0.000000, bitrate: 757 kb/s
  Stream #0:0[0x1](und): Video: h264 (avc1 / 0x31637661), yuv420p, 1280x720 [SAR 1:1 DAR 16:9]
  Stream #0:1[0x2](und): Audio: aac (LC), 44100 Hz, stereo
"""
    assert parse_ffmpeg_probe(output) == {"duration": 63.5, "width": 1280, "height": 720}


def test_parse_ffmpeg_probe_handles_audio_only() -> None:
    output = "  Duration: 00:00:03.02, start: 0.0\n  Stream #0:0: Audio: mp3, 44100 Hz"
    assert parse_ffmpeg_probe(output) == {"duration": 3.02}


def test_parse_ffmpeg_probe_ignores_64_bit_codec_tags() -> None:
    output = "Stream #0:0: Video: h264 (avc1 / 0x31637661), yuv420p, 640x360"
    assert parse_ffmpeg_probe(output) == {"width": 640, "height": 360}


def test_scan_probes_fields_the_sidecar_left_null(
    settings: Settings, store: Store, library: Library, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_media(
        settings,
        "video",
        "clip.mp4",
        meta={"title": "Clip", "duration": None, "width": None, "height": None},
    )
    monkeypatch.setattr(
        library, "_probe", lambda _: {"duration": 42.0, "width": 1920, "height": 1080}
    )

    library.scan()
    row = store.list_media()[0]

    assert row["title"] == "Clip"
    assert row["duration"] == 42.0
    assert (row["width"], row["height"]) == (1920, 1080)


def test_register_download_probes_metadata_the_source_omitted(
    settings: Settings, store: Store, library: Library, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.ensure_dirs()
    path = settings.video_dir / "Clip [vid1].mp4"
    path.write_bytes(b"video")
    monkeypatch.setattr(library, "_probe", lambda _: {"duration": 7.5, "width": 640, "height": 360})

    media = library.register_download(path, {"title": "Clip", "source_id": "vid1"})

    assert media["duration"] == 7.5
    assert (media["width"], media["height"]) == (640, 360)


def test_clean_title_strips_source_id_suffix() -> None:
    assert clean_title("A long title [dQw4w9WgXcQ]") == "A long title"
    assert clean_title("with_underscores") == "with underscores"
    assert clean_title("   ") == "Untitled"


def test_media_id_is_stable_for_relative_path() -> None:
    assert media_id_for("audio/a.mp3") == media_id_for("audio/a.mp3")
    assert media_id_for("audio/a.mp3") != media_id_for("audio/b.mp3")
    assert len(media_id_for("audio/a.mp3")) == 16
