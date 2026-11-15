import type { ResourceEntry } from "./model";
export type ClientRequirement =
  "required" | "optional" | "unknown" | "unsupported";
export type ResourceTier = ClientRequirement | "unavailable";
export const requirementLabels: Record<ResourceTier, string> = {
  required: "客户端必需",
  optional: "客户端可选",
  unknown: "待确认",
  unsupported: "仅服务端",
  unavailable: "不可导入",
};
export function clientRequirement(row: ResourceEntry): ClientRequirement {
  if (row.status === "server_only") return "unsupported";
  if (row.client_requirement) return row.client_requirement;
  if (row.origin === "manifest") return row.optional ? "optional" : "required";
  return "unknown";
}
export function resourceTier(row: ResourceEntry): ResourceTier {
  if (row.status === "server_only") return "unsupported";
  return row.selectable ? clientRequirement(row) : "unavailable";
}
export function requirementExplanation(row: ResourceEntry): string {
  const requirement = clientRequirement(row);
  if (requirement === "unsupported")
    return row.origin === "manifest"
      ? "整合包清单声明客户端不支持此文件。"
      : "Mod 元数据声明仅用于服务端。";
  if (requirement === "optional")
    return "整合包清单将此文件标记为客户端可选，可按需保留。";
  if (requirement === "required")
    return "整合包清单将此文件列为客户端必需；排除可能导致内容缺失或依赖失败。";
  return "包内或本地文件未声明客户端是否必需，需结合用途和依赖确认。";
}
