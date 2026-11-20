import { useCallback, useEffect, useRef, useState } from "react";
import type { StoragePlan } from "./storageManagement";

export interface ScanProgress {
  task: string;
  state: string;
  phase?: string;
  files: number;
  dirs: number;
  bytes: number;
  current: string;
  error?: string;
  completedRoles?: string[];
  totalRoles?: number;
}

export interface ScanStart {
  state: string;
  task?: string;
  reused?: boolean;
  progress?: ScanProgress;
}

export interface ScanSnapshot {
  cached: boolean;
  plan: StoragePlan | null;
  task?: ScanProgress | null;
}

export interface RefreshResult {
  incremental: boolean;
  plan: StoragePlan | null;
}

export type ScanLoad = <T>(
  action: string,
  fields?: Record<string, unknown>,
) => Promise<T>;

const POLL_MS = 400;
const FINISHED = new Set(["complete", "cancelled", "failed", "interrupted"]);
const ACTIVE = new Set(["queued", "running"]);

/**
 * Storage scanning lives outside the page component so that switching pages
 * never cancels a running scan and returning to the page re-attaches to it.
 * Every answer is tagged with the workspace that asked for it; a late result
 * for a previous workspace can never overwrite the current one.
 */
export function useStorageScan({
  enabled,
  workspace,
  load,
}: {
  enabled: boolean;
  workspace: string;
  load: ScanLoad;
}) {
  const [plan, setPlan] = useState<StoragePlan | null>(null);
  const [progress, setProgress] = useState<ScanProgress | null>(null);
  const [scanning, setScanning] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const planRef = useRef<StoragePlan | null>(null);
  const loadRef = useRef(load);
  const taskRef = useRef<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const generationRef = useRef(0);
  const mountedRef = useRef(true);

  loadRef.current = load;

  const remember = useCallback((next: StoragePlan | null) => {
    planRef.current = next;
    setPlan(next);
  }, []);

  const clearTimer = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = null;
  }, []);

  const finish = useCallback(
    (next: StoragePlan | null, note: string) => {
      if (!mountedRef.current) return;
      remember(next);
      setMessage(note);
      setScanning(false);
      setProgress(null);
      taskRef.current = null;
    },
    [remember],
  );

  const poll = useCallback(
    async (generation: number, id: string) => {
      const alive = () =>
        mountedRef.current && generationRef.current === generation;
      try {
        const state = await loadRef.current<
          ScanProgress & { status: string }
        >("storage-scan-status", { task: id });
        if (!alive()) return;
        setProgress(state);
        if (!FINISHED.has(state.state) && state.state !== "cancelling") {
          setScanning(true);
          timerRef.current = setTimeout(
            () => void poll(generation, id),
            POLL_MS,
          );
          return;
        }
        if (state.state === "complete") {
          const result = await loadRef.current<ScanSnapshot>(
            "storage-snapshot",
          );
          if (!alive()) return;
          finish(result.plan, "");
          return;
        }
        if (state.state === "cancelled") {
          finish(planRef.current, "已取消扫描，未完成的统计没有写入缓存。");
          return;
        }
        if (state.state === "cancelling") {
          // The worker acknowledged the request; keep polling until it stops.
          setScanning(true);
          timerRef.current = setTimeout(
            () => void poll(generation, id),
            POLL_MS,
          );
          return;
        }
        finish(planRef.current, "");
        setScanning(false);
        setError(state.error || "扫描未完成，请重试。");
      } catch (e) {
        if (!alive()) return;
        setScanning(false);
        setError(String(e).replace(/^Error: /, ""));
      }
    },
    [finish],
  );

  const attach = useCallback(
    async (id: string, generation: number) => {
      taskRef.current = id;
      setScanning(true);
      setError("");
      await poll(generation, id);
    },
    [poll],
  );

  const start = useCallback(
    async (generation: number) => {
      setScanning(true);
      setError("");
      setMessage("");
      try {
        const result = await loadRef.current<ScanStart>("storage-scan-start");
        if (!mountedRef.current || generationRef.current !== generation) return;
        if (!result.task) {
          setScanning(false);
          return;
        }
        await attach(result.task, generation);
      } catch (e) {
        if (!mountedRef.current || generationRef.current !== generation) return;
        setScanning(false);
        setError(String(e).replace(/^Error: /, ""));
      }
    },
    [attach],
  );

  /** Cached numbers first, then a background refresh if nothing is running. */
  const open = useCallback(async () => {
    if (!enabled) return;
    const generation = ++generationRef.current;
    setError("");
    try {
      const snapshot = await loadRef.current<ScanSnapshot>("storage-snapshot");
      if (!mountedRef.current || generationRef.current !== generation) return;
      if (snapshot.plan) {
        // The snapshot row and the plan can disagree after an upgrade; the plan
        // is what the page renders, so state the cache age there too.
        remember(
          snapshot.cached
            ? {
                ...snapshot.plan,
                cached: true,
                scanState: snapshot.plan.scanState ?? "cached",
              }
            : snapshot.plan,
        );
      }
      const running = snapshot.task;
      if (running && ACTIVE.has(running.state) && running.task) {
        await attach(running.task, generation);
        return;
      }
      if (snapshot.cached && snapshot.plan) {
        // Cached numbers are on screen. Re-walking only the directories the
        // journal reported changed keeps them fresh without a full rescan; a
        // gap or missing cursor returns incremental:false and we scan properly.
        try {
          const refreshed = await loadRef.current<RefreshResult>(
            "storage-refresh",
          );
          if (!mountedRef.current || generationRef.current !== generation) return;
          if (refreshed.incremental && refreshed.plan) {
            remember(refreshed.plan);
            return;
          }
        } catch {
          /* fall through to a full scan */
        }
        if (!mountedRef.current || generationRef.current !== generation) return;
        await start(generation);
        return;
      }
      await start(generation);
    } catch (e) {
      if (!mountedRef.current || generationRef.current !== generation) return;
      setError(String(e).replace(/^Error: /, ""));
    }
  }, [attach, enabled, remember, start]);

  const rescan = useCallback(() => {
    void start(++generationRef.current);
  }, [start]);

  const cancel = useCallback(async () => {
    const id = taskRef.current;
    clearTimer();
    if (!id) {
      setScanning(false);
      return;
    }
    // Supersede the in-flight poll: it must not report "running" after the
    // user has cancelled, and its answer belongs to a scan we abandoned.
    const generation = ++generationRef.current;
    taskRef.current = null;
    setScanning(false);
    setProgress(null);
    setMessage("正在取消扫描…");
    try {
      const state = await loadRef.current<ScanProgress & { status: string }>(
        "storage-scan-cancel",
        { task: id },
      );
      if (!mountedRef.current || generationRef.current !== generation) return;
      if (state.state === "cancelled") {
        setMessage("已取消扫描，未完成的统计没有写入缓存。");
        return;
      }
      await poll(generation, id);
    } catch (e) {
      if (!mountedRef.current || generationRef.current !== generation) return;
      setMessage("");
      setError(String(e).replace(/^Error: /, ""));
    }
  }, [clearTimer, poll]);

  /** Re-read the committed snapshot after a cleanup or a layout change. */
  const reload = useCallback(async () => {
    const generation = ++generationRef.current;
    clearTimer();
    taskRef.current = null;
    setScanning(false);
    try {
      const snapshot = await loadRef.current<ScanSnapshot>("storage-snapshot");
      if (!mountedRef.current || generationRef.current !== generation) return;
      remember(snapshot.plan);
    } catch {
      /* The caller reports the error of the operation that changed data. */
    }
  }, [clearTimer, remember]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      clearTimer();
      generationRef.current += 1;
    };
  }, [clearTimer]);

  // A workspace change invalidates every number and every in-flight answer.
  useEffect(() => {
    generationRef.current += 1;
    clearTimer();
    planRef.current = null;
    setPlan(null);
    setProgress(null);
    setScanning(false);
    setMessage("");
    setError("");
    taskRef.current = null;
  }, [workspace, clearTimer]);

  return {
    plan,
    progress,
    scanning,
    message,
    error,
    open,
    rescan,
    cancel,
    reload,
    setError,
  };
}
