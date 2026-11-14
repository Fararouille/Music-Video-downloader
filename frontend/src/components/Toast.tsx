import { Icon } from "../icons";

export function Toast({ message, tone }: { message: string; tone: "ok" | "error" }) {
  return (
    <div className={`toast toast-${tone}`} role="status" aria-live="polite">
      <Icon name={tone === "ok" ? "check" : "close"} size={16} />
      <span>{message}</span>
    </div>
  );
}
