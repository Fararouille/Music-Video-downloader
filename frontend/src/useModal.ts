import { useEffect } from "react";

export function useModal(onClose: () => void): void {
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    document.addEventListener("keydown", handler);
    document.body.classList.add("no-scroll");
    return () => {
      document.removeEventListener("keydown", handler);
      document.body.classList.remove("no-scroll");
    };
  }, [onClose]);
}
