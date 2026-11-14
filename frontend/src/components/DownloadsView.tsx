import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { api, errorMessage } from "../api";
import { formatDate, formatEta } from "../format";
import { Icon } from "../icons";
import type { Job, JobKind, Media, Notify } from "../types";
import { EmptyState } from "./EmptyState";

interface Props {
  media: Media[];
  onSelect: (media: Media, queue: Media[]) => void;
  onLibraryChanged: () => Promise<void> | void;
  notify: Notify;
}

const AUDIO_QUALITIES = ["320", "192", "128"];
const VIDEO_QUALITIES = ["best", "2160", "1440", "1080", "720", "480", "360"];

function qualityLabel(quality: string, kind: JobKind): string {
  if (kind === "audio") {
    return `${quality} kbps MP3`;
  }
  return quality === "best" ? "Best available" : `${quality}p`;
}

function statusLabel(job: Job): string {
  switch (job.status) {
    case "queued":
      return "Queued";
    case "running":
      return `${Math.round(job.progress * 100)}%`;
    case "done":
      return "Ready";
    case "error":
      return "Failed";
    case "canceled":
      return "Cancelled";
    default:
      return job.status;
  }
}

export function DownloadsView({ media, onSelect, onLibraryChanged, notify }: Props) {
  const [url, setUrl] = useState("");
  const [kind, setKind] = useState<JobKind>("audio");
  const [quality, setQuality] = useState("192");
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<string | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);

  const load = useCallback(
    async (quiet = false) => {
      try {
        const data = await api.downloads(60);
        setJobs(data.items);
      } catch (error) {
        if (!quiet) {
          notify(errorMessage(error), "error");
        }
      }
    },
    [notify],
  );

  useEffect(() => {
    void load(true);
  }, [load]);

  const active = jobs.some((job) => job.status === "queued" || job.status === "running");

  useEffect(() => {
    if (!active) {
      return;
    }
    const timer = window.setInterval(() => void load(true), 1500);
    return () => window.clearInterval(timer);
  }, [active, load]);

  const wasActive = useRef(false);
  useEffect(() => {
    if (wasActive.current && !active) {
      void onLibraryChanged();
    }
    wasActive.current = active;
  }, [active, onLibraryChanged]);

  const chooseKind = (next: JobKind) => {
    setKind(next);
    setQuality(next === "audio" ? "192" : "1080");
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = url.trim();
    if (!trimmed || busy) {
      return;
    }
    setBusy(true);
    try {
      await api.enqueue({ url: trimmed, kind, quality });
      setUrl("");
      notify("Added to the download queue");
      await load(true);
    } catch (error) {
      notify(errorMessage(error), "error");
    } finally {
      setBusy(false);
    }
  };

  const act = async (action: () => Promise<unknown>, message: string, jobId: string) => {
    setPending(jobId);
    try {
      await action();
      notify(message);
      await load(true);
    } catch (error) {
      notify(errorMessage(error), "error");
    } finally {
      setPending(null);
    }
  };

  const qualities = kind === "audio" ? AUDIO_QUALITIES : VIDEO_QUALITIES;

  return (
    <section className="page">
      <header className="page-head">
        <div>
          <h1>Downloads</h1>
          <p>Paste a link, choose a format, and crate fetches it in the background.</p>
        </div>
      </header>

      <form className="download-form" onSubmit={submit}>
        <label className="field field-wide">
          <span>Media URL</span>
          <input
            type="url"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="https://www.youtube.com/watch?v=…"
            required
            maxLength={2048}
          />
        </label>

        <div className="field">
          <span>Format</span>
          <div className="segmented" role="group" aria-label="Download format">
            <button
              type="button"
              className={kind === "audio" ? "active" : ""}
              onClick={() => chooseKind("audio")}
              aria-pressed={kind === "audio"}
            >
              <Icon name="music" size={15} />
              MP3
            </button>
            <button
              type="button"
              className={kind === "video" ? "active" : ""}
              onClick={() => chooseKind("video")}
              aria-pressed={kind === "video"}
            >
              <Icon name="video" size={15} />
              MP4
            </button>
          </div>
        </div>

        <label className="field">
          <span>Quality</span>
          <select value={quality} onChange={(event) => setQuality(event.target.value)}>
            {qualities.map((value) => (
              <option key={value} value={value}>
                {qualityLabel(value, kind)}
              </option>
            ))}
          </select>
        </label>

        <button type="submit" className="btn btn-primary download-submit" disabled={busy || !url.trim()}>
          <Icon name="download" size={16} />
          {busy ? "Adding…" : "Download"}
        </button>
      </form>

      <p className="form-note">
        Video downloads merge the best audio and video streams, so the result is capped by the
        source. MP3 conversion needs ffmpeg — crate bundles one through imageio-ffmpeg.
      </p>

      <div className="section-head">
        <h2>Recent downloads</h2>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => void load()}>
          <Icon name="scan" size={15} />
          Refresh
        </button>
      </div>

      {jobs.length === 0 ? (
        <EmptyState
          icon="download"
          title="Nothing downloading yet"
          body="Paste a link above. Finished downloads show up in your library automatically."
        />
      ) : (
        <ul className="jobs">
          {jobs.map((job) => {
            const finished = job.media_id ? media.find((item) => item.id === job.media_id) : undefined;
            const working = job.status === "queued" || job.status === "running";
            return (
              <li key={job.id} className={`job job-${job.status}`}>
                <div className="job-main">
                  <div className="job-title-row">
                    <span className={`chip chip-${job.status}`}>{statusLabel(job)}</span>
                    <p className="job-title" title={job.title ?? job.url}>
                      {job.title ?? job.url}
                    </p>
                  </div>
                  <p className="job-meta">
                    {job.kind === "audio" ? "MP3" : "MP4"} · {qualityLabel(job.quality, job.kind)} ·{" "}
                    {formatDate(job.created_at)}
                    {job.speed ? ` · ${job.speed}` : ""}
                    {job.eta ? ` · ${formatEta(job.eta)}` : ""}
                  </p>
                  {working && (
                    <div
                      className="progress"
                      role="progressbar"
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={Math.round(job.progress * 100)}
                      aria-label="Download progress"
                    >
                      <span
                        style={{
                          width: `${Math.max(job.status === "queued" ? 0 : job.progress * 100, 2)}%`,
                        }}
                      />
                    </div>
                  )}
                  {job.error && <p className="job-error">{job.error}</p>}
                </div>

                <div className="job-actions">
                  {working && (
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      disabled={pending === job.id}
                      onClick={() =>
                        void act(() => api.cancelDownload(job.id), "Download cancelled", job.id)
                      }
                    >
                      Cancel
                    </button>
                  )}
                  {(job.status === "error" || job.status === "canceled") && (
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      disabled={pending === job.id}
                      onClick={() => void act(() => api.retryDownload(job.id), "Queued again", job.id)}
                    >
                      <Icon name="retry" size={15} />
                      Retry
                    </button>
                  )}
                  {job.status === "done" && finished && (
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => onSelect(finished, media)}
                    >
                      <Icon name="play" size={14} />
                      Play
                    </button>
                  )}
                  {job.status !== "running" && (
                    <button
                      type="button"
                      className="icon-btn icon-btn-danger"
                      aria-label="Remove from download history"
                      title="Remove from history"
                      disabled={pending === job.id}
                      onClick={() =>
                        void act(() => api.deleteDownload(job.id), "Removed from history", job.id)
                      }
                    >
                      <Icon name="trash" size={16} />
                    </button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
