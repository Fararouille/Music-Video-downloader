import { Icon } from "../icons";

export function Logo() {
  return (
    <span className="logo">
      <span className="logo-mark" aria-hidden="true">
        <Icon name="play" size={15} />
      </span>
      <span className="logo-word">crate</span>
    </span>
  );
}
