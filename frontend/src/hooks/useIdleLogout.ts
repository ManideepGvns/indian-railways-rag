import { useEffect, useRef } from "react";

const IDLE_TIMEOUT_MS = 15 * 60 * 1000; // 15 minutes

/**
 * Calls `onIdle` after the user has been inactive for IDLE_TIMEOUT_MS.
 * Activity is detected via mouse, keyboard, scroll, and touch events.
 * The timer resets on every activity event.
 */
export function useIdleLogout(onIdle: () => void, enabled: boolean) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onIdleRef = useRef(onIdle);
  onIdleRef.current = onIdle;

  useEffect(() => {
    if (!enabled) return;

    const reset = () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => onIdleRef.current(), IDLE_TIMEOUT_MS);
    };

    const EVENTS = [
      "mousemove", "mousedown", "keydown",
      "scroll", "touchstart", "click",
    ] as const;

    EVENTS.forEach((e) => window.addEventListener(e, reset, { passive: true }));

    // Start the timer immediately
    reset();

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      EVENTS.forEach((e) => window.removeEventListener(e, reset));
    };
  }, [enabled]);
}
