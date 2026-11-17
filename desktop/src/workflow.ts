import type { Report, EnvironmentCheck } from "./model";
export interface ResourceSelection {
  source: string;
  fingerprint: string;
  included: string[];
}

export interface StoragePaths {
  cache: string;
  builds: string;
  jobs: string;
  rust: string;
}
export interface BuildForm {
  kind?: "dependencies";
  dependencyKeys?: string[];
  unsigned?: boolean;
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
  kind?: "dependencies";
  configFields?: Record<string, string>;
  dependencyProgress?: { completed: number; total: number; key?: string };
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
  signature?: string;
  warning?: string;
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
export interface SetupState {
  state: string;
  message?: string;
  completedBytes?: number;
  totalBytes?: number;
  error?: string;
  client?: string;
  javaHome?: string;
}
export interface Bootstrap {
  bundled?: boolean;
  setup?: SetupState;
  storage?: StoragePaths;
  workspace: string;
  config: string;
  exportOptions: string;
  output: string;
  configFields: Record<string, string>;
  jobs: BuildJob[];
}
export { FORM_KEY, LEGACY_FORM_KEY } from "./storage";
export const defaultForm: BuildForm = {
  unsigned: false,
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
  ["metal", "Metal 后端（可选）", "folder"],
  ["shaders", "Metal 着色器（可选）", "folder"],
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
  value.startsWith("dependency-")
    ? "重建 " + (dependencyNames[value.slice(11)] ?? value.slice(11))
    : value === "dependencies-complete"
      ? "依赖库重建完成"
      : value === "mod-exclusion-review"
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

export const dependencyNames: Record<string, string> = {
  glfw: "GLFW-lite",
  lwjgl: "LWJGL-lite",
  gl41: "OSMesa / MoltenVK",
  lwjglOpengl: "LWJGL OpenGL shim",
  metal: "Metal 后端",
  openal: "OpenAL Soft",
  shaders: "着色器",
};
export interface NativeDependency {
  key: string;
  name: string;
  path: string;
  builtAt: string | null;
  target: string;
  state: "current" | "stale" | "missing" | "invalid";
  changedFiles: string[];
  reasons: string[];
  dependsOn: string[];
  required: boolean;
  mode: "build" | "fetch";
  timeBasis?: string;
}
export interface DependencyInventory {
  ready: boolean;
  libraries: NativeDependency[];
  checkedAt: string;
}
export const jobStateName = (job: BuildJob) =>
  job.kind === "dependencies" && job.state === "succeeded"
    ? "依赖库已重建"
    : stateNames[job.state];

export interface ErrorExplanation {
  /** Short headline naming the failing stage and the kind of problem. */
  title: string;
  /** What actually happened, in plain language. */
  cause: string;
  /** Concrete things the user can change before retrying. */
  next: string[];
  /** Whether retrying unchanged is likely to reproduce the same failure. */
  retryHelps: boolean;
}

// Compiler failures arrive as an English first line plus raw log tails. Turn the
// ones we can recognise into a stated cause and an actionable next step; keep
// the original text available so the diagnosis stays inspectable.
export function explainError(
  error: string,
  stage: string,
): ErrorExplanation | null {
  if (!error.trim()) return null;
  const label = stageName(stage);
  const has = (needle: string) => error.includes(needle);

  if (has("OutOfMemoryError") || has("ran out of memory")) {
    const heap = /-Xmx(\d+)g/.exec(error);
    return {
      title: `${label}内存不足`,
      cause:
        `${heap ? `原生编译只拿到 ${heap[1]} GiB 堆内存，` : "原生编译的 Java 堆不够用，"}` +
        "在分析阶段就耗尽了。这是编译主机的内存限制，和整合包、Mod 兼容性无关。",
      next: [
        "关闭占用内存较多的其它应用，给编译器留出余量。",
        "重试时让构建器使用更大的堆内存（Apple Silicon 18 GB 机型可用 9 GiB）。",
        "若仍然耗尽，需要减少同时启用的内容或换内存更大的 Mac。",
      ],
      retryHelps: false,
    };
  }
  if (has("Build inputs changed")) {
    return {
      title: "构建输入与旧目录不一致",
      cause:
        "这次构建沿用了上次的产物目录，但输入指纹已经变化。编译器不会覆盖已写入指纹的目录。",
      next: ["重试即可，构建器会自动换用新的产物目录继续。"],
      retryHelps: true,
    };
  }
  if (has("UNEXPECTED_EOF") || has("SSL") || has("urlopen error")) {
    return {
      title: "下载整合包内容时网络中断",
      cause:
        "从 Modrinth CDN 下载文件时连接被中断，已下载并通过校验的部分会保留。",
      next: ["确认网络稳定后直接重试，已校验的文件不会重复下载。"],
      retryHelps: true,
    };
  }
  if (has("Requested Fabric instance contains excluded Mods")) {
    return {
      title: "仍有无法静态转换的 Mod",
      cause:
        "转换报告里还有运行期定义类或加载原生库的 Mod，需要确认排除后才能继续。",
      next: ["重试后按提示确认排除清单。"],
      retryHelps: true,
    };
  }
  if (has("失败原因不是可确认的静态 AOT 排除项")) {
    return {
      title: "构建在 Fabric 检查阶段停止",
      cause:
        "这一轮的失败发生在静态转换之后，但当时记录的原因只有这句笼统说明，具体错误没有写进任务记录。",
      next: [
        "直接重试；新版本会把 AOT 编译、下载等真实原因写进这条提示。",
        "若要复核这一轮，请打开任务文件夹里的 build.stderr.log 与对应阶段的日志。",
      ],
      retryHelps: true,
    };
  }
  if (has("Host memory headroom")) {
    return {
      title: "主机内存余量不足",
      cause: "构建前的内存检查没有通过，编译器需要比当前可用内存更多的余量。",
      next: ["释放内存后重试。"],
      retryHelps: false,
    };
  }
  if (has("IPA 完整性验证失败") || has("DEVELOPMENT_IPA_VERIFIED")) {
    return {
      title: "导出的 IPA 未通过完整性校验",
      cause: "导出产物与签名记录不一致，构建器拒绝把它当作可用结果。",
      next: ["重试导出；若重复出现，请保留诊断目录。"],
      retryHelps: false,
    };
  }
  if (has("Expected one exported IPA")) {
    return {
      title: "导出目录里不止一个 IPA",
      cause:
        "Xcode 已导出 IPA，但导出目录中出现了额外的 .ipa 文件，构建器无法判断哪个是本次产物。",
      next: [
        "重试即可；已修复的版本会忽略 macOS 在外部卷上生成的 ._ 元数据文件。",
        "若仍出现，请检查导出目录里是否有你手动放入的 IPA。",
      ],
      retryHelps: true,
    };
  }
  return null;
}
export function buildProblems(
  form: BuildForm,
  report: Report | null,
  desktop: boolean,
): string[] {
  const result: string[] = [];
  if (!desktop) result.push("请在 NCL Builder 桌面应用中执行构建。");
  if (!form.workspace.trim()) result.push("请选择 NCL 项目目录。");
  if (!form.config.trim()) result.push("请选择或创建构建配置。");
  if (!form.unsigned && !form.exportOptions.trim())
    result.push("请选择 IPA 开发导出配置。");
  if (!form.output.trim()) result.push("请选择构建产物目录。");
  if (!form.unsigned && form.team && !/^[A-Z0-9]{10}$/.test(form.team))
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
  if (value.unsigned !== undefined && typeof value.unsigned !== "boolean")
    throw new Error("未签名选项无效");
  result.unsigned = value.unsigned === true;
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
