import type { IconName } from "../icons";
import { Icon } from "../icons";

interface Props {
  icon: IconName;
  title: string;
  body: string;
  action?: { label: string; onClick: () => void };
}

export function EmptyState({ icon, title, body, action }: Props) {
  return (
    <div className="empty">
      <span className="empty-icon">
        <Icon name={icon} size={30} />
      </span>
      <h2>{title}</h2>
      <p>{body}</p>
      {action && (
        <button type="button" className="btn btn-primary" onClick={action.onClick}>
          {action.label}
        </button>
      )}
    </div>
  );
}
