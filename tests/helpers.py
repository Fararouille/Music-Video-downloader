from __future__ import annotations

import json
from pathlib import Path

from crate.config import Settings


def write_media(
    settings: Settings,
    kind: str,
    name: str,
    data: bytes = b"0123456789",
    meta: dict | None = None,
) -> Path:
    folder = settings.audio_dir if kind == "audio" else settings.video_dir
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(data)
    if meta is not None:
        path.with_name(path.stem + ".crate.json").write_text(json.dumps(meta), encoding="utf-8")
    return path
