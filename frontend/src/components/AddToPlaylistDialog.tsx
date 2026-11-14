import { useState } from "react";
import { api, errorMessage } from "../api";
import { Icon } from "../icons";
import type { Media, Notify, PlaylistSummary } from "../types";
import { useModal } from "../useModal";

interface Props {
  media: Media;
  playlists: PlaylistSummary[];
  onClose: () => void;
  onChanged: () => Promise<void> | void;
  notify: Notify;
}

export function AddToPlaylistDialog({ media, playlists, onClose, onChanged, notify }: Props) {
  const [busy, setBusy] = useState<string | null>(null);
  const [name, setName] = useState("");
  useModal(onClose);

  const add = async (playlist: PlaylistSummary) => {
    setBusy(playlist.id);
    try {
      const result = await api.addPlaylistItem(playlist.id, media.id);
      notify(result.added ? `Added to ${playlist.name}` : `Already in ${playlist.name}`);
      onClose();
    } catch (error) {
      notify(errorMessage(error), "error");
    } finally {
      setBusy(null);
    }
  };

  const create = async () => {
    const trimmed = name.trim();
    if (!trimmed) {
      return;
    }
    setBusy("create");
    try {
      const playlist = await api.createPlaylist(trimmed);
      await api.addPlaylistItem(playlist.id, media.id);
      await onChanged();
      notify(`Created “${playlist.name}” and added the track`);
      onClose();
    } catch (error) {
      notify(errorMessage(error), "error");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="overlay" role="dialog" aria-modal="true" aria-label="Add to playlist" onClick={onClose}>
      <div className="sheet" onClick={(event) => event.stopPropagation()}>
        <header className="sheet-head">
          <div>
            <h2>Add to playlist</h2>
            <p>{media.title}</p>
          </div>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close">
            <Icon name="close" size={18} />
          </button>
        </header>

        {playlists.length > 0 ? (
          <ul className="sheet-list">
            {playlists.map((playlist) => (
              <li key={playlist.id}>
                <button
                  type="button"
                  className="sheet-row"
                  onClick={() => void add(playlist)}
                  disabled={busy !== null}
                >
                  <span className="sheet-icon">
                    <Icon name="list" size={18} />
                  </span>
                  <span className="sheet-info">
                    <strong>{playlist.name}</strong>
                    <span>
                      {playlist.item_count} track{playlist.item_count === 1 ? "" : "s"}
                    </span>
                  </span>
                  {busy === playlist.id ? (
                    <span className="spinner" aria-hidden="true" />
                  ) : (
                    <Icon name="plus" size={16} />
                  )}
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="sheet-empty">No playlists yet. Create one below.</p>
        )}

        <div className="sheet-create">
          <input
            type="text"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="New playlist name"
            maxLength={80}
            aria-label="New playlist name"
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                void create();
              }
            }}
          />
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => void create()}
            disabled={!name.trim() || busy !== null}
          >
            Create
          </button>
        </div>
      </div>
    </div>
  );
}
