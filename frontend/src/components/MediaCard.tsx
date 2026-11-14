import { artGradient, formatDuration, initials } from "../format";
import { fileUrl, thumbUrl } from "../api";
import { Icon } from "../icons";
import type { Media } from "../types";
import { useEffect, useState } from "react";

interface Props {
  media: Media;
  onSelect: (media: Media) => void;
  onFavorite: (media: Media) => void;
  onPlaylist: (media: Media) => void;
  onDelete: (media: Media) => void;
}

export function MediaCard({ media, onSelect, onFavorite, onPlaylist, onDelete }: Props) {
  const [broken, setBroken] = useState(false);

  useEffect(() => {
    setBroken(false);
  }, [media.thumbnail]);

  const label =
    media.kind === "video"
      ? media.height
        ? `${media.height}p`
        : "Video"
      : media.ext.toUpperCase();

  return (
    <article className="card">
      <button
        type="button"
        className="card-art"
        style={{ background: artGradient(media.id) }}
        onClick={() => onSelect(media)}
        aria-label={`${media.kind === "video" ? "Watch" : "Play"} ${media.title}`}
      >
        {media.has_thumb && !broken ? (
          <img
            src={thumbUrl(media.id)}
            alt=""
            loading="lazy"
            onError={() => setBroken(true)}
          />
        ) : (
          <span className="card-fallback" aria-hidden="true">
            {initials(media.title)}
          </span>
        )}
        <span className="card-play" aria-hidden="true">
          <Icon name="play" size={20} />
        </span>
        <span className="card-badges">
          {media.kind === "video" && <span className="badge">{label}</span>}
          <span className="badge">{formatDuration(media.duration)}</span>
        </span>
        {media.favorite && (
          <span className="card-heart" aria-hidden="true">
            <Icon name="heart" size={13} filled />
          </span>
        )}
      </button>

      <div className="card-body">
        <p className="card-title" title={media.title}>
          {media.title}
        </p>
        <p className="card-sub" title={media.artist ?? media.album ?? undefined}>
          {media.artist ?? media.album ?? (media.kind === "video" ? "Video" : "Unknown artist")}
        </p>
        <div className="card-actions">
          <button
            type="button"
            className={`icon-btn${media.favorite ? " is-active" : ""}`}
            onClick={() => onFavorite(media)}
            aria-label={media.favorite ? "Remove from favorites" : "Add to favorites"}
            aria-pressed={media.favorite}
            title={media.favorite ? "Remove from favorites" : "Add to favorites"}
          >
            <Icon name="heart" size={16} filled={media.favorite} />
          </button>
          <button
            type="button"
            className="icon-btn"
            onClick={() => onPlaylist(media)}
            aria-label="Add to playlist"
            title="Add to playlist"
          >
            <Icon name="plus" size={16} />
          </button>
          <a
            className="icon-btn"
            href={fileUrl(media.id)}
            aria-label={`Download ${media.title}`}
            title="Download file"
          >
            <Icon name="download" size={16} />
          </a>
          <button
            type="button"
            className="icon-btn icon-btn-danger"
            onClick={() => onDelete(media)}
            aria-label={`Delete ${media.title}`}
            title="Delete from library"
          >
            <Icon name="trash" size={16} />
          </button>
        </div>
      </div>
    </article>
  );
}
