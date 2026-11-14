from __future__ import annotations

from fastapi.testclient import TestClient
from helpers import write_media

from crate.api import create_app


def media_by_title(client: TestClient, title: str) -> dict:
    items = client.get("/api/media").json()["items"]
    return next(item for item in items if item["title"] == title)


# ------------------------------------------------------------------ health/auth


def test_health_lists_counts_and_capabilities(client: TestClient) -> None:
    body = client.get("/api/health").json()

    assert body["status"] == "ok"
    assert body["media"] == {"audio": 2, "video": 1, "total": 3}
    assert body["playlists"] == 0
    assert body["auth_required"] is False
    assert body["ffmpeg"] is False


def test_root_without_a_built_frontend_explains_itself(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "frontend not built" in response.json()["hint"]


def test_api_requires_auth_when_token_is_set(auth_client: TestClient) -> None:
    response = auth_client.get("/api/media")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_health_stays_public(auth_client: TestClient) -> None:
    assert auth_client.get("/api/health").status_code == 200


def test_bearer_token_is_accepted(auth_client: TestClient) -> None:
    response = auth_client.get("/api/media", headers={"Authorization": "Bearer secret-token"})

    assert response.status_code == 200
    assert len(response.json()["items"]) == 3


def test_wrong_token_is_rejected(auth_client: TestClient) -> None:
    response = auth_client.get("/api/media", headers={"Authorization": "Bearer nope"})

    assert response.status_code == 401


def test_login_sets_a_session_cookie(auth_client: TestClient) -> None:
    session = auth_client.get("/api/session").json()
    assert session == {"auth_required": True, "authenticated": False}

    wrong = auth_client.post("/api/login", json={"token": "nope"})
    assert wrong.status_code == 401

    ok = auth_client.post("/api/login", json={"token": "secret-token"})
    assert ok.status_code == 200

    session = auth_client.get("/api/session").json()
    assert session["authenticated"] is True
    assert auth_client.get("/api/media").status_code == 200

    auth_client.post("/api/logout")
    assert auth_client.get("/api/session").json()["authenticated"] is False


# ----------------------------------------------------------------------- media


def test_list_media_filters_and_sorts(client: TestClient) -> None:
    everything = client.get("/api/media").json()["items"]
    assert len(everything) == 3

    audio = client.get("/api/media", params={"kind": "audio"}).json()["items"]
    assert [item["kind"] for item in audio] == ["audio", "audio"]

    search = client.get("/api/media", params={"q": "night"}).json()["items"]
    assert [item["title"] for item in search] == ["Night Drive"]

    by_title = client.get("/api/media", params={"sort": "title"}).json()["items"]
    assert [item["title"] for item in by_title] == ["First Light", "Night Drive", "Soft Focus"]

    longest = client.get("/api/media", params={"sort": "duration"}).json()["items"]
    assert longest[0]["title"] == "Night Drive"


def test_media_payload_exposes_ui_fields(client: TestClient) -> None:
    item = media_by_title(client, "Night Drive")

    assert item["kind"] == "audio"
    assert item["artist"] == "Kite"
    assert item["duration"] == 215
    assert item["favorite"] is False
    assert item["has_thumb"] is False
    assert item["mime"] == "audio/mpeg"


def test_get_media_and_missing_id(client: TestClient) -> None:
    item = media_by_title(client, "First Light")

    assert client.get(f"/api/media/{item['id']}").json()["title"] == "First Light"
    assert client.get("/api/media/does-not-exist").status_code == 404


def test_patch_media_metadata_and_favorite(client: TestClient) -> None:
    item = media_by_title(client, "Soft Focus")

    renamed = client.patch(
        f"/api/media/{item['id']}",
        json={"title": "Soft Focus (edit)", "album": "Demos", "favorite": True},
    )

    assert renamed.status_code == 200
    body = renamed.json()
    assert body["title"] == "Soft Focus (edit)"
    assert body["album"] == "Demos"
    assert body["favorite"] is True
    favorites = client.get("/api/media", params={"favorite": True}).json()["items"]
    assert [row["title"] for row in favorites] == ["Soft Focus (edit)"]


def test_patch_rejects_empty_title_and_unknown_media(client: TestClient) -> None:
    item = media_by_title(client, "Soft Focus")

    assert client.patch(f"/api/media/{item['id']}", json={"title": "  "}).status_code == 400
    assert client.patch("/api/media/nope", json={"title": "x"}).status_code == 404


def test_played_increments_the_counter(client: TestClient) -> None:
    item = media_by_title(client, "Night Drive")

    assert client.post(f"/api/media/{item['id']}/played").status_code == 204
    assert client.post("/api/media/nope/played").status_code == 404

    updated = client.get(f"/api/media/{item['id']}").json()
    assert updated["play_count"] == 1
    assert updated["played_at"]


def test_delete_media_removes_the_file(client: TestClient, populated) -> None:
    item = media_by_title(client, "Night Drive")
    path = populated.library / item["path"]

    assert client.delete(f"/api/media/{item['id']}").status_code == 204

    assert not path.exists()
    assert client.get(f"/api/media/{item['id']}").status_code == 404
    assert client.delete(f"/api/media/{item['id']}").status_code == 404


def test_thumbnail_endpoint(client: TestClient) -> None:
    item = media_by_title(client, "First Light")
    assert client.get(f"/api/media/{item['id']}/thumb").status_code == 404

    write_media(client.app.state.settings, "video", "first-light.mp4", b"0123456789")
    thumb = client.app.state.settings.library / "thumbnails" / f"{item['id']}.jpg"
    thumb.parent.mkdir(parents=True, exist_ok=True)
    thumb.write_bytes(b"jpeg")
    client.app.state.store.update_media(item["id"], {"thumbnail": f"thumbnails/{item['id']}.jpg"})

    response = client.get(f"/api/media/{item['id']}/thumb")
    assert response.status_code == 200
    assert response.content == b"jpeg"


# ------------------------------------------------------------------- playlists


def test_playlist_lifecycle(client: TestClient) -> None:
    created = client.post("/api/playlists", json={"name": "Road trip"})
    assert created.status_code == 201
    playlist_id = created.json()["id"]

    assert client.get("/api/playlists").json()["items"][0]["name"] == "Road trip"
    assert client.post("/api/playlists", json={"name": "   "}).status_code == 400

    renamed = client.patch(f"/api/playlists/{playlist_id}", json={"name": "Night run"})
    assert renamed.status_code == 200 and renamed.json()["name"] == "Night run"

    assert client.delete(f"/api/playlists/{playlist_id}").status_code == 204
    assert client.get(f"/api/playlists/{playlist_id}").status_code == 404


def test_playlist_items_and_order(client: TestClient) -> None:
    playlist_id = client.post("/api/playlists", json={"name": "Mix"}).json()["id"]
    night = media_by_title(client, "Night Drive")
    soft = media_by_title(client, "Soft Focus")

    assert client.post(
        f"/api/playlists/{playlist_id}/items", json={"media_id": night["id"]}
    ).json() == {"added": True}
    assert client.post(
        f"/api/playlists/{playlist_id}/items", json={"media_id": soft["id"]}
    ).json() == {"added": True}
    duplicate = client.post(f"/api/playlists/{playlist_id}/items", json={"media_id": soft["id"]})
    assert duplicate.json() == {"added": False}
    assert (
        client.post("/api/playlists/nope/items", json={"media_id": night["id"]}).status_code == 404
    )

    ordered = client.put(
        f"/api/playlists/{playlist_id}/order",
        json={"media_ids": [soft["id"], night["id"]]},
    )
    assert ordered.status_code == 200
    assert [item["title"] for item in ordered.json()["items"]] == ["Soft Focus", "Night Drive"]

    assert (
        client.put(
            f"/api/playlists/{playlist_id}/order", json={"media_ids": [soft["id"]]}
        ).status_code
        == 400
    )

    assert client.delete(f"/api/playlists/{playlist_id}/items/{soft['id']}").json() == {
        "removed": True
    }
    detail = client.get(f"/api/playlists/{playlist_id}").json()
    assert [item["title"] for item in detail["items"]] == ["Night Drive"]


def test_playlist_m3u_export(client: TestClient) -> None:
    playlist_id = client.post("/api/playlists", json={"name": "Mix"}).json()["id"]
    night = media_by_title(client, "Night Drive")
    client.post(f"/api/playlists/{playlist_id}/items", json={"media_id": night["id"]})

    response = client.get(f"/api/playlists/{playlist_id}/m3u")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/x-mpegurl")
    body = response.text
    assert body.startswith("#EXTM3U\n")
    assert "#EXTINF:215,Kite - Night Drive" in body
    assert str((client.app.state.settings.library / "audio" / "night-drive.mp3").resolve()) in body
    assert client.get("/api/playlists/nope/m3u").status_code == 404


# ------------------------------------------------------------------- downloads


def test_download_validation(client: TestClient) -> None:
    bad_kind = client.post(
        "/api/downloads", json={"url": "http://127.0.0.1:9/x", "kind": "podcast"}
    )
    assert bad_kind.status_code == 422

    bad_quality = client.post(
        "/api/downloads",
        json={"url": "http://127.0.0.1:9/x", "kind": "audio", "quality": "1080"},
    )
    assert bad_quality.status_code == 422

    private = client.post("/api/downloads", json={"url": "http://127.0.0.1:9/x", "kind": "audio"})
    assert private.status_code == 400
    assert "private or local" in private.json()["detail"]

    assert client.post("/api/downloads", json={"kind": "audio"}).status_code == 422


def test_download_defaults_are_applied(client: TestClient) -> None:
    settings = client.app.state.settings
    from dataclasses import replace

    open_settings = replace(settings, allow_private_urls=True)
    app = create_app(open_settings, start_worker=False)
    with TestClient(app) as open_client:
        created = open_client.post(
            "/api/downloads", json={"url": "http://127.0.0.1:9/x", "kind": "audio"}
        )
        assert created.status_code == 201
        assert created.json()["quality"] == "192"
        assert created.json()["status"] == "queued"

        video = open_client.post(
            "/api/downloads", json={"url": "http://127.0.0.1:9/y", "kind": "video"}
        )
        assert video.json()["quality"] == "1080"

        jobs = open_client.get("/api/downloads").json()["items"]
        assert {job["url"] for job in jobs} == {
            "http://127.0.0.1:9/x",
            "http://127.0.0.1:9/y",
        }


def test_download_queue_actions_use_conflicts(client: TestClient) -> None:
    assert client.post("/api/downloads/nope/cancel").status_code == 409
    assert client.post("/api/downloads/nope/retry").status_code == 409
    assert client.delete("/api/downloads/nope").status_code == 409
    assert client.get("/api/downloads").json() == {"items": []}
