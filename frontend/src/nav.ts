import type { IconName } from "./icons";
import type { Route } from "./router";

export interface NavItem {
  href: string;
  label: string;
  icon: IconName;
  active: (route: Route) => boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { href: "#/", label: "Library", icon: "disc", active: (route) => route.name === "library" },
  { href: "#/music", label: "Music", icon: "music", active: (route) => route.name === "music" },
  { href: "#/videos", label: "Videos", icon: "video", active: (route) => route.name === "videos" },
  {
    href: "#/playlists",
    label: "Playlists",
    icon: "list",
    active: (route) => route.name === "playlists" || route.name === "playlist",
  },
  {
    href: "#/downloads",
    label: "Downloads",
    icon: "download",
    active: (route) => route.name === "downloads",
  },
];
