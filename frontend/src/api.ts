import type {
  Health,
  Job,
  JobKind,
  Media,
  MediaKind,
  Playlist,
  PlaylistSummary,
  Session,
} from "./types";

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

type Options = {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
};

async function request<T>(path: string, options: Options = {}): Promise<T> {
  const headers: Record<string, string> = {};
  const init: RequestInit = {
    method: options.method ?? "GET",
    credentials: "same-origin",
    headers,
  };
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(options.body);
  }
  if (options.signal) {
    init.signal = options.signal;
  }

  const response = await fetch(path, init);
  if (response.status === 401) {
    window.dispatchEvent(new Event("crate:unauthorized"));
  }
  if (!response.ok) {
    let detail = response.statusText || "request failed";
    try {
      const payload = (await response.json()) as {
        detail?: string | Array<{ msg?: string }>;
      };
      if (typeof payload.detail === "string") {
        detail = payload.detail;
      } else if (Array.isArray(payload.detail)) {
        detail = payload.detail.map((item) => item.msg ?? "invalid value").join(", ");
      }
    } catch {
      // Response had no JSON body; keep the status text.
    }
    throw new ApiError(detail, response.status);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

function query(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

export type SortKey = "recent" | "title" | "duration" | "plays";

export interface MediaQuery {
  kind?: MediaKind;
  q?: string;
  sort?: SortKey;
  favorite?: boolean;
  limit?: number;
}

export interface MediaPatch {
  title?: string;
  artist?: string | null;
  album?: string | null;
  favorite?: boolean;
}

export interface DownloadRequest {
  url: string;
  kind: JobKind;
  quality: string;
}

export const api = {
  session: () => request<Session>("/api/session"),
  login: (token: string) =>
    request<{ ok: boolean }>("/api/login", { method: "POST", body: { token } }),
  logout: () => request<{ ok: boolean }>("/api/logout", { method: "POST" }),
  health: () => request<Health>("/api/health"),

  media: (params: MediaQuery = {}) =>
    request<{ items: Media[] }>(`/api/media${query({ ...params })}`),
  mediaItem: (id: string) => request<Media>(`/api/media/${id}`),
  patchMedia: (id: string, patch: MediaPatch) =>
    request<Media>(`/api/media/${id}`, { method: "PATCH", body: patch }),
  deleteMedia: (id: string) =>
    request<void>(`/api/media/${id}`, { method: "DELETE" }),
  played: (id: string) =>
    request<void>(`/api/media/${id}/played`, { method: "POST" }),
  scan: () => request<{ added: number; updated: number; removed: number }>(
    "/api/library/scan",
    { method: "POST" },
  ),

  playlists: () =>
    request<{ items: PlaylistSummary[] }>("/api/playlists"),
  playlist: (id: string) => request<Playlist>(`/api/playlists/${id}`),
  createPlaylist: (name: string) =>
    request<Playlist>("/api/playlists", { method: "POST", body: { name } }),
  renamePlaylist: (id: string, name: string) =>
    request<Playlist>(`/api/playlists/${id}`, { method: "PATCH", body: { name } }),
  deletePlaylist: (id: string) =>
    request<void>(`/api/playlists/${id}`, { method: "DELETE" }),
  addPlaylistItem: (playlistId: string, mediaId: string) =>
    request<{ added: boolean }>(`/api/playlists/${playlistId}/items`, {
      method: "POST",
      body: { media_id: mediaId },
    }),
  removePlaylistItem: (playlistId: string, mediaId: string) =>
    request<{ removed: boolean }>(
      `/api/playlists/${playlistId}/items/${mediaId}`,
      { method: "DELETE" },
    ),
  reorderPlaylist: (playlistId: string, mediaIds: string[]) =>
    request<Playlist>(`/api/playlists/${playlistId}/order`, {
      method: "PUT",
      body: { media_ids: mediaIds },
    }),

  downloads: (limit = 50) =>
    request<{ items: Job[] }>(`/api/downloads${query({ limit })}`),
  enqueue: (payload: DownloadRequest) =>
    request<Job>("/api/downloads", { method: "POST", body: payload }),
  cancelDownload: (id: string) =>
    request<{ canceled: boolean }>(`/api/downloads/${id}/cancel`, {
      method: "POST",
    }),
  retryDownload: (id: string) =>
    request<{ queued: boolean }>(`/api/downloads/${id}/retry`, { method: "POST" }),
  deleteDownload: (id: string) =>
    request<void>(`/api/downloads/${id}`, { method: "DELETE" }),
};

export const streamUrl = (id: string) => `/api/media/${id}/stream`;
export const fileUrl = (id: string) => `/api/media/${id}/file`;
export const thumbUrl = (id: string) => `/api/media/${id}/thumb`;
export const m3uUrl = (playlistId: string) => `/api/playlists/${playlistId}/m3u`;

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) {
    return error.message;
  }
  return "something went wrong";
}
