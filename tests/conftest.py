from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from helpers import write_media

from crate.api import create_app
from crate.config import Settings
from crate.db import Store
from crate.library import Library


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        root=tmp_path,
        library=tmp_path / "library",
        db_path=tmp_path / "data" / "crate.db",
        ffmpeg=None,
        frontend=None,
    )


@pytest.fixture
def store(settings: Settings) -> Store:
    settings.ensure_dirs()
    return Store(settings.db_path)


@pytest.fixture
def library(settings: Settings, store: Store) -> Library:
    return Library(settings, store)


@pytest.fixture
def populated(settings: Settings) -> Settings:
    write_media(
        settings,
        "audio",
        "night-drive.mp3",
        meta={"title": "Night Drive", "artist": "Kite", "duration": 215},
    )
    write_media(
        settings,
        "audio",
        "soft-focus.mp3",
        meta={"title": "Soft Focus", "artist": "Moth", "duration": 180},
    )
    write_media(
        settings,
        "video",
        "first-light.mp4",
        meta={"title": "First Light", "duration": 95, "width": 1920, "height": 1080},
    )
    return settings


@pytest.fixture
def client(populated: Settings):
    app = create_app(populated, start_worker=False)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_client(populated: Settings):
    settings = replace(populated, token="secret-token")
    app = create_app(settings, start_worker=False)
    with TestClient(app) as test_client:
        yield test_client
