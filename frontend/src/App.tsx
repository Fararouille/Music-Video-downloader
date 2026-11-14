import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { ApiError, api, errorMessage } from "./api";
import { AddToPlaylistDialog } from "./components/AddToPlaylistDialog";
import { DownloadsView } from "./components/DownloadsView";
import { LoginScreen } from "./components/LoginScreen";
import { Logo } from "./components/Logo";
import { MediaBrowser } from "./components/MediaBrowser";
import { MobileNav } from "./components/MobileNav";
import { PlayerBar } from "./components/PlayerBar";
import { PlaylistDetail } from "./components/PlaylistDetail";
import { PlaylistsView } from "./components/PlaylistsView";
import { Sidebar } from "./components/Sidebar";
import { Toast } from "./components/Toast";
import { VideoOverlay } from "./components/VideoOverlay";
import { formatBytes, formatDuration } from "./format";
import { Icon } from "./icons";
import { navigate, useRoute } from "./router";
import type { Health, Media, Notify, PlaylistSummary, Session } from "./types";
import { usePlayer } from "./usePlayer";

export default function App() {
  const route = useRoute();
  const { player, audioRef, audioProps } = usePlayer();

  const [session, setSession] = useState<Session | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [media, setMedia] = useState<Media[]>([]);
  const [playlists, setPlaylists] = useState<PlaylistSummary[]>([]);
  const [scanning, setScanning] = useState(false);
  const [video, setVideo] = useState<Media | null>(null);
  const [playlistTarget, setPlaylistTarget] = useState<Media | null>(null);
  const [toast, setToast] = useState<{ message: string; tone: "ok" | "error" } | null>(null);

  const toastTimer = useRef<number | null>(null);
  const reported = useRef<string | null>(null);

  const notify: Notify = useCallback((message, tone = "ok") => {
    setToast({ message, tone });
    if (toastTimer.current !== null) {
      window.clearTimeout(toastTimer.current);
    }
    toastTimer.current = window.setTimeout(() => setToast(null), 3400);
  }, []);

  useEffect(
    () => () => {
      if (toastTimer.current !== null) {
        window.clearTimeout(toastTimer.current);
      }
    },
    [],
  );

  const refresh = useCallback(async () => {
    try {
      const [library, lists, status] = await Promise.all([
        api.media({ limit: 5000 }),
        api.playlists(),
        api.health(),
      ]);
      setMedia(library.items);
      setPlaylists(lists.items);
      setHealth(status);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        return;
      }
      notify(errorMessage(error), "error");
    }
  }, [notify]);

  const refreshPlaylists = useCallback(async () => {
    try {
      const lists = await api.playlists();
      setPlaylists(lists.items);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        return;
      }
      notify(errorMessage(error), "error");
    }
  }, [notify]);

  useEffect(() => {
    let cancelled = false;
    api
      .session()
      .then((value) => {
        if (!cancelled) {
          setSession(value);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSession({ auth_required: false, authenticated: false });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const handler = () => setSession({ auth_required: true, authenticated: false });
    window.addEventListener("crate:unauthorized", handler);
    return () => window.removeEventListener("crate:unauthorized", handler);
  }, []);

  useEffect(() => {
    if (session?.authenticated) {
      void refresh();
    }
  }, [session?.authenticated, refresh]);

  useEffect(() => {
    const current = player.current;
    if (!current) {
      reported.current = null;
      return;
    }
    if (!player.playing || reported.current === current.id) {
      return;
    }
    reported.current = current.id;
    void api
      .played(current.id)
      .then(() => {
        setMedia((rows) =>
          rows.map((row) =>
            row.id === current.id
              ? { ...row, play_count: row.play_count + 1, played_at: new Date().toISOString() }
              : row,
          ),
        );
      })
      .catch(() => undefined);
  }, [player.current?.id, player.playing]);

  useEffect(() => {
    if (!video) {
      return;
    }
    void api.played(video.id).catch(() => undefined);
    setMedia((rows) =>
      rows.map((row) =>
        row.id === video.id
          ? { ...row, play_count: row.play_count + 1, played_at: new Date().toISOString() }
          : row,
      ),
    );
  }, [video]);

  const handleSelect = useCallback(
    (item: Media, queue: Media[]) => {
      if (item.kind === "video") {
        setVideo(item);
        return;
      }
      player.play(
        item,
        queue.filter((row) => row.kind === "audio"),
      );
    },
    [player],
  );

  const toggleFavorite = useCallback(
    async (item: Media) => {
      try {
        const updated = await api.patchMedia(item.id, { favorite: !item.favorite });
        setMedia((rows) => rows.map((row) => (row.id === updated.id ? updated : row)));
      } catch (error) {
        notify(errorMessage(error), "error");
      }
    },
    [notify],
  );

  const removeMedia = useCallback(
    async (item: Media) => {
      if (
        !window.confirm(
          `Delete “${item.title}” from the library? This removes the file from disk.`,
        )
      ) {
        return;
      }
      try {
        await api.deleteMedia(item.id);
        setMedia((rows) => rows.filter((row) => row.id !== item.id));
        if (player.current?.id === item.id) {
          player.close();
        }
        await refreshPlaylists();
        notify("Deleted from library");
      } catch (error) {
        notify(errorMessage(error), "error");
      }
    },
    [notify, player, refreshPlaylists],
  );

  const scan = useCallback(async () => {
    setScanning(true);
    try {
      const result = await api.scan();
      await refresh();
      notify(`Library scanned: ${result.added} added, ${result.removed} removed`);
    } catch (error) {
      notify(errorMessage(error), "error");
    } finally {
      setScanning(false);
    }
  }, [notify, refresh]);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      // The cookie is cleared locally either way.
    }
    player.close();
    setSession({ auth_required: true, authenticated: false });
    navigate("#/");
  }, [player]);

  const counts = useMemo(() => {
    const audio = media.filter((item) => item.kind === "audio").length;
    return { audio, video: media.length - audio, total: media.length };
  }, [media]);

  const audioItems = useMemo(() => media.filter((item) => item.kind === "audio"), [media]);
  const videoItems = useMemo(() => media.filter((item) => item.kind === "video"), [media]);

  const storage = useMemo(
    () => media.reduce((sum, item) => sum + item.size, 0),
    [media],
  );
  const audioDuration = useMemo(
    () => audioItems.reduce((sum, item) => sum + (item.duration ?? 0), 0),
    [audioItems],
  );
  const videoSize = useMemo(
    () => videoItems.reduce((sum, item) => sum + item.size, 0),
    [videoItems],
  );

  const closeVideo = useCallback(() => setVideo(null), []);
  const closePlaylist = useCallback(() => setPlaylistTarget(null), []);

  if (!session) {
    return (
      <div className="splash">
        <Logo />
        <p>Loading your crate…</p>
      </div>
    );
  }

  if (session.auth_required && !session.authenticated) {
    return (
      <LoginScreen
        onSuccess={() => setSession({ auth_required: true, authenticated: true })}
      />
    );
  }

  let content: ReactNode;
  switch (route.name) {
    case "music":
      content = (
        <MediaBrowser
          title="Music"
          subtitle={`${audioItems.length} songs · ${formatDuration(audioDuration)}`}
          items={audioItems}
          emptyIcon="music"
          emptyTitle="No music yet"
          emptyBody="Download a track as MP3, or drop files into library/audio and rescan."
          emptyAction={{ label: "Start a download", onClick: () => navigate("#/downloads") }}
          onSelect={handleSelect}
          onFavorite={toggleFavorite}
          onDelete={removeMedia}
          onPlaylist={setPlaylistTarget}
          onScan={() => void scan()}
          scanning={scanning}
        />
      );
      break;
    case "videos":
      content = (
        <MediaBrowser
          title="Videos"
          subtitle={`${videoItems.length} videos · ${formatBytes(videoSize)}`}
          items={videoItems}
          emptyIcon="video"
          emptyTitle="No videos yet"
          emptyBody="Download something as MP4, or drop files into library/video and rescan."
          emptyAction={{ label: "Start a download", onClick: () => navigate("#/downloads") }}
          onSelect={handleSelect}
          onFavorite={toggleFavorite}
          onDelete={removeMedia}
          onPlaylist={setPlaylistTarget}
          onScan={() => void scan()}
          scanning={scanning}
        />
      );
      break;
    case "playlists":
      content = (
        <PlaylistsView
          playlists={playlists}
          onChanged={refreshPlaylists}
          notify={notify}
        />
      );
      break;
    case "playlist":
      content = (
        <PlaylistDetail
          key={route.id}
          playlistId={route.id}
          onChanged={refreshPlaylists}
          onSelect={handleSelect}
          notify={notify}
        />
      );
      break;
    case "downloads":
      content = (
        <DownloadsView
          media={media}
          onSelect={handleSelect}
          onLibraryChanged={refresh}
          notify={notify}
        />
      );
      break;
    default:
      content = (
        <MediaBrowser
          title="Library"
          subtitle={`${counts.audio} songs · ${counts.video} videos · ${formatBytes(storage)}`}
          items={media}
          emptyIcon="disc"
          emptyTitle="Your crate is empty"
          emptyBody="Paste a link in Downloads, or drop media into the library folder and rescan."
          emptyAction={{ label: "Download something", onClick: () => navigate("#/downloads") }}
          onSelect={handleSelect}
          onFavorite={toggleFavorite}
          onDelete={removeMedia}
          onPlaylist={setPlaylistTarget}
          onScan={() => void scan()}
          scanning={scanning}
        />
      );
  }

  return (
    <div className={`app-shell${player.current ? " has-player" : ""}`}>
      <Sidebar
        route={route}
        health={health}
        counts={counts}
        playlistCount={playlists.length}
        storage={storage}
        scanning={scanning}
        onScan={() => void scan()}
        onLogout={() => void logout()}
      />

      <div className="app-frame">
        <header className="mobile-top">
          <Logo />
          <button
            type="button"
            className="icon-btn"
            onClick={() => void scan()}
            disabled={scanning}
            aria-label="Rescan files"
          >
            <Icon name="scan" size={18} />
          </button>
        </header>
        <main className="app-content">{content}</main>
      </div>

      <PlayerBar player={player} audioRef={audioRef} audioProps={audioProps} />
      <MobileNav route={route} />

      {video && <VideoOverlay media={video} onClose={closeVideo} />}
      {playlistTarget && (
        <AddToPlaylistDialog
          media={playlistTarget}
          playlists={playlists}
          onClose={closePlaylist}
          onChanged={refreshPlaylists}
          notify={notify}
        />
      )}
      {toast && <Toast message={toast.message} tone={toast.tone} />}
    </div>
  );
}
