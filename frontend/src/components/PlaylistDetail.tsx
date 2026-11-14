import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api, errorMessage, m3uUrl } from "../api";
import { formatDuration } from "../format";
import { Icon } from "../icons";
import { navigate } from "../router";
import type { Media, Notify, Playlist } from "../types";
import { EmptyState } from "./EmptyState";

interface Props {
  playlistId: string;
  onChanged: () => Promise<void> | void;
  onSelect: (media: Media, queue: Media[]) => void;
  notify: Notify;
}

export function PlaylistDetail({ playlistId, onChanged, onSelect, notify }: Props) {
  const [playlist, setPlaylist] = useState<Playlist | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.playlist(playlistId);
      setPlaylist(data);
      setDraft(data.name);
      setError(null);
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setLoading(false);
    }
  }, [playlistId]);

  useEffect(() => {
    void load();
  }, [load]);

  const rename = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!playlist || !draft.trim() || busy) {
      return;
    }
    setBusy(true);
    try {
      const updated = await api.renamePlaylist(playlist.id, draft.trim());
      setPlaylist(updated);
      setEditing(false);
      await onChanged();
      notify("Playlist renamed");
    } catch (failure) {
      notify(errorMessage(failure), "error");
    } finally {
      setBusy(false);
    }
  };

  const move = async (from: number, to: number) => {
    if (!playlist || to < 0 || to >= playlist.items.length || busy) {
      return;
    }
    const ids = playlist.items.map((item) => item.id);
    const [moved] = ids.splice(from, 1);
    ids.splice(to, 0, moved);
    setBusy(true);
    try {
      const updated = await api.reorderPlaylist(playlist.id, ids);
      setPlaylist(updated);
      await onChanged();
    } catch (failure) {
      notify(errorMessage(failure), "error");
    } finally {
      setBusy(false);
    }
  };

  const removeItem = async (media: Media) => {
    if (!playlist || busy) {
      return;
    }
    setBusy(true);
    try {
      await api.removePlaylistItem(playlist.id, media.id);
      await load();
      await onChanged();
      notify("Removed from playlist");
    } catch (failure) {
      notify(errorMessage(failure), "error");
    } finally {
      setBusy(false);
    }
  };

  const removePlaylist = async () => {
    if (!playlist) {
      return;
    }
    if (!window.confirm(`Delete the playlist “${playlist.name}”? The files stay in your library.`)) {
      return;
    }
    try {
      await api.deletePlaylist(playlist.id);
      await onChanged();
      notify(`Deleted “${playlist.name}”`);
      navigate("#/playlists");
    } catch (failure) {
      notify(errorMessage(failure), "error");
    }
  };

  if (loading) {
    return (
      <section className="page">
        <p className="muted">Loading playlist…</p>
      </section>
    );
  }

  if (error || !playlist) {
    return (
      <section className="page">
        <a className="back" href="#/playlists">
          <Icon name="arrowLeft" size={16} />
          Playlists
        </a>
        <EmptyState
          icon="list"
          title="Playlist not found"
          body={error ?? "This playlist may have been deleted."}
          action={{ label: "Back to playlists", onClick: () => navigate("#/playlists") }}
        />
      </section>
    );
  }

  return (
    <section className="page">
      <a className="back" href="#/playlists">
        <Icon name="arrowLeft" size={16} />
        Playlists
      </a>

      <header className="detail-head">
        <div className="detail-copy">
          {editing ? (
            <form className="rename-form" onSubmit={rename}>
              <input
                type="text"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                maxLength={80}
                aria-label="Playlist name"
                autoFocus
              />
              <button type="submit" className="btn btn-primary btn-sm" disabled={busy || !draft.trim()}>
                Save
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => {
                  setDraft(playlist.name);
                  setEditing(false);
                }}
              >
                Cancel
              </button>
            </form>
          ) : (
            <>
              <h1>{playlist.name}</h1>
              <p>
                {playlist.item_count} track{playlist.item_count === 1 ? "" : "s"} ·{" "}
                {formatDuration(playlist.duration)}
              </p>
            </>
          )}
        </div>

        <div className="detail-actions">
          {playlist.items.length > 0 && (
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => onSelect(playlist.items[0], playlist.items)}
            >
              <Icon name="play" size={15} />
              Play all
            </button>
          )}
          <a className="btn btn-ghost btn-sm" href={m3uUrl(playlist.id)}>
            <Icon name="download" size={15} />
            Export M3U
          </a>
          {!editing && (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => {
                setDraft(playlist.name);
                setEditing(true);
              }}
            >
              Rename
            </button>
          )}
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => void removePlaylist()}>
            <Icon name="trash" size={15} />
            Delete
          </button>
        </div>
      </header>

      {playlist.items.length === 0 ? (
        <EmptyState
          icon="music"
          title="This playlist is empty"
          body="Browse the library and use the + button on any track to add it here."
          action={{ label: "Browse music", onClick: () => navigate("#/music") }}
        />
      ) : (
        <ol className="tracks">
          {playlist.items.map((item, position) => (
            <li key={item.id} className="track">
              <button
                type="button"
                className="track-main"
                onClick={() => onSelect(item, playlist.items)}
              >
                <span className="track-index">{String(position + 1).padStart(2, "0")}</span>
                <span className="track-info">
                  <strong>{item.title}</strong>
                  <span>{item.artist ?? "Unknown artist"}</span>
                </span>
                <span className="track-time">{formatDuration(item.duration)}</span>
              </button>
              <div className="track-actions">
                <button
                  type="button"
                  className="icon-btn"
                  onClick={() => void move(position, position - 1)}
                  disabled={position === 0 || busy}
                  aria-label={`Move ${item.title} up`}
                >
                  <Icon name="up" size={15} />
                </button>
                <button
                  type="button"
                  className="icon-btn"
                  onClick={() => void move(position, position + 1)}
                  disabled={position === playlist.items.length - 1 || busy}
                  aria-label={`Move ${item.title} down`}
                >
                  <Icon name="down" size={15} />
                </button>
                <button
                  type="button"
                  className="icon-btn icon-btn-danger"
                  onClick={() => void removeItem(item)}
                  disabled={busy}
                  aria-label={`Remove ${item.title} from playlist`}
                >
                  <Icon name="close" size={15} />
                </button>
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
