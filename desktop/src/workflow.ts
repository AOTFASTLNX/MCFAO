import type { Report, EnvironmentCheck } from "./model";
export interface ResourceSelection {
  source: string;
  fingerprint: string;
  included: string[];
}

export interface BuildForm {
  resourceSelection: ResourceSelection | null;
  existingBuild?: string;
  workspace: string;
  python: string;
  config: string;
  exportOptions: string;
  output: string;
  loader: "fabric" | "vanilla";
  source: string;
  team: string;
  audited: boolean;
  forceCompile: boolean;
}
export interface BuildJob {
  id: string;
  name: string;
  state:
    | "queued"
    | "running"
    | "cancelling"
    | "awaiting-exclusions"
    | "cancelled"
    | "interrupted"
    | "failed"
    | "succeeded";
  stage: string;
  startedAt: string;
  finishedAt?: string;
  folder: string;
  build: string;
  request: BuildForm;
  error: string;
  ipa?: string;
  sha256?: string;
  bytes?: number;
  log?: string;
  compatibilityOverrides?: {
    code: string;
    sourceLoader: string;
    buildLoader: string;
    message: string;
  }[];
  exclusionChallenge?: {
    id: string;
    summary: string;
    excludedIds: string[];
    mods: {
      modIds: string[];
      name: string;
      version: string;
      file: string;
      reasons: string[];
    }[];
  };
  acceptedExclusions?: BuildJob["exclusionChallenge"][];
  previousBuilds?: { path: string; reason: string }[];
}
export interface Checks {
  ready: boolean;
  checks: EnvironmentCheck[];
  checkedAt: string;
}
export interface Bootstrap {
  workspace: string;
  config: string;
  exportOptions: string;
  output: string;
  configFields: Record<string, string>;
  jobs: BuildJob[];
}
export const FORM_KEY = "fabricaot.builder.v2";
export const defaultForm: BuildForm = {
  resourceSelection: null,
  workspace: "",
  python: "",
  config: "",
  exportOptions: "",
  output: "",
  loader: "fabric",
  source: "",
  team: "",
  audited: false,
  forceCompile: false,
};
export const configurationFields = [
  ["prepared", "客户端参考输入", "folder"],
  ["caps", "iOS 能力探针", "folder"],
  ["bootstrapRuntime", "Java 25 iOS 运行库", "folder"],
  ["splitter", "方法拆分工具", "folder"],
  ["versionMetadata", "26.1.2 版本元数据", "file"],
  ["assets", "已校验的游戏资源", "folder"],
  ["glfw", "GLFW / 触摸桥接", "folder"],
  ["lwjgl", "LWJGL 原生桥接", "folder"],
  ["gl41", "OpenGL 兼容运行库", "folder"],
  ["lwjglOpengl", "OpenGL 原生桥接", "folder"],
  ["openal", "OpenAL 音频", "folder"],
  ["b1Evidence", "B1 运行验证记录", "file"],
] as const;
export const stages = [
  ["validate", "构建前检查"],
  ["source", "取得并校验内容"],
  ["doctor", "核验全部输入"],
  ["fabric", "Fabric 静态转换"],
  ["split", "方法拆分"],
  ["gl41-patch", "接入 OpenGL 兼容后端"],
  ["aot", "Java 25 原生编译"],
  ["runtime", "构建 iOS 运行库"],
  ["link", "链接 ARM64 镜像"],
  ["stage", "准备应用资源"],
  ["package", "构建与开发签名"],
  ["archive", "归档应用"],
  ["export-log", "导出 IPA"],
  ["verify", "验证签名与产物"],
] as const;
export const stageName = (value: string) =>
  value === "mod-exclusion-review"
    ? "等待排除确认"
    : (stages.find((s) => s[0] === value)?.[1] ?? value);
export const isActive = (job?: BuildJob | null) =>
  !!job &&
  ["queued", "running", "cancelling", "awaiting-exclusions"].includes(
    job.state,
  );
export const stateNames: Record<BuildJob["state"], string> = {
  queued: "等待开始",
  running: "正在构建",
  cancelling: "正在取消",
  "awaiting-exclusions": "等待排除确认",
  cancelled: "已取消",
  interrupted: "已中断",
  failed: "构建失败",
  succeeded: "IPA 已验证",
};
export function buildProblems(
  form: BuildForm,
  report: Report | null,
  desktop: boolean,
): string[] {
  const result: string[] = [];
  if (!desktop) result.push("请在 FabricAOT 桌面应用中执行构建。");
  if (!form.workspace.trim()) result.push("请选择 FabricAOT 项目目录。");
  if (!form.config.trim()) result.push("请选择或创建构建配置。");
  if (!form.exportOptions.trim()) result.push("请选择 IPA 开发导出配置。");
  if (!form.output.trim()) result.push("请选择构建产物目录。");
  if (form.team && !/^[A-Z0-9]{10}$/.test(form.team))
    result.push("Team ID 需要 10 位大写字母或数字。");
  if (form.loader === "fabric") {
    if (!form.source.trim()) result.push("请选择整合包或 Prism 实例。");
    if (!report || report.source !== form.source)
      result.push("请先检查当前来源。");
    else {
      if (
        report.resources &&
        (!form.resourceSelection ||
          form.resourceSelection.source !== form.source ||
          form.resourceSelection.fingerprint !== report.resources_fingerprint)
      )
        result.push("请在资源管理中确认本次保留的资源。");
      if (
        report.resources &&
        form.resourceSelection &&
        !report.resources.some(
          (r) =>
            r.category === "mods" &&
            r.path.toLowerCase().endsWith(".jar") &&
            form.resourceSelection!.included.includes(r.id),
        )
      )
        result.push("整合包构建至少保留一个启用的 Mod。");
      if (report.fatal) result.push("来源存在阻断问题，请先处理。");
    }
    if (!form.audited) result.push("确认 Mod 已审计后，才能执行构建期转换。");
  }
  return result;
}
export function restoreForm(raw: string | null): BuildForm {
  if (!raw) return { ...defaultForm };
  const value = JSON.parse(raw);
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("构建设置损坏");
  const result = { ...defaultForm };
  for (const key of [
    "workspace",
    "python",
    "config",
    "exportOptions",
    "output",
    "source",
    "team",
  ] as const) {
    if (
      value[key] !== undefined &&
      (typeof value[key] !== "string" || value[key].length > 4096)
    )
      throw new Error("构建设置字段无效");
    result[key] = value[key] ?? "";
  }
  result.loader = value.loader === "vanilla" ? "vanilla" : "fabric";
  if (value.resourceSelection != null) {
    const r = value.resourceSelection;
    if (
      typeof r !== "object" ||
      typeof r.source !== "string" ||
      typeof r.fingerprint !== "string" ||
      !/^[a-f0-9]{64}$/.test(r.fingerprint) ||
      !Array.isArray(r.included) ||
      r.included.length > 20000 ||
      r.included.some(
        (id: unknown) => typeof id !== "string" || id.length > 4096,
      )
    )
      throw new Error("资源选择记录无效");
    result.resourceSelection = {
      source: r.source,
      fingerprint: r.fingerprint,
      included: [...new Set<string>(r.included)],
    };
  }
  // Audit acknowledgement belongs to a build session; never grant it from stored data.
  result.audited = false;
  result.forceCompile = false;
  return result;
}
export function mergeJob(jobs: BuildJob[], next: BuildJob): BuildJob[] {
  return [next, ...jobs.filter((j) => j.id !== next.id)]
    .sort((a, b) => b.startedAt.localeCompare(a.startedAt))
    .slice(0, 40);
}
