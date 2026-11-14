from __future__ import annotations

import pytest

from crate.downloader import (
    audio_options,
    format_speed,
    validate_url,
    video_format,
)


@pytest.mark.parametrize("url", ["", "   ", "ftp://example.com/a", "not a url", "//example.com/a"])
def test_validate_url_rejects_non_http(url: str) -> None:
    with pytest.raises(ValueError):
        validate_url(url, allow_private=False)


def test_validate_url_rejects_loopback_by_default() -> None:
    with pytest.raises(ValueError, match="private or local"):
        validate_url("http://127.0.0.1:8080/audio.mp3", allow_private=False)


def test_validate_url_allows_loopback_when_opted_in() -> None:
    url = "http://127.0.0.1:8080/audio.mp3"

    assert validate_url(url, allow_private=True) == url


def test_validate_url_rejects_localhost_by_default() -> None:
    with pytest.raises(ValueError, match="private or local"):
        validate_url("http://localhost:9000/x", allow_private=False)


def test_validate_url_allows_lan_when_opted_in() -> None:
    url = "http://192.168.1.20:9000/library/x.mp3"

    assert validate_url(url, allow_private=True) == url


def test_validate_url_rejects_invalid_port() -> None:
    with pytest.raises(ValueError, match="port"):
        validate_url("http://127.0.0.1:99999/x", allow_private=True)


def test_video_format_without_ffmpeg_uses_single_file() -> None:
    assert video_format("best", has_ffmpeg=False) == "b"
    assert video_format("720", has_ffmpeg=False) == "b[height<=720]/b"


def test_video_format_with_ffmpeg_merges_streams() -> None:
    assert video_format("best", has_ffmpeg=True) == "bv*+ba/b"
    assert video_format("1080", has_ffmpeg=True) == "bv*[height<=1080]+ba/b[height<=1080]/b"


def test_audio_options_request_mp3_at_the_chosen_bitrate() -> None:
    assert audio_options("192") == [
        {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
    ]


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, None), (0, None), (512, "512 B/s"), (2048, "2.0 KiB/s"), (5 * 1024**2, "5.0 MiB/s")],
)
def test_format_speed(value: float | None, expected: str | None) -> None:
    assert format_speed(value) == expected
