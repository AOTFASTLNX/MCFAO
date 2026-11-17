/**
 * Classifies the paths reported by the native drag session. A directory is a
 * valid Prism instance candidate, and the drag payload carries no file type,
 * so only names with a clearly unrelated file extension are rejected. The
 * preflight still validates the real contents; this only stops a known-wrong
 * file from starting a read.
 */
const UNSUPPORTED = new Set([
  "zip",
  "jar",
  "txt",
  "json",
  "png",
  "jpg",
  "jpeg",
  "gif",
  "dmg",
  "pkg",
  "ipa",
  "app",
  "tar",
  "gz",
  "7z",
  "rar",
  "pdf",
  "sh",
  "py",
]);

export function dragVerdict(paths: string[]): "accepted" | "rejected" {
  if (paths.length === 0) return "accepted";
  const usable = paths.some((path) => {
    const name = path.split("/").filter(Boolean).pop() ?? "";
    if (!name) return false;
    if (/\.mrpack$/i.test(name)) return true;
    const extension = /\.([a-z0-9]{1,8})$/i.exec(name)?.[1]?.toLowerCase();
    return !extension || !UNSUPPORTED.has(extension);
  });
  return usable ? "accepted" : "rejected";
}

export function dropMessage(verdict: "accepted" | "rejected"): string {
  return verdict === "rejected"
    ? "请选择 .mrpack 文件或 Prism 实例目录"
    : "松开以导入 .mrpack 或 Prism 实例";
}
