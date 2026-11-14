from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import Response, StreamingResponse

CHUNK_SIZE = 256 * 1024


def attachment_header(name: str) -> str:
    """Build a ``Content-Disposition`` value browsers and Android both understand.

    RFC 6266 wants a quoted ASCII ``filename`` plus an encoded ``filename*``. Browsers prefer
    the latter, while simpler clients (Android's ``DownloadManager``, some curl builds) only
    look at the plain one and would otherwise save every file as ``file.<ext>``.
    """
    fallback = "".join(
        ch if ch.isascii() and ch not in '"\\' and ch.isprintable() else "_" for ch in name
    ).strip()
    encoded = quote(name)
    if not any(ch.isalnum() for ch in Path(fallback).stem):
        fallback = "download" + Path(name).suffix
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{encoded}"


class RangeNotSatisfiable(Exception):
    pass


def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """Parse a single ``bytes=`` range against a known file size.

    Returns ``None`` when the header is absent, or ``(start, end)`` inclusive.
    Raises :class:`RangeNotSatisfiable` for malformed or unsatisfiable ranges.
    """
    if header is None or not header.strip():
        return None
    value = header.strip()
    if not value.lower().startswith("bytes="):
        raise RangeNotSatisfiable
    spec = value[6:].split(",", 1)[0].strip()
    if "-" not in spec:
        raise RangeNotSatisfiable
    first, _, last = spec.partition("-")
    first, last = first.strip(), last.strip()
    try:
        if first == "":
            if last == "":
                raise ValueError
            suffix = int(last)
            if suffix <= 0 or size <= 0:
                raise ValueError
            start = max(0, size - suffix)
            end = size - 1
        else:
            start = int(first)
            end = int(last) if last else size - 1
            if size <= 0 or start < 0 or start >= size or start > end:
                raise ValueError
            end = min(end, size - 1)
    except ValueError as exc:
        raise RangeNotSatisfiable from exc
    return start, end


def iter_file(path: Path, start: int, length: int, chunk_size: int = CHUNK_SIZE) -> Iterator[bytes]:
    with path.open("rb") as handle:
        handle.seek(start)
        remaining = length
        while remaining > 0:
            chunk = handle.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def file_response(
    request: Request,
    path: Path,
    media_type: str,
    *,
    attachment: bool = False,
    filename: str | None = None,
    cache_control: str = "private, max-age=0, must-revalidate",
) -> Response:
    size = path.stat().st_size
    headers = {"Accept-Ranges": "bytes", "Cache-Control": cache_control}
    if attachment:
        headers["Content-Disposition"] = attachment_header(filename or path.name)

    try:
        parsed = parse_range(request.headers.get("range"), size)
    except RangeNotSatisfiable:
        return Response(
            status_code=416,
            headers={"Content-Range": f"bytes */{size}", "Accept-Ranges": "bytes"},
        )

    if parsed is None:
        headers["Content-Length"] = str(size)
        return StreamingResponse(iter_file(path, 0, size), media_type=media_type, headers=headers)

    start, end = parsed
    length = end - start + 1
    headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    headers["Content-Length"] = str(length)
    return StreamingResponse(
        iter_file(path, start, length),
        status_code=206,
        media_type=media_type,
        headers=headers,
    )
