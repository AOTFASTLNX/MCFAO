import { describe, expect, it, vi } from "vitest";
import {
  MOTION,
  createMotionStore,
  directionBetween,
  easeOutCubic,
  formatDuration,
  stepPercent,
} from "./motion";

describe("motion tokens", () => {
  it("keeps the interaction scale ordered from press to completion", () => {
    const values = [
      MOTION.instant,
      MOTION.fast,
      MOTION.normal,
      MOTION.smooth,
      MOTION.expand,
      MOTION.completion,
    ];
    expect(values).toEqual([...values].sort((a, b) => a - b));
    expect(MOTION.offsetSmall).toBeLessThan(MOTION.offsetMedium);
    expect(MOTION.scalePressed).toBeGreaterThan(MOTION.scaleEnter);
  });

  it("reports the direction of a step change", () => {
    expect(directionBetween(1, 3)).toBe("forward");
    expect(directionBetween(3, 1)).toBe("back");
    expect(directionBetween(2, 2)).toBe("none");
  });
});

describe("motion helpers", () => {
  it("eases out with a clamped cubic curve", () => {
    expect(easeOutCubic(0)).toBe(0);
    expect(easeOutCubic(1)).toBe(1);
    expect(easeOutCubic(-1)).toBe(0);
    expect(easeOutCubic(2)).toBe(1);
    expect(easeOutCubic(0.5)).toBeCloseTo(0.875);
  });

  it("formats build elapsed time without inventing progress", () => {
    expect(formatDuration(0)).toBe("00:00");
    expect(formatDuration(65_000)).toBe("01:05");
    expect(formatDuration(3_725_000)).toBe("1:02:05");
  });

  it("converts a step count into a bounded percentage", () => {
    expect(stepPercent(2, 4)).toBe(50);
    expect(stepPercent(5, 4)).toBe(100);
    expect(stepPercent(-1, 4)).toBe(0);
    expect(stepPercent(1, 0)).toBe(0);
  });
});

describe("reduced motion store", () => {
  it("follows the media query and notifies subscribers once per change", () => {
    const listeners = new Set<() => void>();
    const query = {
      matches: false,
      addEventListener: (_: string, listener: () => void) =>
        listeners.add(listener),
      removeEventListener: (_: string, listener: () => void) =>
        listeners.delete(listener),
    };
    const store = createMotionStore(query);
    const seen: string[] = [];
    const unsubscribe = store.subscribe(() => seen.push(store.get()));
    expect(store.get()).toBe("full");
    query.matches = true;
    listeners.forEach((listener) => listener());
    expect(seen).toEqual(["reduced"]);
    // A duplicate event is not a change.
    listeners.forEach((listener) => listener());
    expect(seen).toEqual(["reduced"]);
    unsubscribe();
    query.matches = false;
    listeners.forEach((listener) => listener());
    expect(seen).toEqual(["reduced"]);
    store.destroy();
    expect(listeners.size).toBe(0);
  });

  it("supports older Safari media query listeners", () => {
    let legacy: (() => void) | null = null;
    const query = {
      matches: false,
      addListener: vi.fn((listener: () => void) => {
        legacy = listener;
      }),
      removeListener: vi.fn(),
    };
    const store = createMotionStore(query);
    query.matches = true;
    legacy!();
    expect(store.get()).toBe("reduced");
    store.destroy();
    expect(query.removeListener).toHaveBeenCalled();
  });
});
