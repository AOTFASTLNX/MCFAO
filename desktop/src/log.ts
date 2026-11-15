const LEVEL =
  /\b(?:INFO|WARN(?:ING)?|ERROR|DEBUG|TRACE|FATAL|NOTICE|BLOCKED|FAIL(?:ED)?|PASS(?:ED)?|OK)\b/i;

export type LogTone = "info" | "warning" | "error" | "muted" | "plain";

export function logTone(line: string): LogTone {
  if (/\b(?:ERROR|FATAL|FAIL(?:ED)?|BLOCKED)\b/i.test(line)) return "error";
  if (/\b(?:WARN(?:ING)?|NOTICE|UNSUPPORTED)\b/i.test(line)) return "warning";
  if (/\b(?:INFO|PASS(?:ED)?|OK|DONE)\b/i.test(line)) return "info";
  if (/^\s*(?:#|--|\/\/|阶段|等待|正在)/.test(line)) return "muted";
  return "plain";
}

export function logLevel(line: string): string | null {
  const match = line.match(LEVEL);
  return match ? match[0].toUpperCase() : null;
}
