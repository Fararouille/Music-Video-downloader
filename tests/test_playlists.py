from __future__ import annotations

from helpers import write_media

from crate.config import Settings
from crate.db import Store
from crate.library import Library


def seed(settings: Settings, store: Store, library: Library) -> list[str]:
    for index, title in enumerate(("Alpha", "Bravo", "Charlie")):
        write_media(
            settings,
            "audio",
            f"{index}-{title.lower()}.mp3",
            meta={"title": title, "duration": 60 + index},
        )
    library.scan()
    return [row["id"] for row in store.list_media(sort="title")]


def test_create_and_list_playlists(settings: Settings, store: Store, library: Library) -> None:
    playlist = store.create_playlist("Late night")

    assert playlist["name"] == "Late night"
    assert playlist["item_count"] == 0
    assert playlist["duration"] == 0
    listed = store.list_playlists()
    assert [row["name"] for row in listed] == ["Late night"]


def test_items_keep_insertion_order(settings: Settings, store: Store, library: Library) -> None:
    ids = seed(settings, store, library)
    playlist = store.create_playlist("Mix")

    assert store.add_playlist_item(playlist["id"], ids[2]) is True
    assert store.add_playlist_item(playlist["id"], ids[0]) is True
    assert store.add_playlist_item(playlist["id"], ids[1]) is True

    detailed = store.get_playlist(playlist["id"])
    assert [item["id"] for item in detailed["items"]] == [ids[2], ids[0], ids[1]]
    assert detailed["item_count"] == 3
    assert detailed["duration"] == 183


def test_duplicate_item_is_not_added(settings: Settings, store: Store, library: Library) -> None:
    ids = seed(settings, store, library)
    playlist = store.create_playlist("Mix")
    store.add_playlist_item(playlist["id"], ids[0])

    assert store.add_playlist_item(playlist["id"], ids[0]) is False
    assert store.get_playlist(playlist["id"])["item_count"] == 1


def test_add_item_with_unknown_ids(settings: Settings, store: Store, library: Library) -> None:
    ids = seed(settings, store, library)
    playlist = store.create_playlist("Mix")

    assert store.add_playlist_item("missing", ids[0]) is None
    assert store.add_playlist_item(playlist["id"], "missing") is None


def test_remove_item(settings: Settings, store: Store, library: Library) -> None:
    ids = seed(settings, store, library)
    playlist = store.create_playlist("Mix")
    store.add_playlist_item(playlist["id"], ids[0])
    store.add_playlist_item(playlist["id"], ids[1])

    assert store.remove_playlist_item(playlist["id"], ids[0]) is True
    assert [item["id"] for item in store.get_playlist(playlist["id"])["items"]] == [ids[1]]


def test_reorder(settings: Settings, store: Store, library: Library) -> None:
    ids = seed(settings, store, library)
    playlist = store.create_playlist("Mix")
    for media_id in ids:
        store.add_playlist_item(playlist["id"], media_id)

    assert store.reorder_playlist(playlist["id"], list(reversed(ids))) is True
    assert [item["id"] for item in store.get_playlist(playlist["id"])["items"]] == list(
        reversed(ids)
    )


def test_reorder_rejects_incomplete_permutations(
    settings: Settings, store: Store, library: Library
) -> None:
    ids = seed(settings, store, library)
    playlist = store.create_playlist("Mix")
    for media_id in ids:
        store.add_playlist_item(playlist["id"], media_id)

    assert store.reorder_playlist(playlist["id"], ids[:2]) is False
    assert store.reorder_playlist(playlist["id"], [*ids, ids[0]]) is False
    assert store.reorder_playlist(playlist["id"], ["nope", ids[0], ids[1]]) is False


def test_rename_and_delete(settings: Settings, store: Store, library: Library) -> None:
    playlist = store.create_playlist("Old name")

    renamed = store.rename_playlist(playlist["id"], "New name")
    assert renamed is not None and renamed["name"] == "New name"

    assert store.delete_playlist(playlist["id"]) is True
    assert store.get_playlist(playlist["id"]) is None
    assert store.delete_playlist(playlist["id"]) is False


def test_deleting_media_cascades_to_playlists(
    settings: Settings, store: Store, library: Library
) -> None:
    ids = seed(settings, store, library)
    playlist = store.create_playlist("Mix")
    store.add_playlist_item(playlist["id"], ids[0])

    library.delete(ids[0])

    assert store.get_playlist(playlist["id"])["item_count"] == 0
