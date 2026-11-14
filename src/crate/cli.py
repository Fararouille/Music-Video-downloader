from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config import Settings
from .db import Store
from .library import Library

LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="crate", description="download, keep, and play media")
    parser.add_argument("--version", action="version", version=f"crate {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run the API and web UI")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--reload", action="store_true")
    serve.set_defaults(func=cmd_serve)

    scan = sub.add_parser("scan", help="index files added to the library by hand")
    scan.set_defaults(func=cmd_scan)

    info = sub.add_parser("info", help="show configuration and library counts")
    info.set_defaults(func=cmd_info)

    return parser


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    settings = Settings.from_env()
    settings.ensure_dirs()
    host = args.host or settings.host
    port = args.port or settings.port
    if host not in LOOPBACK and not settings.token:
        print(
            "warning: serving on a non-loopback address without CRATE_TOKEN. "
            "Anyone on the network can browse, download, and delete your library.",
            file=sys.stderr,
        )
    print(f"crate {__version__} on http://{host}:{port}")
    if settings.auth_required:
        print("access token required (CRATE_TOKEN is set)")
    uvicorn.run(
        "crate.api:create_app",
        factory=True,
        host=host,
        port=port,
        reload=args.reload,
        log_level="info",
    )
    return 0


def cmd_scan(_: argparse.Namespace) -> int:
    settings = Settings.from_env()
    settings.ensure_dirs()
    store = Store(settings.db_path)
    library = Library(settings, store)
    result = library.scan()
    print(json.dumps({**result, **store.count_media()}, indent=2))
    return 0


def cmd_info(_: argparse.Namespace) -> int:
    settings = Settings.from_env()
    store = Store(settings.db_path)
    counts = store.count_media()
    frontend = Path(settings.frontend) if settings.frontend else None
    payload = {
        "version": __version__,
        "library": str(settings.library),
        "database": str(settings.db_path),
        "media": counts,
        "playlists": len(store.list_playlists()),
        "ffmpeg": settings.ffmpeg or "missing",
        "yt-dlp": _installed_version("yt-dlp"),
        "auth": "token required" if settings.auth_required else "open (loopback use)",
        "ui": str(frontend) if frontend else "not built",
    }
    print(json.dumps(payload, indent=2))
    return 0


def _installed_version(name: str) -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version(name)
    except PackageNotFoundError:
        return "missing"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        return 130
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
