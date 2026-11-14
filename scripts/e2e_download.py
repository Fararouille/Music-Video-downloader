"""End-to-end download check against a local HTTP server.

Generates a small MP4 with ffmpeg, serves it from loopback, starts crate with
private URLs enabled, enqueues an MP4 and an MP3 job through the real API, then
checks metadata, indexing, sidecars, and Range streaming.

    python scripts/e2e_download.py

No internet access is needed. Exit code 0 means the whole pipeline works.
"""

from __future__ import annotations

import functools
import http.server
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from email.message import Message
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = "Portable Sample Clip.mp4"
TITLE = "Portable Sample Clip"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request(
    base: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict | None = None,
    headers: dict | None = None,
) -> tuple[int, bytes, dict]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    merged = dict(headers or {})
    if body is not None:
        merged["Content-Type"] = "application/json"
    call = urllib.request.Request(base + path, data=body, method=method, headers=merged)
    try:
        with urllib.request.urlopen(call, timeout=30) as response:
            return response.status, response.read(), _lower_headers(response.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), _lower_headers(exc.headers)


def wait_for(predicate: Callable[[], object], timeout: float, label: str) -> object:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.5)
    raise TimeoutError(f"timed out waiting for {label}")


def server_up(base: str) -> bool:
    try:
        with urllib.request.urlopen(base + "/api/health", timeout=2) as response:
            return response.status == 200
    except OSError:
        return False


def _lower_headers(headers: Message) -> dict[str, str]:
    return {key.lower(): value for key, value in headers.items()}


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> int:
    from crate.config import discover_ffmpeg

    ffmpeg = discover_ffmpeg()
    if not ffmpeg:
        print("error: ffmpeg is required for this check", file=sys.stderr)
        return 2

    work = Path(tempfile.mkdtemp(prefix="crate-e2e-"))
    log_path = work / "server.log"
    log = log_path.open("w", encoding="utf-8")
    sample_dir = work / "served"
    sample_dir.mkdir()
    sample = sample_dir / SAMPLE
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=640x360:rate=24:duration=3",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=330:duration=3",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            "-movflags",
            "+faststart",
            str(sample),
        ],
        check=True,
    )
    print(f"generated {sample.name} ({sample.stat().st_size} bytes)")

    media_port = free_port()
    handler = functools.partial(QuietHandler, directory=str(sample_dir))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", media_port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    api_port = free_port()
    base = f"http://127.0.0.1:{api_port}"
    environment = {
        **os.environ,
        "CRATE_LIBRARY": str(work / "library"),
        "CRATE_DB": str(work / "data" / "crate.db"),
        "CRATE_ALLOW_PRIVATE_URLS": "1",
    }
    server = subprocess.Popen(
        [sys.executable, "-m", "crate", "serve", "--host", "127.0.0.1", "--port", str(api_port)],
        cwd=ROOT,
        env=environment,
        stdout=log,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        wait_for(lambda: server_up(base), 45, "the API to start")
        print("API is up")

        source = f"http://127.0.0.1:{media_port}/{SAMPLE.replace(' ', '%20')}"
        for kind, quality in (("video", "720"), ("audio", "192")):
            status, body, _ = request(
                base,
                "/api/downloads",
                method="POST",
                payload={"url": source, "kind": kind, "quality": quality},
            )
            if status != 201:
                raise SystemExit(f"enqueue {kind} failed: {status} {body!r}")
            print(f"queued {kind} job {json.loads(body)['id']}")

        def finished() -> dict[str, str] | None:
            _, body, _ = request(base, "/api/downloads")
            states = {item["id"]: item["status"] for item in json.loads(body)["items"]}
            if any(state in {"error", "canceled"} for state in states.values()):
                raise SystemExit(f"a job failed: {states}")
            return states if states and all(v == "done" for v in states.values()) else None

        wait_for(finished, 240, "both downloads to finish")
        print("both jobs finished")

        _, body, _ = request(base, "/api/media?limit=50")
        media = json.loads(body)["items"]
        kinds = sorted(item["kind"] for item in media)
        if kinds != ["audio", "video"]:
            raise SystemExit(f"expected one audio and one video, got {kinds}")

        video = next(item for item in media if item["kind"] == "video")
        audio = next(item for item in media if item["kind"] == "audio")
        print(
            f"indexed video: {video['ext']}, {video['duration']}s, "
            f"{video['width']}x{video['height']}, {video['size']} bytes"
        )
        print(f"indexed audio: {audio['ext']}, {audio['duration']}s, {audio['size']} bytes")
        assert video["ext"] == "mp4", video["ext"]
        assert video["title"] == TITLE, video["title"]
        assert video["duration"] and 2.5 < video["duration"] < 4.5, video["duration"]
        assert (video["width"], video["height"]) == (640, 360), video
        assert audio["ext"] == "mp3", audio["ext"]
        assert audio["duration"] and 2.5 < audio["duration"] < 4.5, audio["duration"]

        status, chunk, headers = request(
            base,
            f"/api/media/{video['id']}/stream",
            headers={"Range": "bytes=0-99"},
        )
        print(
            f"range request: {status} {headers.get('content-range')} "
            f"({len(chunk)} bytes, accept-ranges={headers.get('accept-ranges')})"
        )
        assert status == 206, status
        assert len(chunk) == 100, len(chunk)
        assert headers["content-range"].startswith("bytes 0-99/"), headers["content-range"]

        status, _, headers = request(base, f"/api/media/{video['id']}/file")
        print(f"attachment request: {status} {headers.get('content-disposition')}")
        assert status == 200
        assert "attachment" in headers.get("content-disposition", "")
        assert request(base, "/api/downloads/nope/retry", method="POST")[0] == 409

        sidecars = sorted((work / "library").rglob("*.crate.json"))
        print(f"sidecars written: {', '.join(path.name for path in sidecars)}")
        assert len(sidecars) == 2, sidecars

        print("E2E OK")
        return 0
    except Exception:
        log.flush()
        print("\n--- server log ---", file=sys.stderr)
        print(log_path.read_text(encoding="utf-8")[-4000:], file=sys.stderr)
        raise
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        log.close()
        httpd.shutdown()
        httpd.server_close()
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
