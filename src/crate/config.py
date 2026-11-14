from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc


def _env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name)
    if raw and raw.strip():
        return Path(raw).expanduser().resolve()
    return default.resolve()


@dataclass(frozen=True)
class Settings:
    root: Path
    library: Path
    db_path: Path
    host: str = "127.0.0.1"
    port: int = 8000
    token: str = ""
    allow_private_urls: bool = False
    cookies_file: Path | None = None
    secure_cookies: bool = False
    ffmpeg: str | None = None
    frontend: Path | None = None

    @classmethod
    def from_env(cls, root: Path | None = None) -> Settings:
        root = (root or Path.cwd()).resolve()
        cookies = os.environ.get("CRATE_COOKIES", "").strip()
        configured_frontend = os.environ.get("CRATE_FRONTEND", "").strip()
        frontend = (
            Path(configured_frontend).expanduser().resolve()
            if configured_frontend
            else Path(__file__).resolve().parents[2] / "frontend" / "dist"
        )
        return cls(
            root=root,
            library=_env_path("CRATE_LIBRARY", root / "library"),
            db_path=_env_path("CRATE_DB", root / "data" / "crate.db"),
            host=os.environ.get("CRATE_HOST", "127.0.0.1"),
            port=_env_int("CRATE_PORT", 8000),
            token=os.environ.get("CRATE_TOKEN", "").strip(),
            allow_private_urls=_env_bool("CRATE_ALLOW_PRIVATE_URLS"),
            cookies_file=Path(cookies).expanduser().resolve() if cookies else None,
            secure_cookies=_env_bool("CRATE_SECURE_COOKIES"),
            ffmpeg=discover_ffmpeg(),
            frontend=frontend if (frontend / "index.html").is_file() else None,
        )

    @property
    def audio_dir(self) -> Path:
        return self.library / "audio"

    @property
    def video_dir(self) -> Path:
        return self.library / "video"

    @property
    def thumbs_dir(self) -> Path:
        return self.library / "thumbnails"

    @property
    def cache_dir(self) -> Path:
        return self.db_path.parent / "yt-dlp-cache"

    @property
    def auth_required(self) -> bool:
        return bool(self.token)

    def ensure_dirs(self) -> None:
        for directory in (
            self.library,
            self.audio_dir,
            self.video_dir,
            self.thumbs_dir,
            self.db_path.parent,
            self.cache_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)


def discover_ffmpeg() -> str | None:
    """Prefer an explicit path, then PATH, then the binary bundled with imageio-ffmpeg."""
    configured = os.environ.get("CRATE_FFMPEG", "").strip()
    if configured:
        path = Path(configured).expanduser()
        if path.is_file():
            return str(path)
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None
