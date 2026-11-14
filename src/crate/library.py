from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from .config import Settings
from .db import Store, utcnow

AUDIO_EXTS = {".mp3", ".m4a", ".opus", ".ogg", ".oga", ".flac", ".wav", ".aac", ".weba"}
VIDEO_EXTS = {".mp4", ".webm", ".mkv", ".mov", ".m4v", ".avi"}
MEDIA_EXTS = AUDIO_EXTS | VIDEO_EXTS

MIME_TYPES = {
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".opus": "audio/ogg",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".flac": "audio/flac",
    ".wav": "audio/wav",
    ".aac": "audio/aac",
    ".weba": "audio/webm",
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
}

THUMB_EXTS = (".jpg", ".jpeg", ".png", ".webp")

DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
VIDEO_SIZE_RE = re.compile(r"Video:.*?\b(\d{2,5})x(\d{2,5})\b")


def parse_ffmpeg_probe(output: str) -> dict:
    """Read duration and frame size from ``ffmpeg -i`` output.

    Used when ffprobe is unavailable but ffmpeg is present (the binary bundled
    with imageio-ffmpeg is a plain ffmpeg build).
    """
    result: dict = {}
    match = DURATION_RE.search(output)
    if match:
        hours, minutes, seconds = match.groups()
        total = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        if total > 0:
            result["duration"] = round(total, 3)
    for line in output.splitlines():
        if "Video:" not in line:
            continue
        size = VIDEO_SIZE_RE.search(line)
        if size:
            result["width"] = int(size.group(1))
            result["height"] = int(size.group(2))
            break
    return result


def media_id_for(relative_path: str) -> str:
    return hashlib.sha1(relative_path.encode("utf-8")).hexdigest()[:16]


def kind_for(extension: str) -> str:
    return "audio" if extension.lower() in AUDIO_EXTS else "video"


def mime_for(extension: str) -> str:
    return MIME_TYPES.get(extension.lower(), "application/octet-stream")


def clean_title(stem: str) -> str:
    title = stem
    if title.endswith("]") and " [" in title:
        title = title.rsplit(" [", 1)[0]
    return title.replace("_", " ").strip() or "Untitled"


class Library:
    def __init__(self, settings: Settings, store: Store):
        self.settings = settings
        self.store = store
        self.root = settings.library
        self.root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ paths

    def resolve(self, relative_path: str) -> Path:
        candidate = (self.root / relative_path).resolve()
        if not candidate.is_relative_to(self.root):
            raise ValueError(f"path escapes the library: {relative_path}")
        return candidate

    def _sidecar(self, path: Path) -> Path:
        return path.with_name(path.stem + ".crate.json")

    def thumb_path(self, row: dict) -> Path | None:
        thumb = row.get("thumbnail")
        return self.resolve(thumb) if thumb else None

    def has_thumb(self, row: dict) -> bool:
        path = self.thumb_path(row)
        return bool(path and path.is_file())

    # --------------------------------------------------------------- scanning

    def scan(self) -> dict:
        indexed = {row["path"]: row for row in self.store.list_media(limit=100_000)}
        seen: set[str] = set()
        added = 0
        updated = 0

        for kind, folder in (
            ("audio", self.settings.audio_dir),
            ("video", self.settings.video_dir),
        ):
            if not folder.is_dir():
                continue
            for path in sorted(folder.rglob("*")):
                if not path.is_file():
                    continue
                suffix = path.suffix.lower()
                if suffix not in MEDIA_EXTS or path.name.startswith("."):
                    continue
                relative = path.relative_to(self.root).as_posix()
                seen.add(relative)
                existing = indexed.get(relative)
                size = path.stat().st_size
                if existing:
                    if existing["size"] != size:
                        with self.store.connect() as connection:
                            connection.execute(
                                "UPDATE media SET size = ? WHERE id = ?", (size, existing["id"])
                            )
                            connection.commit()
                        updated += 1
                    continue
                metadata = self._metadata(path)
                self.store.upsert_media(self._row_for(path, kind, metadata))
                added += 1

        removed = 0
        for relative, row in indexed.items():
            if relative not in seen:
                self.store.delete_media(row["id"])
                removed += 1

        return {"added": added, "updated": updated, "removed": removed}

    def _row_for(self, path: Path, kind: str, metadata: dict) -> dict:
        relative = path.relative_to(self.root).as_posix()
        thumbnail = None
        sibling = self._sibling_thumbnail(path)
        if sibling is not None:
            thumbnail = sibling.relative_to(self.root).as_posix()
        return {
            "id": media_id_for(relative),
            "kind": kind,
            "path": relative,
            "title": metadata.get("title") or clean_title(path.stem),
            "artist": metadata.get("artist"),
            "album": metadata.get("album"),
            "duration": metadata.get("duration"),
            "size": path.stat().st_size,
            "ext": path.suffix.lower().lstrip("."),
            "mime": mime_for(path.suffix),
            "width": metadata.get("width"),
            "height": metadata.get("height"),
            "source_url": metadata.get("source_url"),
            "source_id": metadata.get("source_id"),
            "thumbnail": thumbnail,
            "added_at": utcnow(),
            "played_at": None,
            "play_count": 0,
            "favorite": 0,
        }

    def _metadata(self, path: Path) -> dict:
        metadata: dict = {}
        sidecar = self._sidecar(path)
        if sidecar.is_file():
            try:
                payload = json.loads(sidecar.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    metadata = payload
            except (OSError, ValueError):
                metadata = {}
        metadata = self._merge_metadata(path, metadata)
        metadata.setdefault("title", clean_title(path.stem))
        return metadata

    def _merge_metadata(self, path: Path, metadata: dict) -> dict:
        """Drop nulls and probe the file for anything the source did not report."""
        clean = {key: value for key, value in metadata.items() if value is not None}
        is_video = path.suffix.lower() in VIDEO_EXTS
        needs_duration = not clean.get("duration")
        needs_size = is_video and not (clean.get("width") and clean.get("height"))
        if not (needs_duration or needs_size):
            return clean
        return {**self._probe(path), **clean}

    def _sibling_thumbnail(self, path: Path) -> Path | None:
        for suffix in THUMB_EXTS:
            candidate = path.with_suffix(suffix)
            if candidate.is_file():
                return candidate
        return None

    def _probe(self, path: Path) -> dict:
        executable = ffprobe_for(self.settings.ffmpeg)
        if executable:
            probed = self._probe_ffprobe(executable, path)
            if probed:
                return probed
        return self._probe_ffmpeg(path)

    def _probe_ffprobe(self, executable: str, path: Path) -> dict:
        command = [
            executable,
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=width,height",
            "-of",
            "json",
            str(path),
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            payload = json.loads(completed.stdout or "{}")
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return {}
        stream = next((item for item in payload.get("streams", []) if item.get("width")), {})
        duration = payload.get("format", {}).get("duration")
        result: dict = {}
        if duration:
            try:
                result["duration"] = float(duration)
            except (TypeError, ValueError):
                pass
        if stream.get("width") and stream.get("height"):
            result["width"] = stream["width"]
            result["height"] = stream["height"]
        return result

    def _probe_ffmpeg(self, path: Path) -> dict:
        """Fallback probe for when ffprobe is missing: ffmpeg prints metadata on stderr."""
        executable = self.settings.ffmpeg
        if not executable:
            return {}
        try:
            completed = subprocess.run(
                [executable, "-hide_banner", "-nostdin", "-i", str(path)],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except (OSError, subprocess.TimeoutExpired):
            return {}
        return parse_ffmpeg_probe(completed.stderr or "")

    # -------------------------------------------------------------- downloads

    def register_download(self, path: Path, metadata: dict, thumbnail: Path | None = None) -> dict:
        path = path.resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("downloaded file is outside the library")
        relative = path.relative_to(self.root).as_posix()
        kind = kind_for(path.suffix)
        metadata = self._merge_metadata(path, metadata)

        existing = None
        if metadata.get("source_id"):
            existing = self.store.find_media_by_source(str(metadata["source_id"]), kind)
        media_id = existing["id"] if existing else media_id_for(relative)

        owner = self.store.find_media_by_path(relative)
        if owner and owner["id"] != media_id:
            self.store.delete_media(owner["id"])

        if existing and existing["path"] != relative:
            self._unlink_row_files(existing, keep=path, keep_thumb=True)

        thumbnail_relative = existing.get("thumbnail") if existing else None
        if thumbnail is not None and thumbnail.is_file():
            suffix = thumbnail.suffix.lower()
            if suffix not in THUMB_EXTS:
                suffix = ".jpg"
            destination = self.settings.thumbs_dir / f"{media_id}{suffix}"
            destination.parent.mkdir(parents=True, exist_ok=True)
            for old in destination.parent.glob(f"{media_id}.*"):
                old.unlink(missing_ok=True)
            shutil.move(str(thumbnail), destination)
            thumbnail_relative = destination.relative_to(self.root).as_posix()

        row = {
            "id": media_id,
            "kind": kind,
            "path": relative,
            "title": metadata.get("title") or clean_title(path.stem),
            "artist": metadata.get("artist"),
            "album": metadata.get("album"),
            "duration": metadata.get("duration"),
            "size": path.stat().st_size,
            "ext": path.suffix.lower().lstrip("."),
            "mime": mime_for(path.suffix),
            "width": metadata.get("width") if kind == "video" else None,
            "height": metadata.get("height") if kind == "video" else None,
            "source_url": metadata.get("source_url"),
            "source_id": metadata.get("source_id"),
            "thumbnail": thumbnail_relative,
            "added_at": existing["added_at"] if existing else utcnow(),
            "played_at": existing["played_at"] if existing else None,
            "play_count": existing["play_count"] if existing else 0,
            "favorite": existing["favorite"] if existing else 0,
        }
        self._write_sidecar(path, row)
        self.store.upsert_media(row)
        return self.store.get_media(media_id)  # type: ignore[return-value]

    def _write_sidecar(self, path: Path, row: dict) -> None:
        payload = {
            "title": row["title"],
            "artist": row.get("artist"),
            "album": row.get("album"),
            "duration": row.get("duration"),
            "width": row.get("width"),
            "height": row.get("height"),
            "source_url": row.get("source_url"),
            "source_id": row.get("source_id"),
        }
        try:
            self._sidecar(path).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass

    def delete(self, media_id: str) -> bool:
        row = self.store.get_media(media_id)
        if row is None:
            return False
        self._unlink_row_files(row)
        self.store.delete_media(media_id)
        return True

    def _unlink_row_files(
        self, row: dict, keep: Path | None = None, keep_thumb: bool = False
    ) -> None:
        try:
            path = self.resolve(row["path"])
        except ValueError:
            path = None
        if path and path.is_file() and path != keep:
            path.unlink(missing_ok=True)
        if path:
            sidecar = self._sidecar(path)
            if sidecar.is_file():
                sidecar.unlink(missing_ok=True)
        if not keep_thumb:
            thumb = self.thumb_path(row)
            if thumb and thumb.is_file() and thumb != keep:
                thumb.unlink(missing_ok=True)


def ffprobe_for(ffmpeg: str | None) -> str | None:
    if ffmpeg:
        candidate = Path(ffmpeg).with_name("ffprobe" + (".exe" if os.name == "nt" else ""))
        if candidate.is_file():
            return str(candidate)
    return shutil.which("ffprobe")
