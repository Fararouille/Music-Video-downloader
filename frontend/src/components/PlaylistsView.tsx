import { useState } from "react";
import type { FormEvent } from "react";
import { api, errorMessage } from "../api";
import { formatDuration } from "../format";
import { Icon } from "../icons";
import { navigate } from "../router";
import type { Notify, PlaylistSummary } from "../types";
import { EmptyState } from "./EmptyState";

interface Props {
  playlists: PlaylistSummary[];
  onChanged: () => Promise<void> | void;
  notify: Notify;
}

export function PlaylistsView({ playlists, onChanged, notify }: Props) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  const create = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed || busy) {
      return;
    }
    setBusy(true);
    try {
      const playlist = await api.createPlaylist(trimmed);
      setName("");
      await onChanged();
      notify(`Created “${playlist.name}”`);
      navigate(`#/playlists/${playlist.id}`);
    } catch (error) {
      notify(errorMessage(error), "error");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (playlist: PlaylistSummary) => {
    if (!window.confirm(`Delete the playlist “${playlist.name}”? The files stay in your library.`)) {
      return;
    }
    setDeleting(playlist.id);
    try {
      await api.deletePlaylist(playlist.id);
      await onChanged();
      notify(`Deleted “${playlist.name}”`);
    } catch (error) {
      notify(errorMessage(error), "error");
    } finally {
      setDeleting(null);
    }
  };

  return (
    <section className="page">
      <header className="page-head">
        <div>
          <h1>Playlists</h1>
          <p>Line up tracks and videos into a queue you can play anywhere.</p>
        </div>
        <form className="inline-form" onSubmit={create}>
          <input
            type="text"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="New playlist"
            maxLength={80}
            aria-label="New playlist name"
          />
          <button type="submit" className="btn btn-primary" disabled={!name.trim() || busy}>
            <Icon name="plus" size={16} />
            Create
          </button>
        </form>
      </header>

      {playlists.length === 0 ? (
        <EmptyState
          icon="list"
          title="No playlists yet"
          body="Create your first playlist above, then add tracks from the library with the + button."
        />
      ) : (
        <div className="playlist-grid">
          {playlists.map((playlist) => (
            <div key={playlist.id} className="playlist-card">
              <a className="playlist-open" href={`#/playlists/${playlist.id}`}>
                <span className="playlist-art" aria-hidden="true">
                  <Icon name="list" size={24} />
                </span>
                <span className="playlist-info">
                  <strong>{playlist.name}</strong>
                  <span>
                    {playlist.item_count} track{playlist.item_count === 1 ? "" : "s"} ·{" "}
                    {formatDuration(playlist.duration)}
                  </span>
                </span>
              </a>
              <button
                type="button"
                className="icon-btn icon-btn-danger playlist-delete"
                onClick={() => void remove(playlist)}
                disabled={deleting === playlist.id}
                aria-label={`Delete playlist ${playlist.name}`}
                title="Delete playlist"
              >
                <Icon name="trash" size={16} />
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
