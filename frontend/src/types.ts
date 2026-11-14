export type MediaKind = "audio" | "video";

export interface Media {
  id: string;
  kind: MediaKind;
  path: string;
  title: string;
  artist: string | null;
  album: string | null;
  duration: number | null;
  size: number;
  ext: string;
  mime: string;
  width: number | null;
  height: number | null;
  source_url: string | null;
  source_id: string | null;
  thumbnail: string | null;
  added_at: string;
  played_at: string | null;
  play_count: number;
  favorite: boolean;
  has_thumb: boolean;
}

export interface PlaylistSummary {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  item_count: number;
  duration: number;
}

export interface Playlist extends PlaylistSummary {
  items: Media[];
}

export type JobStatus = "queued" | "running" | "done" | "error" | "canceled";
export type JobKind = "audio" | "video";

export interface Job {
  id: string;
  url: string;
  kind: JobKind;
  quality: string;
  status: JobStatus;
  progress: number;
  speed: string | null;
  eta: number | null;
  title: string | null;
  error: string | null;
  media_id: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface Health {
  status: string;
  version: string;
  media: { audio: number; video: number; total: number };
  playlists: number;
  ffmpeg: boolean;
  ytdlp: string | null;
  auth_required: boolean;
  private_urls: boolean;
  library: string;
}

export interface Session {
  auth_required: boolean;
  authenticated: boolean;
}

export type Notify = (message: string, tone?: "ok" | "error") => void;
