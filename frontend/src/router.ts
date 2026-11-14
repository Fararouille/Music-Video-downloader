import { useEffect, useState } from "react";

export type Route =
  | { name: "library" }
  | { name: "music" }
  | { name: "videos" }
  | { name: "playlists" }
  | { name: "playlist"; id: string }
  | { name: "downloads" };

export function parseRoute(hash: string): Route {
  const clean = hash.replace(/^#\/?/, "");
  const [head, tail] = clean.split("/");
  switch (head) {
    case "music":
      return { name: "music" };
    case "videos":
      return { name: "videos" };
    case "downloads":
      return { name: "downloads" };
    case "playlists":
      return tail ? { name: "playlist", id: decodeURIComponent(tail) } : { name: "playlists" };
    default:
      return { name: "library" };
  }
}

export function navigate(path: string): void {
  window.location.hash = path;
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.hash));

  useEffect(() => {
    const update = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);

  return route;
}
