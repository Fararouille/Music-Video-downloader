import { formatBytes } from "../format";
import { Icon } from "../icons";
import { NAV_ITEMS } from "../nav";
import type { Health } from "../types";
import type { Route } from "../router";
import { Logo } from "./Logo";

interface Props {
  route: Route;
  health: Health | null;
  counts: { audio: number; video: number; total: number };
  playlistCount: number;
  storage: number;
  scanning: boolean;
  onScan: () => void;
  onLogout: () => void;
}

function badgeFor(label: string, counts: Props["counts"], playlistCount: number): number | null {
  switch (label) {
    case "Library":
      return counts.total;
    case "Music":
      return counts.audio;
    case "Videos":
      return counts.video;
    case "Playlists":
      return playlistCount;
    default:
      return null;
  }
}

export function Sidebar({
  route,
  health,
  counts,
  playlistCount,
  storage,
  scanning,
  onScan,
  onLogout,
}: Props) {
  return (
    <aside className="sidebar">
      <a className="sidebar-brand" href="#/" aria-label="crate home">
        <Logo />
      </a>

      <nav className="sidebar-nav" aria-label="Main navigation">
        {NAV_ITEMS.map((item) => {
          const badge = badgeFor(item.label, counts, playlistCount);
          return (
            <a
              key={item.href}
              href={item.href}
              className={`nav-link${item.active(route) ? " active" : ""}`}
              aria-current={item.active(route) ? "page" : undefined}
            >
              <Icon name={item.icon} size={18} />
              <span>{item.label}</span>
              {badge !== null && <span className="nav-badge">{badge}</span>}
            </a>
          );
        })}
      </nav>

      <div className="sidebar-foot">
        <div className="stat-line">
          <span>Library size</span>
          <strong>{formatBytes(storage)}</strong>
        </div>
        <div className="stat-line">
          <span>ffmpeg</span>
          <strong className={health?.ffmpeg ? "ok" : "warn"}>
            {health?.ffmpeg ? "ready" : "missing"}
          </strong>
        </div>
        <div className="stat-line">
          <span>yt-dlp</span>
          <strong>{health?.ytdlp ?? "missing"}</strong>
        </div>

        <button type="button" className="btn btn-ghost btn-sm" onClick={onScan} disabled={scanning}>
          <Icon name="scan" size={16} />
          {scanning ? "Scanning…" : "Rescan files"}
        </button>
        {health?.auth_required && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={onLogout}>
            <Icon name="logout" size={16} />
            Sign out
          </button>
        )}
        <p className="version">crate v{health?.version ?? "0.1.0"}</p>
      </div>
    </aside>
  );
}
