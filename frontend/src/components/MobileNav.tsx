import { Icon } from "../icons";
import { NAV_ITEMS } from "../nav";
import type { Route } from "../router";

export function MobileNav({ route }: { route: Route }) {
  return (
    <nav className="mobile-nav" aria-label="Main navigation">
      {NAV_ITEMS.map((item) => (
        <a
          key={item.href}
          href={item.href}
          className={`mobile-link${item.active(route) ? " active" : ""}`}
          aria-current={item.active(route) ? "page" : undefined}
        >
          <Icon name={item.icon} size={21} />
          <span>{item.label}</span>
        </a>
      ))}
    </nav>
  );
}
