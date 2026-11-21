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
  icon?: string;
  iconFit?: "fit" | "fill";
  iconBackground?: string;
  iconPadding?: number;
  testVersion?: string;
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
  forceCompile: boolean;
  quickBuild?: boolean;
}
type CompatibilityStage = "PASS" | "FAIL" | "SKIPPED" | "UNVERIFIED";
export interface ModCompatibility {
  id: string;
  name: string;
  version: string;
  dependencyStatus: "RESOLVED" | "UNSATISFIED" | "UNVERIFIED";
  buildStatus: "BUILD_PASS" | "TRANSFORMED" | "BLOCKED" | "UNVERIFIED";
  functionStatus: "UNVERIFIED";
  deviceStatus: "DEVICE_NOT_RUN";
  rules: string[];
  risks: AotCompatibility["findings"];
  riskCount: number;
  degradation: string[];
  relevantChecks: string[];
}

export interface AotCompatibility {
  modCount: number;
  fixes: number;
  warnings: number;
  blockers: number;
  findingGroups: number;
  mods?: ModCompatibility[];
  rootCause?: {
    category: string;
    confidence: "HIGH_CONFIDENCE" | "UNKNOWN";
    modId?: string;
    evidence: { line: string; frame?: string };
  };
  stages: Record<
    "static" | "transform" | "aot" | "startup" | "device",
    CompatibilityStage
  >;
  findings: {
    code: string;
    severity: "fix" | "warning" | "blocker";
    location?: string | null;
    renderer?: string;
    stage?: string;
    archive?: string;
    mod?: string;
    suggestion?: string;
    target: string;
    count: number;
  }[];
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
  compatibility?: AotCompatibility;
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
  stage?: string;
  config?: string;
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
  icon: "",
  iconFit: "fit",
  iconBackground: "transparent",
  iconPadding: 0,
  testVersion: "",
  resourceSelection: null,
  workspace: "",
  python: "",
  config: "",
  exportOptions: "",
  output: "",
  loader: "fabric",
  source: "",
  team: "",
  forceCompile: false,
  quickBuild: false,
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
  const has = (needle: string) => error.includes(needle);

  const isNativeImage = stage === "aot" || has("mcfao build: aot failed") ||
    has("Native Image stopped before producing an image");
  if (isNativeImage && (has("OutOfMemoryError: Java heap space") || has("The Native Image build process ran out of memory"))) {
    const heap = /-Xmx(\d+)g/.exec(error);
    const collector = /Native Image builder: (g1|parallel) GC/.exec(error)?.[1];
    const phase = /Native Image last completed phase: ([1-8])\/8/.exec(error);
    const phases = ["初始化", "可达性分析", "构建编译模型", "解析方法",
      "内联方法", "编译方法", "布置方法", "生成镜像"];
    const budget = heap ? `（堆上限 ${heap[1]} GiB）` : "";
    const progress = phase ? `最后完成的步骤为${phases[Number(phase[1]) - 1]}。` : "";
    const next = collector
      ? ["查看任务里的 Native Image 和 GC 日志，确认堆使用情况。", "可精简本次构建的内容，再重新编译。"]
      : ["用新版构建器重试。Fabric 编译现在默认使用 G1 回收器。"];
    return {
      title: "Java 25 原生编译堆耗尽",
      cause: `Native Image 的构建 JVM${budget}耗尽了 Java 堆。${progress}`,
      next,
      retryHelps: !collector,
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
  canPrepare = false,
): string[] {
  const result: string[] = [];
  if (
    form.testVersion?.trim() &&
    !/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(form.testVersion.trim())
  )
    result.push(
      "测试版本需为 1–64 位英文字母、数字、点、下划线或短横线，且以字母或数字开头。",
    );
  if (!desktop) result.push("请在 NCL Builder 桌面应用中执行构建。");
  if (!form.workspace.trim()) result.push("请选择 NCL 项目目录。");
  if (!form.config.trim() && !canPrepare)
    result.push("请验证正版账号并自动生成构建配置。");
  if (!form.unsigned && !form.exportOptions.trim())
    result.push("请选择 IPA 开发导出配置。");
  if (!form.output.trim()) result.push("请选择构建产物目录。");
  if (
    form.icon &&
    !/\.icon$/i.test(form.icon) &&
    !/\.(png|jpe?g|heic|heif|webp|gif|tiff?|bmp|svg|pdf|icns|ico)$/i.test(
      form.icon,
    )
  )
    result.push("图标需要 .icon 文档或受支持的图片格式。");
  if (!form.unsigned && form.team && !/^[A-Z0-9]{10}$/.test(form.team))
    result.push("Team ID 需要 10 位大写字母或数字。");
  if (form.loader === "fabric") {
    if (!form.source.trim()) result.push("请选择整合包或 Prism 实例。");
    if (!report || report.source !== form.source)
      result.push("请重新选择整合包，等待来源检查完成。");
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
    "team",
    "icon",
    "testVersion",
  ] as const) {
    if (
      value[key] !== undefined &&
      (typeof value[key] !== "string" || value[key].length > 4096)
    )
      throw new Error("构建设置字段无效");
    result[key] = value[key] ?? "";
  }
  if (value.iconFit !== undefined && !["fit", "fill"].includes(value.iconFit))
    throw new Error("图标缩放方式无效");
  result.iconFit = value.iconFit === "fill" ? "fill" : "fit";
  if (
    value.iconBackground !== undefined &&
    value.iconBackground !== "transparent" &&
    !/^#[0-9A-Fa-f]{6}$/.test(String(value.iconBackground))
  )
    throw new Error("图标背景色无效");
  result.iconBackground = value.iconBackground || "transparent";
  if (
    value.iconPadding !== undefined &&
    (!Number.isInteger(value.iconPadding) ||
      value.iconPadding < 0 ||
      value.iconPadding > 30)
  )
    throw new Error("图标留白无效");
  result.iconPadding = value.iconPadding ?? 0;
  if (value.unsigned !== undefined && typeof value.unsigned !== "boolean")
    throw new Error("未签名选项无效");
  result.unsigned = value.unsigned === true;
  if (value.quickBuild !== undefined && typeof value.quickBuild !== "boolean")
    throw new Error("快速构建选项无效");
  result.quickBuild = value.quickBuild === true;
  result.loader = value.loader === "vanilla" ? "vanilla" : "fabric";
  // The game source is a per-visit choice: a stored pack must never preselect
  // the next build. The field is accepted for older records and ignored.
  result.source = "";
  result.forceCompile = false;
  return result;
}
export function mergeJob(jobs: BuildJob[], next: BuildJob): BuildJob[] {
  return [next, ...jobs.filter((j) => j.id !== next.id)]
    .sort((a, b) => b.startedAt.localeCompare(a.startedAt))
    .slice(0, 40);
}
