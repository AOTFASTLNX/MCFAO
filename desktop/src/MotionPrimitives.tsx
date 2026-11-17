import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import {
  MOTION,
  useAnimatedNumber,
  useReducedMotion,
  type MotionDirection,
  type MotionPhase,
} from "./motion";

/**
 * The moving selection layer used by the stepper and the sidebar. It is
 * positioned by the hook and painted behind the row content; while it moves,
 * the settled row background is suppressed so only one layer is visible.
 */
export function MotionIndicator({
  indicatorRef,
  moving,
}: {
  indicatorRef: React.RefObject<HTMLSpanElement | null>;
  moving: boolean;
}) {
  return (
    <span
      ref={indicatorRef}
      className="motion-indicator"
      data-moving={moving ? "true" : "false"}
      aria-hidden="true"
    />
  );
}

/**
 * Directional step content with a measured height hand-off. The outgoing
 * panel keeps its own content while it fades; the incoming panel starts on
 * the opposite side, so forward and back read differently without moving the
 * surrounding page.
 */
export function StepBody({
  step,
  phase,
  direction,
  children,
  className = "",
}: {
  step: number;
  phase: MotionPhase;
  direction: MotionDirection;
  children: ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const measured = useRef(0);
  const reduced = useReducedMotion();
  const [height, setHeight] = useState<number | null>(null);
  const lastStep = useRef(step);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    measured.current = element.offsetHeight;
    const observer = new ResizeObserver(() => {
      if (!element.style.height) measured.current = element.offsetHeight;
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    if (lastStep.current === step) return;
    const previous = measured.current;
    lastStep.current = step;
    if (reduced) {
      setHeight(null);
      return;
    }
    element.style.transition = "none";
    element.style.height = `${previous}px`;
    element.style.overflow = "hidden";
    const next = element.scrollHeight;
    // Commit the old height first, then release into the new one so the
    // change reads as a settle instead of a jump.
    void element.offsetHeight;
    element.style.transition = `height ${MOTION.normal}ms ${MOTION.easing.out}`;
    element.style.height = `${next}px`;
    setHeight(next);
  }, [step, reduced]);

  useEffect(() => {
    if (height === null) return;
    const timer = window.setTimeout(() => {
      const element = ref.current;
      if (!element) return;
      element.style.transition = "";
      element.style.height = "";
      element.style.overflow = "";
      measured.current = element.offsetHeight;
      setHeight(null);
    }, MOTION.normal + 40);
    return () => window.clearTimeout(timer);
  }, [height]);

  return (
    <div
      ref={ref}
      className={"step-body " + className}
      data-phase={phase}
      data-direction={direction}
    >
      {children}
    </div>
  );
}

/** Whole-number counter that rolls between values without reflowing layout. */
export function AnimatedNumber({
  value,
  format = (n) => String(Math.round(n)),
  minDelta = 0,
  className = "",
}: {
  value: number;
  format?: (value: number) => string;
  minDelta?: number;
  className?: string;
}) {
  const display = useAnimatedNumber(value, { minDelta });
  return (
    <span className={"motion-number " + className}>{format(display)}</span>
  );
}

/**
 * Cross-fades a status glyph while keeping the box size fixed, so rows never
 * reflow when a check becomes a spinner or a warning.
 */
export function StatusMark({
  state,
  children,
  size = 18,
}: {
  state: string;
  children: ReactNode;
  size?: number;
}) {
  return (
    <span
      className="status-mark"
      data-state={state}
      style={{ "--mark-size": `${size}px` } as CSSProperties}
    >
      <span key={state} className="status-mark-glyph">
        {children}
      </span>
    </span>
  );
}

/**
 * Animates height for disclosure content. The panel is measured after mount
 * and removed from the flow only while closing, so interactive children keep
 * working normally.
 */
export function Reveal({
  open,
  children,
  className = "",
}: {
  open: boolean;
  children: ReactNode;
  className?: string;
}) {
  const reduced = useReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const [mounted, setMounted] = useState(open);
  const [expanded, setExpanded] = useState(open);
  useEffect(() => {
    if (open) setMounted(true);
    const frame = requestAnimationFrame(() => setExpanded(open));
    if (open) return () => cancelAnimationFrame(frame);
    const timer = window.setTimeout(
      () => setMounted(false),
      reduced ? 0 : MOTION.expand + 20,
    );
    return () => {
      cancelAnimationFrame(frame);
      window.clearTimeout(timer);
    };
  }, [open, reduced]);
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element || reduced) return;
    const inner = element.firstElementChild as HTMLElement | null;
    if (!inner) return;
    const next = expanded ? inner.scrollHeight : 0;
    element.style.height = `${next}px`;
    if (!expanded) return;
    const timer = window.setTimeout(() => {
      element.style.height = "auto";
    }, MOTION.expand + 20);
    return () => window.clearTimeout(timer);
  }, [expanded, reduced, mounted]);
  if (!mounted) return null;
  return (
    <div
      ref={ref}
      className={"motion-reveal " + className}
      data-expanded={expanded ? "true" : "false"}
      style={reduced ? undefined : { height: expanded ? undefined : 0 }}
    >
      <div className="motion-reveal-inner">{children}</div>
    </div>
  );
}

/** Shared press feedback: scale down while the pointer is held. */
export function usePressFeedback() {
  const [pressed, setPressed] = useState(false);
  const reduced = useReducedMotion();
  const props = {
    onPointerDown: () => !reduced && setPressed(true),
    onPointerUp: () => setPressed(false),
    onPointerLeave: () => setPressed(false),
    onPointerCancel: () => setPressed(false),
    "data-pressed": pressed ? "true" : "false",
  };
  return { pressed, props };
}
