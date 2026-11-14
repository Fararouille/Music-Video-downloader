from __future__ import annotations

import ipaddress
import socket
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .config import Settings
from .library import MEDIA_EXTS

VIDEO_QUALITIES = ("best", "2160", "1440", "1080", "720", "480", "360")
AUDIO_QUALITIES = ("320", "192", "128")

AUDIO_SUFFIXES = {".mp3", ".m4a", ".opus", ".ogg", ".oga", ".flac", ".wav", ".aac", ".weba"}
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")


class DownloadError(RuntimeError):
    pass


class Cancelled(DownloadError):
    pass


@dataclass(frozen=True)
class Progress:
    fraction: float
    speed: str | None = None
    eta: int | None = None
    title: str | None = None


@dataclass(frozen=True)
class Downloaded:
    path: Path
    metadata: dict
    thumbnail: Path | None


def validate_url(url: str, *, allow_private: bool) -> str:
    """Reject anything that is not a public http(s) URL.

    yt-dlp will fetch arbitrary URLs, so the API refuses local targets by default.
    Set ``CRATE_ALLOW_PRIVATE_URLS=1`` to allow loopback/private addresses (tests,
    or a media server on your own LAN).
    """
    candidate = url.strip()
    if not candidate:
        raise ValueError("paste a URL to download")
    if len(candidate) > 2048:
        raise ValueError("URL is too long")
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("only http and https URLs are supported")
    host = parsed.hostname
    if not host:
        raise ValueError("URL has no host")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise ValueError("URL has an invalid port") from exc
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"cannot resolve {host}") from exc
    if not addresses:
        raise ValueError(f"cannot resolve {host}")
    if allow_private:
        return candidate
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if ip.version == 6 and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ValueError(
                "refusing to download from a private or local address; "
                "set CRATE_ALLOW_PRIVATE_URLS=1 to allow it"
            )
    return candidate


def video_format(quality: str, *, has_ffmpeg: bool) -> str:
    height = None if quality == "best" else int(quality)
    if height is None:
        return "bv*+ba/b" if has_ffmpeg else "b"
    if has_ffmpeg:
        return f"bv*[height<={height}]+ba/b[height<={height}]/b"
    return f"b[height<={height}]/b"


def audio_options(quality: str) -> list[dict]:
    return [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": quality,
        }
    ]


def format_speed(value: float | None) -> str | None:
    if not value:
        return None
    for unit in ("B/s", "KiB/s", "MiB/s", "GiB/s"):
        if value < 1024 or unit == "GiB/s":
            return f"{value:.1f} {unit}" if unit != "B/s" else f"{int(value)} B/s"
        value /= 1024
    return None


class Downloader:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _options(self, job: dict, hook: Callable[[dict], None]) -> dict:
        kind = job["kind"]
        quality = job["quality"]
        ffmpeg = self.settings.ffmpeg
        target = self.settings.audio_dir if kind == "audio" else self.settings.video_dir

        options: dict = {
            "format": (
                video_format(quality, has_ffmpeg=bool(ffmpeg)) if kind == "video" else "ba/b"
            ),
            "outtmpl": str(target / "%(title).120B [%(id)s].%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "windowsfilenames": True,
            "writethumbnail": True,
            "overwrites": True,
            "continuedl": True,
            "retries": 3,
            "fragment_retries": 3,
            "concurrent_fragment_downloads": 4,
            "socket_timeout": 30,
            "cachedir": str(self.settings.cache_dir),
            "progress_hooks": [hook],
            "format_sort": ["res", "ext:mp4:m4a"],
        }
        if ffmpeg:
            options["ffmpeg_location"] = ffmpeg
            if kind == "video":
                options["merge_output_format"] = "mp4"
        if kind == "audio":
            if not ffmpeg:
                raise DownloadError(
                    "MP3 conversion needs ffmpeg; install it or use the bundled "
                    "imageio-ffmpeg package"
                )
            options["postprocessors"] = audio_options(quality)
        if self.settings.cookies_file:
            if not self.settings.cookies_file.is_file():
                raise DownloadError(f"cookie file not found: {self.settings.cookies_file}")
            options["cookiefile"] = str(self.settings.cookies_file)
        return options

    def download(
        self,
        job: dict,
        on_progress: Callable[[Progress], None],
        cancel: threading.Event,
    ) -> Downloaded:
        try:
            import yt_dlp
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise DownloadError("yt-dlp is not installed") from exc

        target = self.settings.audio_dir if job["kind"] == "audio" else self.settings.video_dir
        target.mkdir(parents=True, exist_ok=True)

        def hook(status: dict) -> None:
            if cancel.is_set():
                raise Cancelled("download cancelled")
            info = status.get("info_dict") or {}
            title = info.get("title") or None
            if status.get("status") == "downloading":
                total = status.get("total_bytes") or status.get("total_bytes_estimate") or 0
                done = status.get("downloaded_bytes") or 0
                fraction = min(0.98, done / total) if total else 0.05
                on_progress(
                    Progress(fraction, format_speed(status.get("speed")), status.get("eta"), title)
                )
            elif status.get("status") == "finished":
                on_progress(Progress(0.98, None, None, title))

        options = self._options(job, hook)
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(job["url"], download=True)
        except Exception as exc:
            if cancel.is_set():
                raise Cancelled("download cancelled") from exc
            message = str(exc).replace("ERROR: ", "").strip()
            raise DownloadError(message or "the download failed") from exc
        if cancel.is_set():
            raise Cancelled("download cancelled")
        if not isinstance(info, dict):
            raise DownloadError("the site returned no media information")
        if info.get("_type") == "playlist" and info.get("entries"):
            info = info["entries"][0]
        path = self._locate_media(target, info)
        thumbnail = self._locate_thumbnail(target, info)
        metadata = {
            "title": info.get("title") or path.stem,
            "artist": info.get("artist") or info.get("uploader") or info.get("creator"),
            "album": info.get("album"),
            "duration": _float_or_none(info.get("duration")),
            "width": info.get("width"),
            "height": info.get("height"),
            "source_url": info.get("webpage_url") or job["url"],
            "source_id": str(info["id"]) if info.get("id") else None,
        }
        return Downloaded(path=path, metadata=metadata, thumbnail=thumbnail)

    def _locate_media(self, target: Path, info: dict) -> Path:
        candidates: list[Path] = []
        for item in info.get("requested_downloads") or []:
            if isinstance(item, dict) and item.get("filepath"):
                candidates.append(Path(item["filepath"]))
        for key in ("filepath", "_filename"):
            value = info.get(key)
            if value:
                candidates.append(Path(value))
        video_id = info.get("id")
        if video_id:
            candidates.extend(
                path for path in target.glob(f"*[{video_id}]*") if path.suffix.lower() in MEDIA_EXTS
            )
        for candidate in candidates:
            if candidate.is_file() and candidate.suffix.lower() in MEDIA_EXTS:
                return candidate.resolve()
        raise DownloadError("the download finished but no media file was found")

    def _locate_thumbnail(self, target: Path, info: dict) -> Path | None:
        video_id = info.get("id")
        if not video_id:
            return None
        images = [
            path
            for path in target.glob(f"*[{video_id}]*")
            if path.suffix.lower() in IMAGE_SUFFIXES and path.is_file()
        ]
        if not images:
            return None
        return max(images, key=lambda path: path.stat().st_mtime).resolve()

    def cleanup(self, job: dict) -> None:
        """Remove partial files left by a cancelled or failed job."""
        target = self.settings.audio_dir if job["kind"] == "audio" else self.settings.video_dir
        if not target.is_dir():
            return
        for pattern in ("*.part", "*.ytdl", "*.temp"):
            for path in target.glob(pattern):
                path.unlink(missing_ok=True)


def _float_or_none(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None
