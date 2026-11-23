import { useEffect, useRef } from "react";

function editable(el: EventTarget | null) {
  if (!(el instanceof HTMLElement)) return false;
  return el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName);
}

/**
 * Single-key shortcuts (Bloomberg-style function keys). Ignored while typing in
 * a field or with a modifier held, so they never fight the browser or a form.
 */
export function useHotkeys(map: Record<string, (e: KeyboardEvent) => void>) {
  const ref = useRef(map);
  useEffect(() => {
    ref.current = map;
  });
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || e.defaultPrevented || editable(e.target)) return;
      // Enter on a focused link or button keeps its native meaning.
      if (e.key === "Enter" && e.target instanceof HTMLElement && e.target.closest("a, button")) return;
      const fn = ref.current[e.key] ?? ref.current[e.key.toLowerCase()];
      if (!fn) return;
      e.preventDefault();
      fn(e);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
