"""Create the demo library used in the screenshots.

Generates short royalty-free test tones and test-pattern clips with ffmpeg,
writes ``.crate.json`` sidecars, indexes everything, then builds the "Late
night" playlist and marks two favorites. Safe to run more than once.

    python scripts/seed_demo.py [--root .] [--force]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from crate.config import Settings
from crate.db import Store
from crate.library import Library

TRACKS = [
    ("Night Drive", "a1b2c3d4e5f6", "Kite", "Harbor", 222, 220, "8b5cf6", "1e1b4b"),
    ("Soft Focus", "b2c3d4e5f6a1", "Moth", "Slow Light", 178, 262, "22d3ee", "0f172a"),
    ("Harbor Lights", "c3d4e5f6a1b2", "Kite", "Harbor", 252, 294, "38bdf8", "1e3a8a"),
    ("Paper Planes", "d4e5f6a1b2c3", "June Atlas", "Postcards", 201, 330, "f472b6", "831843"),
    ("Static Bloom", "e5f6a1b2c3d4", "Wren", "Static Bloom", 164, 349, "a3e635", "365314"),
    ("Midnight Ferry", "f6a1b2c3d4e5", "Kite", "Harbor", 303, 196, "6366f1", "111827"),
    ("Afterglow", "a7b8c9d0e1f2", "Moth", "Slow Light", 215, 392, "fb923c", "7c2d12"),
    ("Low Tide", "b8c9d0e1f2a3", "June Atlas", "Postcards", 146, 440, "2dd4bf", "134e4a"),
]

VIDEOS = [
    ("First Light", "vid0001first", "Kite", 95, 1920, 1080, 240, "f59e0b", "7c2d12"),
    ("Neon Run", "vid0002neon", "Wren", 130, 1280, 720, 320, "ec4899", "4c1d95"),
    ("Rain on Glass", "vid0003rain", "Moth", 185, 1920, 1080, 180, "60a5fa", "1e293b"),
]

PLAYLIST = ("Late night", ["Night Drive", "Soft Focus", "Midnight Ferry", "Afterglow"])
FAVORITES = ("Night Drive", "First Light")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="project root (default: current directory)")
    parser.add_argument("--force", action="store_true", help="regenerate existing media files")
    args = parser.parse_args()

    settings = Settings.from_env(Path(args.root))
    settings.ensure_dirs()
    ffmpeg = settings.ffmpeg
    if not ffmpeg:
        print("error: ffmpeg not found; install it or pip install imageio-ffmpeg", file=sys.stderr)
        return 2

    for title, source_id, artist, album, duration, hz, c0, c1 in TRACKS:
        stem = f"{title} [{source_id}]"
        audio = settings.audio_dir / f"{stem}.mp3"
        cover = settings.audio_dir / f"{stem}.jpg"
        if args.force or not audio.is_file():
            _ffmpeg(
                ffmpeg,
                [
                    "-f",
                    "lavfi",
                    "-i",
                    f"sine=frequency={hz}:duration=40",
                    "-c:a",
                    "libmp3lame",
                    "-b:a",
                    "192k",
                    str(audio),
                ],
            )
        if args.force or not cover.is_file():
            _cover(ffmpeg, cover, c0, c1)
        _sidecar(
            audio,
            title=title,
            artist=artist,
            album=album,
            duration=duration,
            source_id=source_id,
        )

    for title, source_id, artist, duration, width, height, hz, c0, c1 in VIDEOS:
        stem = f"{title} [{source_id}]"
        video = settings.video_dir / f"{stem}.mp4"
        cover = settings.video_dir / f"{stem}.jpg"
        if args.force or not video.is_file():
            _ffmpeg(
                ffmpeg,
                [
                    "-f",
                    "lavfi",
                    "-i",
                    f"testsrc2=size={width}x{height}:rate=24:duration=15",
                    "-f",
                    "lavfi",
                    "-i",
                    f"sine=frequency={hz}:duration=15",
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
                    str(video),
                ],
            )
        if args.force or not cover.is_file():
            _cover(ffmpeg, cover, c0, c1)
        _sidecar(
            video,
            title=title,
            artist=artist,
            duration=duration,
            width=width,
            height=height,
            source_id=source_id,
        )

    store = Store(settings.db_path)
    library = Library(settings, store)
    library.scan()

    rows = {row["title"]: row for row in store.list_media(limit=1000)}
    playlist_name, titles = PLAYLIST
    existing = next((p for p in store.list_playlists() if p["name"] == playlist_name), None)
    playlist = existing or store.create_playlist(playlist_name)
    for title in titles:
        if title in rows:
            store.add_playlist_item(playlist["id"], rows[title]["id"])
    for title in FAVORITES:
        if title in rows:
            store.update_media(rows[title]["id"], {"favorite": 1})

    counts = store.count_media()
    print(
        f"seeded {counts['audio']} tracks and {counts['video']} videos, "
        f"playlist {playlist_name!r} with {len(titles)} entries"
    )
    print(f"library {settings.library}")
    print("next: python -m crate serve")
    return 0


def _ffmpeg(executable: str, arguments: list[str]) -> None:
    subprocess.run(
        [executable, "-hide_banner", "-loglevel", "error", "-y", *arguments],
        check=True,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )


def _cover(executable: str, destination: Path, c0: str, c1: str) -> None:
    grid = "drawgrid=w=80:h=80:t=2:c=white@0.06"
    filters = [
        f"gradients=s=640x640:c0=0x{c0}:c1=0x{c1}:x0=0:y0=0:x1=640:y1=640:duration=1,{grid}",
        f"color=c=0x{c0}:s=640x640:d=1,{grid}",
    ]
    for index, source in enumerate(filters):
        try:
            _ffmpeg(executable, ["-f", "lavfi", "-i", source, "-frames:v", "1", str(destination)])
            return
        except subprocess.CalledProcessError:
            if index == len(filters) - 1:
                raise


def _sidecar(path: Path, **metadata: object) -> None:
    payload = {key: value for key, value in metadata.items() if value is not None}
    payload["source_url"] = f"https://www.youtube.com/watch?v={metadata['source_id']}"
    path.with_name(path.stem + ".crate.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    sys.exit(main())
