export interface StorageItem {
  path: string;
  bytes: number;
  reason?: string;
}
export interface StorageGroup {
  id: string;
  label: string;
  detail: string;
  count: number;
  bytes: number;
  items: StorageItem[];
}
export interface StorageUsage {
  role: string;
  path: string;
  bytes: number;
  volumeId?: string;
  available?: boolean;
  error?: string;
  itemCount?: number;
  items?: StorageItem[];
}
export interface StorageVolume {
  id: string;
  path: string;
  totalBytes: number;
  freeBytes: number;
  managedBytes: number;
  otherBytes: number;
  roles: string[];
}
export interface StoragePlan {
  status: string;
  dataRoot: string;
  freeBytes: number;
  reclaimBytes: number;
  groups: StorageGroup[];
  blocked: boolean;
  reason?: string;
  usage?: StorageUsage[];
  volumes?: StorageVolume[];
  managedBytes?: number;
  scannedAt?: string;
  warnings?: string[];
}
export const storageRoles: Record<string, string> = {
  cache: "编译缓存",
  builds: "构建产物",
  jobs: "任务记录",
  rust: "Rust 缓存",
};
export function unifiedStoragePaths(directory: string) {
  const base = directory.replace(/\/+$/, "");
  return {
    cache: base + "/cache",
    builds: base + "/builds",
    jobs: base + "/jobs",
    rust: base + "/rust",
  };
}
export function formatBytes(bytes: number): string {
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let unit = 0;
  let value = Math.max(0, Number.isFinite(bytes) ? bytes : 0);
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit++;
  }
  return `${unit ? value.toFixed(1) : value} ${units[unit]}`;
}
export function percent(value: number, total: number): number {
  return total > 0 ? Math.min(100, Math.max(0, (value / total) * 100)) : 0;
}
export function selectedBytes(plan: StoragePlan, choices: string[]): number {
  return plan.groups
    .filter((g) => choices.includes(g.id))
    .reduce((sum, g) => sum + g.bytes, 0);
}
