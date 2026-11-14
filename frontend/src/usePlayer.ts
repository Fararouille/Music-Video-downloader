import { useCallback, useEffect, useRef, useState } from "react";
import type { RefObject } from "react";
import { streamUrl } from "./api";
import type { Media } from "./types";

export interface PlayerController {
  queue: Media[];
  current: Media | null;
  index: number;
  playing: boolean;
  time: number;
  duration: number;
  volume: number;
  play: (media: Media, queue: Media[]) => void;
  toggle: () => void;
  next: () => void;
  previous: () => void;
  seek: (time: number) => void;
  changeVolume: (volume: number) => void;
  close: () => void;
}

export interface AudioBindings {
  onTimeUpdate: () => void;
  onLoadedMetadata: () => void;
  onEnded: () => void;
  onPlay: () => void;
  onPause: () => void;
  onError: () => void;
}

interface Player {
  player: PlayerController;
  audioRef: RefObject<HTMLAudioElement | null>;
  audioProps: AudioBindings;
}

const VOLUME_KEY = "crate:volume";

function initialVolume(): number {
  const stored = Number(window.localStorage.getItem(VOLUME_KEY));
  return Number.isFinite(stored) && stored >= 0 && stored <= 1 ? stored : 0.9;
}

export function usePlayer(): Player {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [queue, setQueue] = useState<Media[]>([]);
  const [index, setIndex] = useState(-1);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(initialVolume);

  const current = index >= 0 && index < queue.length ? queue[index] : null;
  const autoplay = useRef(false);
  const currentRef = useRef<Media | null>(null);
  currentRef.current = current;

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) {
      return;
    }
    if (!current) {
      audio.removeAttribute("src");
      audio.load();
      setPlaying(false);
      setTime(0);
      setDuration(0);
      return;
    }
    audio.src = streamUrl(current.id);
    audio.load();
    setTime(0);
    setDuration(current.duration ?? 0);
    if (autoplay.current) {
      void audio.play().catch(() => setPlaying(false));
    }
  }, [current?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    window.localStorage.setItem(VOLUME_KEY, String(volume));
    if (audioRef.current) {
      audioRef.current.volume = volume;
    }
  }, [volume]);

  const play = useCallback((media: Media, list: Media[]) => {
    const audio = audioRef.current;
    const nextQueue = list.some((item) => item.id === media.id) ? list : [media];
    if (currentRef.current?.id === media.id) {
      setQueue(nextQueue);
      setIndex(nextQueue.findIndex((item) => item.id === media.id));
      if (audio) {
        audio.currentTime = 0;
        autoplay.current = true;
        void audio.play().catch(() => setPlaying(false));
      }
      return;
    }
    autoplay.current = true;
    setQueue(nextQueue);
    setIndex(nextQueue.findIndex((item) => item.id === media.id));
  }, []);

  const toggle = useCallback(() => {
    const audio = audioRef.current;
    if (!audio || !currentRef.current) {
      return;
    }
    if (audio.paused) {
      autoplay.current = true;
      void audio.play().catch(() => setPlaying(false));
    } else {
      audio.pause();
    }
  }, []);

  const next = useCallback(() => {
    if (index < 0) {
      return;
    }
    if (index + 1 >= queue.length) {
      const audio = audioRef.current;
      if (audio) {
        audio.pause();
        audio.currentTime = 0;
      }
      setTime(0);
      return;
    }
    autoplay.current = true;
    setIndex(index + 1);
  }, [index, queue.length]);

  const previous = useCallback(() => {
    const audio = audioRef.current;
    if (audio && audio.currentTime > 3) {
      audio.currentTime = 0;
      setTime(0);
      return;
    }
    if (index > 0) {
      autoplay.current = true;
      setIndex(index - 1);
    }
  }, [index]);

  const seek = useCallback((value: number) => {
    const audio = audioRef.current;
    if (audio) {
      audio.currentTime = value;
      setTime(value);
    }
  }, []);

  const changeVolume = useCallback((value: number) => {
    setVolume(Math.min(1, Math.max(0, value)));
  }, []);

  const close = useCallback(() => {
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      audio.currentTime = 0;
    }
    autoplay.current = false;
    setQueue([]);
    setIndex(-1);
    setPlaying(false);
    setTime(0);
    setDuration(0);
  }, []);

  const audioProps = {
    onTimeUpdate: () => setTime(audioRef.current?.currentTime ?? 0),
    onLoadedMetadata: () => {
      const audio = audioRef.current;
      if (!audio) {
        return;
      }
      setDuration(Number.isFinite(audio.duration) ? audio.duration : currentRef.current?.duration ?? 0);
    },
    onEnded: next,
    onPlay: () => setPlaying(true),
    onPause: () => setPlaying(false),
    onError: () => setPlaying(false),
  };

  const player: PlayerController = {
    queue,
    current,
    index,
    playing,
    time,
    duration,
    volume,
    play,
    toggle,
    next,
    previous,
    seek,
    changeVolume,
    close,
  };

  return { player, audioRef, audioProps };
}
