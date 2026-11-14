import type { RefObject } from "react";
import { artGradient, formatDuration, formatTime } from "../format";
import { Icon } from "../icons";
import { thumbUrl } from "../api";
import type { AudioBindings, PlayerController } from "../usePlayer";

interface Props {
  player: PlayerController;
  audioRef: RefObject<HTMLAudioElement | null>;
  audioProps: AudioBindings;
}

export function PlayerBar({ player, audioRef, audioProps }: Props) {
  const current = player.current;
  const max = Math.max(player.duration || current?.duration || 0, 0.1);
  const value = Math.min(player.time, max);
  const hasNext = player.index >= 0 && player.index + 1 < player.queue.length;

  return (
    <>
      <audio ref={audioRef} {...audioProps} preload="metadata" />
      {current && (
        <div className="player" role="region" aria-label="Now playing">
          <div className="player-track">
            <span className="player-art" style={{ background: artGradient(current.id) }}>
              {current.has_thumb ? (
                <img src={thumbUrl(current.id)} alt="" />
              ) : (
                <Icon name={current.kind === "video" ? "video" : "music"} size={18} />
              )}
            </span>
            <span className="player-meta">
              <span className="player-title" title={current.title}>
                {current.title}
              </span>
              <span className="player-sub">{current.artist ?? "Unknown artist"}</span>
            </span>
          </div>

          <div className="player-center">
            <div className="player-controls">
              <button
                type="button"
                className="icon-btn"
                onClick={player.previous}
                aria-label="Previous track"
              >
                <Icon name="prev" size={18} />
              </button>
              <button
                type="button"
                className="play-btn"
                onClick={player.toggle}
                aria-label={player.playing ? "Pause" : "Play"}
              >
                <Icon name={player.playing ? "pause" : "play"} size={20} />
              </button>
              <button
                type="button"
                className="icon-btn"
                onClick={player.next}
                aria-label="Next track"
                disabled={!hasNext}
              >
                <Icon name="next" size={18} />
              </button>
            </div>
            <div className="player-progress">
              <span className="player-time">{formatTime(player.time)}</span>
              <input
                type="range"
                min={0}
                max={max}
                step={0.1}
                value={value}
                onChange={(event) => player.seek(Number(event.target.value))}
                aria-label="Seek"
              />
              <span className="player-time">{formatDuration(player.duration)}</span>
            </div>
          </div>

          <div className="player-right">
            <Icon name="music" size={16} className="player-volume-icon" />
            <input
              type="range"
              className="volume"
              min={0}
              max={1}
              step={0.01}
              value={player.volume}
              onChange={(event) => player.changeVolume(Number(event.target.value))}
              aria-label="Volume"
            />
            <button
              type="button"
              className="icon-btn"
              onClick={player.close}
              aria-label="Close player"
            >
              <Icon name="close" size={16} />
            </button>
          </div>
        </div>
      )}
    </>
  );
}
