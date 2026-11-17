import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";

/**
 * One timing scale for the whole Builder. Components consume these tokens
 * through CSS variables; the values below are the source of truth for the
 * small amount of motion that has to be driven from JavaScript.
 */
export const MOTION = {
  instant: 100,
  fast: 160,
  normal: 240,
  smooth: 320,
  expand: 360,
  completion: 480,
  offsetSmall: 4,
  offsetMedium: 16,
  scalePressed: 0.985,
  scaleEnter: 0.96,
  easing: {
    out: "cubic-bezier(0.22, 1, 0.36, 1)",
    spring: "cubic-bezier(0.34, 1.3, 0.64, 1)",
    standard: "cubic-bezier(0.2, 0, 0, 1)",
    in: "cubic-bezier(0.4, 0, 1, 1)",
  },
} as const;

export type MotionDirection = "forward" | "back" | "none";
export type MotionPhase = "idle" | "out" | "in";
export type MotionPreference = "full" | "reduced";

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function directionBetween(
  previous: number,
  next: number,
): MotionDirection {
  if (next > previous) return "forward";
  if (next < previous) return "back";
  return "none";
}

export function easeOutCubic(t: number): number {
  const value = clamp(t, 0, 1);
  return 1 - Math.pow(1 - value, 3);
}

export function formatDuration(milliseconds: number): string {
  const total = Math.max(0, Math.floor(milliseconds / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  const pad = (value: number) => String(value).padStart(2, "0");
  return hours
    ? `${hours}:${pad(minutes)}:${pad(seconds)}`
    : `${pad(minutes)}:${pad(seconds)}`;
}

export function stepPercent(current: number, total: number): number {
  return total > 0 ? clamp((current / total) * 100, 0, 100) : 0;
}

type MotionQuery = Pick<MediaQueryList, "matches"> & {
  addEventListener?: (type: string, listener: () => void) => void;
  removeEventListener?: (type: string, listener: () => void) => void;
  addListener?: (listener: () => void) => void;
  removeListener?: (listener: () => void) => void;
};

export function createMotionStore(query: MotionQuery | null) {
  let preference: MotionPreference = query?.matches ? "reduced" : "full";
  const listeners = new Set<() => void>();
  const update = () => {
    const next: MotionPreference = query?.matches ? "reduced" : "full";
    if (next === preference) return;
    preference = next;
    listeners.forEach((listener) => listener());
  };
  query?.addEventListener?.("change", update);
  query?.addListener?.(update);
  return {
    get: () => preference,
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    destroy() {
      query?.removeEventListener?.("change", update);
      query?.removeListener?.(update);
      listeners.clear();
    },
  };
}

const browserMotionStore =
  typeof window === "undefined" || typeof window.matchMedia !== "function"
    ? null
    : createMotionStore(window.matchMedia("(prefers-reduced-motion: reduce)"));

export function useMotionPreference(): MotionPreference {
  return useSyncExternalStore(
    browserMotionStore?.subscribe ?? (() => () => undefined),
    browserMotionStore?.get ?? (() => "full"),
    () => "full",
  );
}

export function useReducedMotion(): boolean {
  return useMotionPreference() === "reduced";
}

/**
 * Keeps an absolutely positioned selection layer on the active item. The
 * layer is always parked on the active item; it only becomes visible while a
 * selection change is interpolating, so the settled UI keeps its original
 * row backgrounds. Changing the target mid-transition simply retargets the
 * same element, which is what makes rapid switching cancel cleanly.
 */
export function useSlidingIndicator<T extends HTMLElement>(
  activeIndex: number,
  options: { duration?: number; enabled?: boolean } = {},
) {
  const containerRef = useRef<T>(null);
  const indicatorRef = useRef<HTMLSpanElement>(null);
  const [moving, setMoving] = useState(false);
  const [ready, setReady] = useState(false);
  const firstPass = useRef(true);
  const reduced = useReducedMotion();
  const activeRef = useRef(activeIndex);
  activeRef.current = activeIndex;
  const timer = useRef<number | undefined>(undefined);
  const duration = options.duration ?? MOTION.smooth;
  const enabled = options.enabled !== false;

  const position = useCallback((animate: boolean, hide: boolean) => {
    const container = containerRef.current;
    const indicator = indicatorRef.current;
    if (!container || !indicator) return;
    const items = Array.from(
      container.querySelectorAll<HTMLElement>("[data-motion-item]"),
    );
    const item = items[activeRef.current];
    if (!item) {
      indicator.style.opacity = "0";
      return;
    }
    const box = container.getBoundingClientRect();
    const rect = item.getBoundingClientRect();
    if (!animate) indicator.style.transition = "none";
    indicator.style.transform = `translate3d(${rect.left - box.left}px, ${rect.top - box.top}px, 0)`;
    indicator.style.width = `${rect.width}px`;
    indicator.style.height = `${rect.height}px`;
    indicator.style.opacity = hide ? "0" : "1";
    if (!animate) {
      // Force the new geometry to be the transition origin before restoring
      // the CSS transition for the next selection change.
      void indicator.offsetWidth;
      indicator.style.transition = "";
    }
  }, []);

  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    window.clearTimeout(timer.current);
    if (!ready) {
      position(false, true);
      setReady(true);
      return;
    }
    if (firstPass.current) {
      // The first ready pass only records the initial geometry; it must not
      // play an entrance move or briefly suppress the settled row colour.
      firstPass.current = false;
      setMoving(false);
      position(false, true);
      return;
    }
    if (reduced || !enabled) {
      setMoving(false);
      position(false, true);
      return;
    }
    setMoving(true);
    // Retargeting mid-flight must not restart from the old row: let the
    // browser interpolate from the current painted position.
    position(true, false);
    timer.current = window.setTimeout(() => {
      setMoving(false);
      position(false, true);
    }, duration + 20);
    return () => window.clearTimeout(timer.current);
  }, [activeIndex, ready, reduced, enabled, duration, position]);

  useEffect(() => {
    if (!ready) return;
    const container = containerRef.current;
    if (!container) return;
    const measure = () => position(false, true);
    const observer = new ResizeObserver(measure);
    observer.observe(container);
    container
      .querySelectorAll<HTMLElement>("[data-motion-item]")
      .forEach((item) => observer.observe(item));
    window.addEventListener("resize", measure);
    void document.fonts?.ready.then(measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [ready, position, activeIndex]);

  return { containerRef, indicatorRef, moving, ready };
}

/**
 * A single content panel that can play a directional exit and entrance. The
 * panel stays mounted, so form state and scroll position survive a step
 * change; only its opacity and a small translate are animated.
 */
export function useStepContent(
  target: number,
  options: { out?: number; in?: number } = {},
) {
  const reduced = useReducedMotion();
  const outDuration = options.out ?? MOTION.fast;
  const inDuration = options.in ?? MOTION.normal;
  const [view, setView] = useState<{
    step: number;
    phase: MotionPhase;
    direction: MotionDirection;
  }>({ step: target, phase: "idle", direction: "none" });
  const viewRef = useRef(view);
  viewRef.current = view;
  const timers = useRef<number[]>([]);
  const clear = () => {
    timers.current.forEach((timer) => window.clearTimeout(timer));
    timers.current = [];
  };

  useEffect(() => {
    clear();
    const current = viewRef.current;
    if (reduced) {
      setView({ step: target, phase: "idle", direction: "none" });
      return;
    }
    if (target === current.step && current.phase !== "out") {
      if (current.phase !== "idle")
        setView({ step: current.step, phase: "idle", direction: "none" });
      return;
    }
    const direction = directionBetween(current.step, target);
    setView({ step: current.step, phase: "out", direction });
    timers.current.push(
      window.setTimeout(() => {
        setView({ step: target, phase: "in", direction });
        timers.current.push(
          window.setTimeout(() => {
            setView({ step: target, phase: "idle", direction: "none" });
          }, inDuration),
        );
      }, outDuration),
    );
    return clear;
  }, [target, reduced, outDuration, inDuration]);

  return view;
}

/**
 * Page changes only animate the incoming surface. The previous page is
 * replaced immediately, so each screen keeps its own scroll and task state and
 * the navigation never shows two live pages at once.
 */
export function usePageEnter(page: string) {
  const reduced = useReducedMotion();
  const previous = useRef(page);
  const [entered, setEntered] = useState(true);
  const [direction, setDirection] = useState<MotionDirection>("none");
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => {
    if (previous.current === page) return;
    const nextDirection = directionBetween(
      pageIndex(previous.current),
      pageIndex(page),
    );
    previous.current = page;
    setDirection(nextDirection);
    if (reduced) {
      setEntered(true);
      return;
    }
    setEntered(false);
    const frame = requestAnimationFrame(() => {
      setEntered(true);
      timer.current = window.setTimeout(
        () => setDirection("none"),
        MOTION.smooth,
      );
    });
    return () => {
      cancelAnimationFrame(frame);
      window.clearTimeout(timer.current);
    };
  }, [page, reduced]);
  return { entered, direction };
}

/** Marks a short window after a selection change, for CSS-only indicators. */
export function useSelectionPulse(value: string, duration = MOTION.smooth) {
  const reduced = useReducedMotion();
  const previous = useRef(value);
  const [moving, setMoving] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => {
    if (previous.current === value) return;
    previous.current = value;
    window.clearTimeout(timer.current);
    if (reduced) {
      setMoving(false);
      return;
    }
    setMoving(true);
    timer.current = window.setTimeout(() => setMoving(false), duration + 20);
    return () => window.clearTimeout(timer.current);
  }, [value, duration, reduced]);
  return moving;
}

const pageOrder = ["builder", "history", "environment", "storage", "settings"];
function pageIndex(page: string): number {
  return pageOrder.indexOf(page);
}

export function useAnimatedNumber(
  value: number,
  options: {
    duration?: number;
    minDelta?: number;
    enabled?: boolean;
    throttle?: number;
  } = {},
): number {
  const reduced = useReducedMotion();
  const [display, setDisplay] = useState(value);
  const displayRef = useRef(value);
  const frame = useRef<number | undefined>(undefined);
  const lastChange = useRef(0);
  const duration = options.duration ?? MOTION.normal;
  const minDelta = options.minDelta ?? 0;
  const throttle = options.throttle ?? 80;
  const enabled = options.enabled !== false;

  useEffect(() => {
    const target = Number.isFinite(value) ? value : 0;
    const from = displayRef.current;
    if (
      reduced ||
      !enabled ||
      Math.abs(target - from) < minDelta ||
      typeof requestAnimationFrame !== "function"
    ) {
      displayRef.current = target;
      setDisplay(target);
      return;
    }
    const now = performance.now();
    if (now - lastChange.current < throttle) {
      displayRef.current = target;
      setDisplay(target);
      lastChange.current = now;
      return;
    }
    lastChange.current = now;
    const start = now;
    const tick = (time: number) => {
      const progress = Math.min(1, (time - start) / duration);
      const next = from + (target - from) * easeOutCubic(progress);
      displayRef.current = next;
      setDisplay(next);
      if (progress < 1) frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
    return () => {
      if (frame.current) cancelAnimationFrame(frame.current);
    };
  }, [value, reduced, enabled, duration, minDelta, throttle]);

  return display;
}
