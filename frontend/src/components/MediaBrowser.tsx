import { useMemo, useState } from "react";
import type { SortKey } from "../api";
import type { IconName } from "../icons";
import { Icon } from "../icons";
import type { Media } from "../types";
import { EmptyState } from "./EmptyState";
import { MediaCard } from "./MediaCard";

interface Props {
  title: string;
  subtitle: string;
  items: Media[];
  emptyIcon: IconName;
  emptyTitle: string;
  emptyBody: string;
  emptyAction?: { label: string; onClick: () => void };
  onSelect: (media: Media, queue: Media[]) => void;
  onFavorite: (media: Media) => void;
  onDelete: (media: Media) => void;
  onPlaylist: (media: Media) => void;
  onScan?: () => void;
  scanning?: boolean;
}

const SORT_OPTIONS: Array<{ value: SortKey; label: string }> = [
  { value: "recent", label: "Recently added" },
  { value: "title", label: "Title A–Z" },
  { value: "duration", label: "Longest first" },
  { value: "plays", label: "Most played" },
];

export function MediaBrowser({
  title,
  subtitle,
  items,
  emptyIcon,
  emptyTitle,
  emptyBody,
  emptyAction,
  onSelect,
  onFavorite,
  onDelete,
  onPlaylist,
  onScan,
  scanning = false,
}: Props) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortKey>("recent");

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const filtered = needle
      ? items.filter((item) =>
          [item.title, item.artist, item.album].some((value) =>
            value?.toLowerCase().includes(needle),
          ),
        )
      : [...items];
    switch (sort) {
      case "title":
        return filtered.sort((a, b) => a.title.localeCompare(b.title));
      case "duration":
        return filtered.sort((a, b) => (b.duration ?? 0) - (a.duration ?? 0));
      case "plays":
        return filtered.sort(
          (a, b) => b.play_count - a.play_count || b.added_at.localeCompare(a.added_at),
        );
      default:
        return filtered.sort((a, b) => b.added_at.localeCompare(a.added_at));
    }
  }, [items, query, sort]);

  return (
    <section className="page">
      <header className="page-head">
        <div>
          <h1>{title}</h1>
          <p>{subtitle}</p>
        </div>
        {onScan && (
          <button
            type="button"
            className="btn btn-ghost"
            onClick={onScan}
            disabled={scanning}
          >
            <Icon name="scan" size={16} />
            {scanning ? "Scanning…" : "Rescan files"}
          </button>
        )}
      </header>

      {items.length === 0 ? (
        <EmptyState
          icon={emptyIcon}
          title={emptyTitle}
          body={emptyBody}
          action={emptyAction}
        />
      ) : (
        <>
          <div className="toolbar">
            <label className="search">
              <Icon name="search" size={17} />
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search titles, artists, albums"
                aria-label="Search library"
              />
            </label>
            <label className="select">
              <span className="sr-only">Sort by</span>
              <select
                value={sort}
                onChange={(event) => setSort(event.target.value as SortKey)}
              >
                {SORT_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <span className="toolbar-count">
              {visible.length} of {items.length}
            </span>
          </div>

          {visible.length === 0 ? (
            <div className="empty empty-inline">
              <h2>No matches</h2>
              <p>Nothing here matches “{query.trim()}”.</p>
              <button type="button" className="btn btn-ghost" onClick={() => setQuery("")}>
                Clear search
              </button>
            </div>
          ) : (
            <div className="grid">
              {visible.map((media) => (
                <MediaCard
                  key={media.id}
                  media={media}
                  onSelect={(item) => onSelect(item, visible)}
                  onFavorite={onFavorite}
                  onPlaylist={onPlaylist}
                  onDelete={onDelete}
                />
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}
