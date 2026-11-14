from __future__ import annotations

import hmac
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from . import __version__
from .auth import SESSION_COOKIE, authenticated, session_value
from .config import Settings
from .db import Store
from .downloader import AUDIO_QUALITIES, VIDEO_QUALITIES, Downloader
from .jobs import JobManager
from .library import Library
from .streaming import attachment_header, file_response

SESSION_AGE = 60 * 60 * 24 * 30


class DownloadIn(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    kind: Literal["audio", "video"] = "video"
    quality: str | None = None

    @model_validator(mode="after")
    def _default_quality(self) -> DownloadIn:
        allowed = AUDIO_QUALITIES if self.kind == "audio" else VIDEO_QUALITIES
        if self.quality is None:
            self.quality = "192" if self.kind == "audio" else "1080"
        elif self.quality not in allowed:
            raise ValueError(f"quality must be one of {', '.join(allowed)}")
        return self


class PlaylistIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class PlaylistItemIn(BaseModel):
    media_id: str = Field(min_length=1, max_length=64)


class PlaylistOrderIn(BaseModel):
    media_ids: list[str]


class MediaPatch(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    artist: str | None = Field(default=None, max_length=300)
    album: str | None = Field(default=None, max_length=300)
    favorite: bool | None = None


class LoginIn(BaseModel):
    token: str = Field(min_length=1, max_length=512)


def _package_version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def create_app(settings: Settings | None = None, *, start_worker: bool = True) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.ensure_dirs()
    store = Store(settings.db_path)
    library = Library(settings, store)
    library.scan()
    downloader = Downloader(settings)
    manager = JobManager(
        store,
        downloader,
        library,
        allow_private_urls=settings.allow_private_urls,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if start_worker:
            manager.start()
        try:
            yield
        finally:
            manager.stop()

    app = FastAPI(title="crate", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.store = store
    app.state.library = library
    app.state.manager = manager

    def require_auth(request: Request) -> None:
        if not authenticated(settings, request):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )

    def media_out(row: dict) -> dict:
        payload = dict(row)
        payload["favorite"] = bool(row.get("favorite"))
        payload["has_thumb"] = library.has_thumb(row)
        return payload

    # ------------------------------------------------------------------ health

    @app.get("/api/health")
    def health() -> dict:
        return {
            "status": "ok",
            "version": __version__,
            "media": store.count_media(),
            "playlists": len(store.list_playlists()),
            "ffmpeg": bool(settings.ffmpeg),
            "ytdlp": _package_version("yt-dlp"),
            "auth_required": settings.auth_required,
            "private_urls": settings.allow_private_urls,
            "library": str(settings.library),
        }

    # ------------------------------------------------------------------- auth

    @app.get("/api/session")
    def session(request: Request) -> dict:
        return {
            "auth_required": settings.auth_required,
            "authenticated": authenticated(settings, request),
        }

    @app.post("/api/login")
    def login(payload: LoginIn, response: Response) -> dict:
        if not settings.token:
            return {"ok": True}
        if not hmac.compare_digest(payload.token.strip(), settings.token):
            raise HTTPException(status_code=401, detail="wrong access token")
        response.set_cookie(
            SESSION_COOKIE,
            session_value(settings.token),
            max_age=SESSION_AGE,
            httponly=True,
            samesite="lax",
            secure=settings.secure_cookies,
            path="/",
        )
        return {"ok": True}

    @app.post("/api/logout")
    def logout(response: Response) -> dict:
        response.delete_cookie(SESSION_COOKIE, path="/")
        return {"ok": True}

    # ------------------------------------------------------------------ media

    @app.get("/api/media")
    def list_media(
        kind: Literal["audio", "video"] | None = None,
        q: str | None = None,
        sort: Literal["recent", "title", "duration", "plays"] = "recent",
        favorite: bool | None = None,
        limit: int = 1000,
        _: None = Depends(require_auth),
    ) -> dict:
        rows = store.list_media(
            kind=kind,
            query=(q or "").strip()[:100] or None,
            favorite=favorite,
            sort=sort,
            limit=max(1, min(limit, 5000)),
        )
        return {"items": [media_out(row) for row in rows]}

    @app.get("/api/media/{media_id}")
    def get_media(media_id: str, _: None = Depends(require_auth)) -> dict:
        row = store.get_media(media_id)
        if row is None:
            raise HTTPException(404, "media not found")
        return media_out(row)

    @app.patch("/api/media/{media_id}")
    def patch_media(media_id: str, payload: MediaPatch, _: None = Depends(require_auth)) -> dict:
        row = store.get_media(media_id)
        if row is None:
            raise HTTPException(404, "media not found")
        changes = payload.model_dump(exclude_unset=True)
        for key in ("title", "artist", "album"):
            if key in changes and changes[key] is not None:
                changes[key] = changes[key].strip() or None
        if changes.get("title") is None and "title" in changes:
            raise HTTPException(400, "title cannot be empty")
        updated = store.update_media(media_id, changes)
        return media_out(updated or row)

    @app.delete("/api/media/{media_id}", status_code=204)
    def delete_media(media_id: str, _: None = Depends(require_auth)) -> Response:
        if not library.delete(media_id):
            raise HTTPException(404, "media not found")
        return Response(status_code=204)

    @app.post("/api/media/{media_id}/played", status_code=204)
    def played(media_id: str, _: None = Depends(require_auth)) -> Response:
        if store.get_media(media_id) is None:
            raise HTTPException(404, "media not found")
        store.touch_played(media_id)
        return Response(status_code=204)

    @app.get("/api/media/{media_id}/stream")
    def stream(media_id: str, request: Request, _: None = Depends(require_auth)):
        row = store.get_media(media_id)
        if row is None:
            raise HTTPException(404, "media not found")
        try:
            path = library.resolve(row["path"])
        except ValueError as exc:
            raise HTTPException(400, "invalid media path") from exc
        if not path.is_file():
            raise HTTPException(410, "the file is missing from the library")
        return file_response(request, path, row["mime"])

    @app.get("/api/media/{media_id}/file")
    def download_file(media_id: str, request: Request, _: None = Depends(require_auth)):
        row = store.get_media(media_id)
        if row is None:
            raise HTTPException(404, "media not found")
        try:
            path = library.resolve(row["path"])
        except ValueError as exc:
            raise HTTPException(400, "invalid media path") from exc
        if not path.is_file():
            raise HTTPException(410, "the file is missing from the library")
        name = f"{row['title']}.{row['ext']}"
        return file_response(request, path, row["mime"], attachment=True, filename=name)

    @app.get("/api/media/{media_id}/thumb")
    def thumbnail(media_id: str, _: None = Depends(require_auth)):
        row = store.get_media(media_id)
        if row is None:
            raise HTTPException(404, "media not found")
        try:
            path = library.thumb_path(row)
        except ValueError:
            path = None
        if path is None or not path.is_file():
            raise HTTPException(404, "no thumbnail")
        return FileResponse(
            path,
            headers={"Cache-Control": "private, max-age=86400"},
        )

    @app.post("/api/library/scan")
    def scan(_: None = Depends(require_auth)) -> dict:
        return library.scan()

    # -------------------------------------------------------------- playlists

    @app.get("/api/playlists")
    def list_playlists(_: None = Depends(require_auth)) -> dict:
        return {"items": store.list_playlists()}

    @app.post("/api/playlists", status_code=201)
    def create_playlist(payload: PlaylistIn, _: None = Depends(require_auth)) -> dict:
        name = payload.name.strip()
        if not name:
            raise HTTPException(400, "playlist name cannot be empty")
        return store.create_playlist(name)

    @app.get("/api/playlists/{playlist_id}")
    def get_playlist(playlist_id: str, _: None = Depends(require_auth)) -> dict:
        playlist = store.get_playlist(playlist_id)
        if playlist is None:
            raise HTTPException(404, "playlist not found")
        playlist["items"] = [media_out(item) for item in playlist["items"]]
        return playlist

    @app.patch("/api/playlists/{playlist_id}")
    def rename_playlist(
        playlist_id: str, payload: PlaylistIn, _: None = Depends(require_auth)
    ) -> dict:
        name = payload.name.strip()
        if not name:
            raise HTTPException(400, "playlist name cannot be empty")
        playlist = store.rename_playlist(playlist_id, name)
        if playlist is None:
            raise HTTPException(404, "playlist not found")
        return playlist

    @app.delete("/api/playlists/{playlist_id}", status_code=204)
    def delete_playlist(playlist_id: str, _: None = Depends(require_auth)) -> Response:
        if not store.delete_playlist(playlist_id):
            raise HTTPException(404, "playlist not found")
        return Response(status_code=204)

    @app.post("/api/playlists/{playlist_id}/items")
    def add_item(
        playlist_id: str, payload: PlaylistItemIn, _: None = Depends(require_auth)
    ) -> dict:
        added = store.add_playlist_item(playlist_id, payload.media_id)
        if added is None:
            raise HTTPException(404, "playlist or media not found")
        return {"added": added}

    @app.delete("/api/playlists/{playlist_id}/items/{media_id}")
    def remove_item(playlist_id: str, media_id: str, _: None = Depends(require_auth)) -> dict:
        return {"removed": store.remove_playlist_item(playlist_id, media_id)}

    @app.put("/api/playlists/{playlist_id}/order")
    def reorder(
        playlist_id: str, payload: PlaylistOrderIn, _: None = Depends(require_auth)
    ) -> dict:
        result = store.reorder_playlist(playlist_id, payload.media_ids)
        if result is None:
            raise HTTPException(404, "playlist not found")
        if result is False:
            raise HTTPException(400, "media_ids must list every track exactly once")
        return store.get_playlist(playlist_id)  # type: ignore[return-value]

    @app.get("/api/playlists/{playlist_id}/m3u")
    def export_m3u(playlist_id: str, _: None = Depends(require_auth)):
        playlist = store.get_playlist(playlist_id)
        if playlist is None:
            raise HTTPException(404, "playlist not found")
        lines = ["#EXTM3U"]
        for item in playlist["items"]:
            label = " - ".join(part for part in (item.get("artist"), item["title"]) if part)
            lines.append(f"#EXTINF:{int(item.get('duration') or 0)},{label}")
            try:
                lines.append(str(library.resolve(item["path"])))
            except ValueError:
                lines.append(item["path"])
        body = "\n".join(lines) + "\n"
        filename = f"{playlist['name']}.m3u"
        return Response(
            body,
            media_type="audio/x-mpegurl",
            headers={"Content-Disposition": attachment_header(filename)},
        )

    # -------------------------------------------------------------- downloads

    @app.post("/api/downloads", status_code=201)
    def enqueue(payload: DownloadIn, _: None = Depends(require_auth)) -> dict:
        try:
            return manager.enqueue(payload.url, payload.kind, payload.quality or "")
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/downloads")
    def list_downloads(limit: int = 50, _: None = Depends(require_auth)) -> dict:
        return {"items": store.list_jobs(limit=max(1, min(limit, 200)))}

    @app.post("/api/downloads/{job_id}/cancel")
    def cancel(job_id: str, _: None = Depends(require_auth)) -> dict:
        if not manager.cancel(job_id):
            raise HTTPException(409, "only queued or running downloads can be cancelled")
        return {"canceled": True}

    @app.post("/api/downloads/{job_id}/retry")
    def retry(job_id: str, _: None = Depends(require_auth)) -> dict:
        if not manager.retry(job_id):
            raise HTTPException(409, "only failed or cancelled downloads can be retried")
        return {"queued": True}

    @app.delete("/api/downloads/{job_id}", status_code=204)
    def delete_job(job_id: str, _: None = Depends(require_auth)) -> Response:
        if not store.delete_job(job_id):
            raise HTTPException(409, "a running download cannot be deleted")
        return Response(status_code=204)

    # -------------------------------------------------------------------- UI

    frontend = settings.frontend
    if frontend and (frontend / "index.html").is_file():
        app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(frontend / "index.html")

        def _root_file(name: str) -> FileResponse:
            path = frontend / name
            if not path.is_file():
                raise HTTPException(404, "not found")
            return FileResponse(path)

        @app.get("/manifest.webmanifest", include_in_schema=False)
        def manifest() -> FileResponse:
            return _root_file("manifest.webmanifest")

        @app.get("/icon.svg", include_in_schema=False)
        def icon() -> FileResponse:
            return _root_file("icon.svg")
    else:

        @app.get("/")
        def no_ui() -> JSONResponse:
            return JSONResponse(
                {
                    "app": "crate",
                    "version": __version__,
                    "hint": "frontend not built; run `npm install && npm run build` in frontend/",
                    "docs": "/docs",
                }
            )

    return app
