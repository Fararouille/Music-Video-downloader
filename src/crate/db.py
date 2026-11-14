from __future__ import annotations

import secrets
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS media (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('audio', 'video')),
    path TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    artist TEXT,
    album TEXT,
    duration REAL,
    size INTEGER NOT NULL DEFAULT 0,
    ext TEXT NOT NULL,
    mime TEXT NOT NULL,
    width INTEGER,
    height INTEGER,
    source_url TEXT,
    source_id TEXT,
    thumbnail TEXT,
    added_at TEXT NOT NULL,
    played_at TEXT,
    play_count INTEGER NOT NULL DEFAULT 0,
    favorite INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS media_kind_idx ON media(kind);
CREATE INDEX IF NOT EXISTS media_added_idx ON media(added_at DESC);
CREATE INDEX IF NOT EXISTS media_source_idx ON media(source_id, kind);

CREATE TABLE IF NOT EXISTS playlists (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS playlist_items (
    playlist_id TEXT NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    media_id TEXT NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    added_at TEXT NOT NULL,
    PRIMARY KEY (playlist_id, media_id)
);
CREATE INDEX IF NOT EXISTS playlist_items_order_idx ON playlist_items(playlist_id, position);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('audio', 'video')),
    quality TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'done', 'error', 'canceled')),
    progress REAL NOT NULL DEFAULT 0,
    speed TEXT,
    eta INTEGER,
    title TEXT,
    error TEXT,
    media_id TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS jobs_status_idx ON jobs(status, created_at);
"""

MEDIA_FIELDS = (
    "id",
    "kind",
    "path",
    "title",
    "artist",
    "album",
    "duration",
    "size",
    "ext",
    "mime",
    "width",
    "height",
    "source_url",
    "source_id",
    "thumbnail",
    "added_at",
    "played_at",
    "play_count",
    "favorite",
)

JOB_FIELDS = (
    "status",
    "progress",
    "speed",
    "eta",
    "title",
    "error",
    "media_id",
    "started_at",
    "finished_at",
)

SORTS = {
    "recent": "added_at DESC, title COLLATE NOCASE",
    "title": "title COLLATE NOCASE ASC",
    "duration": "COALESCE(duration, 0) DESC, title COLLATE NOCASE",
    "plays": "play_count DESC, added_at DESC",
}


def utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 15000")
        return connection

    @contextmanager
    def session(self):
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _init(self) -> None:
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(SCHEMA)
            connection.commit()

    # ------------------------------------------------------------------ media

    def get_media(self, media_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM media WHERE id = ?", (media_id,)).fetchone()
        return dict(row) if row else None

    def find_media_by_path(self, path: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM media WHERE path = ?", (path,)).fetchone()
        return dict(row) if row else None

    def find_media_by_source(self, source_id: str, kind: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM media WHERE source_id = ? AND kind = ? "
                "ORDER BY added_at DESC LIMIT 1",
                (source_id, kind),
            ).fetchone()
        return dict(row) if row else None

    def list_media(
        self,
        *,
        kind: str | None = None,
        query: str | None = None,
        favorite: bool | None = None,
        sort: str = "recent",
        limit: int = 1000,
    ) -> list[dict]:
        clauses: list[str] = []
        params: list[object] = []
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if favorite is not None:
            clauses.append("favorite = ?")
            params.append(1 if favorite else 0)
        if query:
            like = f"%{query.strip()}%"
            clauses.append(
                "(title LIKE ? OR COALESCE(artist, '') LIKE ? OR COALESCE(album, '') LIKE ?)"
            )
            params.extend([like, like, like])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        order = SORTS.get(sort, SORTS["recent"])
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM media {where} ORDER BY {order} LIMIT ?",  # noqa: S608
                (*params, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_media(self, media: dict) -> None:
        values = {field: media.get(field) for field in MEDIA_FIELDS}
        values["favorite"] = 1 if media.get("favorite") else 0
        values["play_count"] = media.get("play_count") or 0
        columns = ", ".join(MEDIA_FIELDS)
        placeholders = ", ".join(f":{field}" for field in MEDIA_FIELDS)
        updates = ", ".join(
            f"{field} = excluded.{field}" for field in MEDIA_FIELDS if field != "id"
        )
        with self.connect() as connection:
            connection.execute(
                f"INSERT INTO media ({columns}) VALUES ({placeholders}) "  # noqa: S608
                f"ON CONFLICT(id) DO UPDATE SET {updates}",
                values,
            )
            connection.commit()

    def update_media(self, media_id: str, fields: dict) -> dict | None:
        allowed = {"title", "artist", "album", "favorite", "thumbnail"}
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return self.get_media(media_id)
        if "favorite" in updates:
            updates["favorite"] = 1 if updates["favorite"] else 0
        assignments = ", ".join(f"{key} = ?" for key in updates)
        with self.connect() as connection:
            connection.execute(
                f"UPDATE media SET {assignments} WHERE id = ?",  # noqa: S608
                (*updates.values(), media_id),
            )
            connection.commit()
        return self.get_media(media_id)

    def delete_media(self, media_id: str) -> dict | None:
        row = self.get_media(media_id)
        if row is None:
            return None
        with self.connect() as connection:
            connection.execute("DELETE FROM media WHERE id = ?", (media_id,))
            connection.commit()
        return row

    def touch_played(self, media_id: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE media SET play_count = play_count + 1, played_at = ? WHERE id = ?",
                (utcnow(), media_id),
            )
            connection.commit()

    def count_media(self) -> dict:
        result = {"audio": 0, "video": 0, "total": 0}
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT kind, COUNT(*) AS n FROM media GROUP BY kind"
            ).fetchall()
        for row in rows:
            result[row["kind"]] = row["n"]
            result["total"] += row["n"]
        return result

    # -------------------------------------------------------------- playlists

    def list_playlists(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT p.id, p.name, p.created_at, p.updated_at,
                       COUNT(i.media_id) AS item_count,
                       COALESCE(SUM(m.duration), 0) AS duration
                FROM playlists p
                LEFT JOIN playlist_items i ON i.playlist_id = p.id
                LEFT JOIN media m ON m.id = i.media_id
                GROUP BY p.id
                ORDER BY p.updated_at DESC, p.name COLLATE NOCASE
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_playlist(self, playlist_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT p.id, p.name, p.created_at, p.updated_at,
                       COUNT(i.media_id) AS item_count,
                       COALESCE(SUM(m.duration), 0) AS duration
                FROM playlists p
                LEFT JOIN playlist_items i ON i.playlist_id = p.id
                LEFT JOIN media m ON m.id = i.media_id
                WHERE p.id = ?
                GROUP BY p.id
                """,
                (playlist_id,),
            ).fetchone()
            if row is None:
                return None
            items = connection.execute(
                """
                SELECT m.*, i.position AS playlist_position
                FROM playlist_items i
                JOIN media m ON m.id = i.media_id
                WHERE i.playlist_id = ?
                ORDER BY i.position
                """,
                (playlist_id,),
            ).fetchall()
        playlist = dict(row)
        playlist["items"] = [dict(item) for item in items]
        return playlist

    def create_playlist(self, name: str) -> dict:
        playlist_id = secrets.token_hex(8)
        now = utcnow()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO playlists (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (playlist_id, name, now, now),
            )
            connection.commit()
        return self.get_playlist(playlist_id)  # type: ignore[return-value]

    def rename_playlist(self, playlist_id: str, name: str) -> dict | None:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE playlists SET name = ?, updated_at = ? WHERE id = ?",
                (name, utcnow(), playlist_id),
            )
            connection.commit()
        return self.get_playlist(playlist_id) if cursor.rowcount else None

    def delete_playlist(self, playlist_id: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))
            connection.commit()
        return bool(cursor.rowcount)

    def add_playlist_item(self, playlist_id: str, media_id: str) -> bool | None:
        """True when added, False when already present, None when either id is unknown."""
        with self.session() as connection:
            if (
                connection.execute(
                    "SELECT 1 FROM playlists WHERE id = ?", (playlist_id,)
                ).fetchone()
                is None
            ):
                return None
            if (
                connection.execute("SELECT 1 FROM media WHERE id = ?", (media_id,)).fetchone()
                is None
            ):
                return None
            position = connection.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 AS next "
                "FROM playlist_items WHERE playlist_id = ?",
                (playlist_id,),
            ).fetchone()["next"]
            cursor = connection.execute(
                "INSERT OR IGNORE INTO playlist_items "
                "(playlist_id, media_id, position, added_at) VALUES (?, ?, ?, ?)",
                (playlist_id, media_id, position, utcnow()),
            )
            if cursor.rowcount:
                connection.execute(
                    "UPDATE playlists SET updated_at = ? WHERE id = ?",
                    (utcnow(), playlist_id),
                )
            return bool(cursor.rowcount)

    def remove_playlist_item(self, playlist_id: str, media_id: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM playlist_items WHERE playlist_id = ? AND media_id = ?",
                (playlist_id, media_id),
            )
            if cursor.rowcount:
                connection.execute(
                    "UPDATE playlists SET updated_at = ? WHERE id = ?",
                    (utcnow(), playlist_id),
                )
            connection.commit()
        return bool(cursor.rowcount)

    def reorder_playlist(self, playlist_id: str, media_ids: list[str]) -> bool | None:
        with self.session() as connection:
            current_rows = connection.execute(
                "SELECT media_id FROM playlist_items WHERE playlist_id = ?", (playlist_id,)
            ).fetchall()
            if (
                connection.execute(
                    "SELECT 1 FROM playlists WHERE id = ?", (playlist_id,)
                ).fetchone()
                is None
            ):
                return None
            current = [row["media_id"] for row in current_rows]
            if len(media_ids) != len(current) or set(media_ids) != set(current):
                return False
            for position, media_id in enumerate(media_ids):
                connection.execute(
                    "UPDATE playlist_items SET position = ? WHERE playlist_id = ? AND media_id = ?",
                    (position, playlist_id, media_id),
                )
            connection.execute(
                "UPDATE playlists SET updated_at = ? WHERE id = ?",
                (utcnow(), playlist_id),
            )
            return True

    # ------------------------------------------------------------------- jobs

    def create_job(self, url: str, kind: str, quality: str) -> dict:
        job_id = secrets.token_hex(8)
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO jobs (id, url, kind, quality, status, created_at) "
                "VALUES (?, ?, ?, ?, 'queued', ?)",
                (job_id, url, kind, quality, utcnow()),
            )
            connection.commit()
        return self.get_job(job_id)  # type: ignore[return-value]

    def get_job(self, job_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    def list_jobs(self, limit: int = 50) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def next_queued_job(self) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE status = 'queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def update_job(self, job_id: str, **fields: object) -> None:
        updates = {key: value for key, value in fields.items() if key in JOB_FIELDS}
        if not updates:
            return
        assignments = ", ".join(f"{key} = ?" for key in updates)
        with self.connect() as connection:
            connection.execute(
                f"UPDATE jobs SET {assignments} WHERE id = ?",  # noqa: S608
                (*updates.values(), job_id),
            )
            connection.commit()

    def update_job_progress(
        self,
        job_id: str,
        progress: float,
        *,
        speed: str | None = None,
        eta: int | None = None,
        title: str | None = None,
    ) -> None:
        assignments = ["progress = ?", "speed = ?", "eta = ?"]
        params: list[object] = [max(0.0, min(1.0, progress)), speed, eta]
        if title:
            assignments.append("title = ?")
            params.append(title)
        params.append(job_id)
        with self.connect() as connection:
            connection.execute(
                f"UPDATE jobs SET {', '.join(assignments)} WHERE id = ?",
                params,
            )
            connection.commit()

    def cancel_job(self, job_id: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE jobs SET status = 'canceled', finished_at = ? "
                "WHERE id = ? AND status = 'queued'",
                (utcnow(), job_id),
            )
            connection.commit()
        return bool(cursor.rowcount)

    def retry_job(self, job_id: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET status = 'queued', progress = 0, speed = NULL, eta = NULL,
                    error = NULL, media_id = NULL, started_at = NULL, finished_at = NULL
                WHERE id = ? AND status IN ('error', 'canceled')
                """,
                (job_id,),
            )
            connection.commit()
        return bool(cursor.rowcount)

    def delete_job(self, job_id: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM jobs WHERE id = ? AND status != 'running'", (job_id,)
            )
            connection.commit()
        return bool(cursor.rowcount)

    def fail_interrupted_jobs(self) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE jobs SET status = 'error', error = ?, finished_at = ? "
                "WHERE status = 'running'",
                ("interrupted by a server restart", utcnow()),
            )
            connection.commit()
