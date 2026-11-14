import { fileUrl, streamUrl } from "../api";
import { Icon } from "../icons";
import type { Media } from "../types";
import { useModal } from "../useModal";

interface Props {
  media: Media;
  onClose: () => void;
}

export function VideoOverlay({ media, onClose }: Props) {
  useModal(onClose);

  return (
    <div className="overlay" role="dialog" aria-modal="true" aria-label={media.title} onClick={onClose}>
      <div className="video-shell" onClick={(event) => event.stopPropagation()}>
        <header className="video-head">
          <div>
            <h2>{media.title}</h2>
            <p>
              {media.artist ?? "Video"}
              {media.width && media.height ? ` · ${media.width}×${media.height}` : ""}
            </p>
          </div>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close video">
            <Icon name="close" />
          </button>
        </header>
        <video key={media.id} src={streamUrl(media.id)} controls autoPlay playsInline />
        <footer className="video-foot">
          <a className="btn btn-ghost btn-sm" href={fileUrl(media.id)}>
            <Icon name="download" size={16} />
            Download
          </a>
          {media.source_url && (
            <a
              className="btn btn-ghost btn-sm"
              href={media.source_url}
              target="_blank"
              rel="noreferrer"
            >
              View source
            </a>
          )}
        </footer>
      </div>
    </div>
  );
}
