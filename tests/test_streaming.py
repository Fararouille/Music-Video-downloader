from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from helpers import write_media

from crate.streaming import RangeNotSatisfiable, iter_file, parse_range


def test_missing_range_returns_none() -> None:
    assert parse_range(None, 10) is None
    assert parse_range("  ", 10) is None


def test_closed_range() -> None:
    assert parse_range("bytes=0-3", 10) == (0, 3)
    assert parse_range("bytes=2-2", 10) == (2, 2)


def test_open_ended_range_runs_to_eof() -> None:
    assert parse_range("bytes=5-", 10) == (5, 9)


def test_suffix_range_counts_from_the_end() -> None:
    assert parse_range("bytes=-4", 10) == (6, 9)
    assert parse_range("bytes=-99", 10) == (0, 9)


def test_end_is_clamped_to_file_size() -> None:
    assert parse_range("bytes=7-500", 10) == (7, 9)


def test_multiple_ranges_use_the_first() -> None:
    assert parse_range("bytes=1-2,5-6", 10) == (1, 2)


@pytest.mark.parametrize(
    "header",
    ["items=0-3", "bytes=abc", "bytes=-", "bytes=5-2", "bytes=10-", "bytes=-0"],
)
def test_bad_ranges_raise(header: str) -> None:
    with pytest.raises(RangeNotSatisfiable):
        parse_range(header, 10)


def test_range_on_empty_file_is_unsatisfiable() -> None:
    with pytest.raises(RangeNotSatisfiable):
        parse_range("bytes=0-0", 0)


def test_iter_file_respects_chunk_size(tmp_path: Path) -> None:
    path = tmp_path / "blob.bin"
    path.write_bytes(b"abcdefghij")

    chunks = list(iter_file(path, 2, 5, chunk_size=2))

    assert chunks == [b"cd", b"ef", b"g"]


def test_stream_full_file(client: TestClient) -> None:
    media = client.get("/api/media", params={"kind": "video"}).json()["items"][0]

    response = client.get(f"/api/media/{media['id']}/stream")

    assert response.status_code == 200
    assert response.content == (b"0123456789")
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-length"] == "10"


def test_stream_partial_file(client: TestClient) -> None:
    media = client.get("/api/media", params={"kind": "video"}).json()["items"][0]

    response = client.get(f"/api/media/{media['id']}/stream", headers={"Range": "bytes=2-5"})

    assert response.status_code == 206
    assert response.content == b"2345"
    assert response.headers["content-range"] == "bytes 2-5/10"
    assert response.headers["content-length"] == "4"


def test_stream_unsatisfiable_range(client: TestClient) -> None:
    media = client.get("/api/media", params={"kind": "video"}).json()["items"][0]

    response = client.get(f"/api/media/{media['id']}/stream", headers={"Range": "bytes=99-"})

    assert response.status_code == 416
    assert response.headers["content-range"] == "bytes */10"


def test_download_attachment_headers(client: TestClient) -> None:
    media = client.get("/api/media", params={"kind": "audio"}).json()["items"][0]

    response = client.get(f"/api/media/{media['id']}/file")

    assert response.status_code == 200
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert "filename" in disposition


def test_stream_missing_file_returns_410(client: TestClient, populated) -> None:
    media = client.get("/api/media", params={"kind": "audio"}).json()["items"][0]
    (populated.library / media["path"]).unlink()

    response = client.get(f"/api/media/{media['id']}/stream")

    assert response.status_code == 410


def test_scan_endpoint_indexes_new_files(client: TestClient, populated) -> None:
    write_media(populated, "audio", "hand-added.mp3", meta={"title": "Hand Added"})

    response = client.post("/api/library/scan")

    assert response.status_code == 200
    assert response.json()["added"] == 1
    titles = {item["title"] for item in client.get("/api/media").json()["items"]}
    assert "Hand Added" in titles
