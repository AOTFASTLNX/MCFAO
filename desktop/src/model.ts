export interface Finding {
  severity: "error" | "warning" | "info";
  code: string;
  message: string;
}
export interface Mod {
  id: string;
  version: string;
  path: string;
  environment: string;
  has_mixins: boolean;
  has_entrypoints: boolean;
  has_class_tweaker: boolean;
  has_language_adapters: boolean;
  nested_jar_count: number;
  bundled_native_count: number;
  aot_compatibility: "NOT_TESTED";
}
export interface Report {
  source: string;
  target_minecraft: string;
  status: "STATIC_PREFLIGHT_ONLY";
  source_type: string;
  pack_name?: string;
  pack_version?: string;
  fabric_loader_version?: string;
  manifest_files?: number;
  mods: Mod[];
  findings: Finding[];
  fatal: boolean;
  aot_ios_verified: false;
}
export interface Instance {
  id: string;
  name: string;
  importedAt: string;
  report: Report;
}
export interface Settings {
  workspace: string;
  python: string;
  config: string;
  output: string;
}
export interface Task {
  id: string;
  name: string;
  startedAt: string;
  state: "running" | "done" | "blocked" | "failed";
  lines: string[];
}
export interface EnvironmentCheck {
  name: string;
  status: "ready" | "missing" | "unavailable";
  detail: string;
}
export interface Environment {
  os: string;
  arch: string;
  checks: EnvironmentCheck[];
}
export const DEFAULT_SETTINGS: Settings = {
  workspace: "",
  python: "",
  config: "mcfao.local.json",
  output: "artifacts/desktop-preparation",
};
export const STORAGE_KEY = "fabricaot.desktop.v1";
const object = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === "object" && !Array.isArray(value);
function string(value: unknown, max = 4096): string {
  if (typeof value !== "string" || value.length > max)
    throw new Error("报告字段格式不正确或过长。");
  return value;
}
function count(value: unknown): number {
  if (value === undefined) return 0;
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0)
    throw new Error("报告中的数量无效。");
  return value;
}
export function parseReport(value: unknown): Report {
  if (
    !object(value) ||
    value.status !== "STATIC_PREFLIGHT_ONLY" ||
    typeof value.fatal !== "boolean" ||
    !Array.isArray(value.mods) ||
    !Array.isArray(value.findings) ||
    value.mods.length > 5000 ||
    value.findings.length > 50000
  ) {
    throw new Error("请选择 tools/preflight.py 生成的静态预检 JSON 报告。");
  }
  const findings: Finding[] = value.findings.map((f: unknown) => {
    if (
      !object(f) ||
      !["error", "warning", "info"].includes(String(f.severity))
    )
      throw new Error("报告中的诊断项无效。");
    return {
      severity: f.severity as Finding["severity"],
      code: string(f.code, 256),
      message: string(f.message, 16384),
    };
  });
  const mods: Mod[] = value.mods.map((m: unknown) => {
    if (!object(m)) throw new Error("报告中的 Mod 元数据无效。");
    return {
      id: string(m.id, 256),
      version: string(m.version, 256),
      path: string(m.path),
      environment: string(m.environment ?? "*", 64),
      has_mixins: m.has_mixins === true,
      has_entrypoints: m.has_entrypoints === true,
      has_class_tweaker: m.has_class_tweaker === true,
      has_language_adapters: m.has_language_adapters === true,
      nested_jar_count: count(m.nested_jar_count),
      bundled_native_count: count(m.bundled_native_count),
      aot_compatibility: "NOT_TESTED",
    };
  });
  return {
    source: string(value.source),
    target_minecraft: string(value.target_minecraft, 64),
    status: "STATIC_PREFLIGHT_ONLY",
    source_type: string(value.source_type, 64),
    mods,
    findings,
    fatal: value.fatal || findings.some((f) => f.severity === "error"),
    aot_ios_verified: false,
    ...(value.pack_name !== undefined && value.pack_name !== null
      ? { pack_name: string(value.pack_name, 256) }
      : {}),
    ...(value.pack_version !== undefined && value.pack_version !== null
      ? { pack_version: string(value.pack_version, 256) }
      : {}),
    ...(value.fabric_loader_version !== undefined
      ? { fabric_loader_version: string(value.fabric_loader_version, 128) }
      : {}),
    ...(value.manifest_files !== undefined
      ? { manifest_files: count(value.manifest_files) }
      : {}),
  };
}
export function sourceName(report: Report): string {
  const filename =
    report.source
      .replaceAll(String.fromCharCode(92), "/")
      .split("/")
      .filter(Boolean)
      .pop() ?? "";
  return report.pack_name || filename.replace(/\.mrpack$/i, "") || "未命名实例";
}
export function makeInstance(report: Report, previous?: Instance): Instance {
  return {
    id: previous?.id ?? crypto.randomUUID(),
    name: sourceName(report),
    importedAt: new Date().toISOString(),
    report,
  };
}
export function upsertInstance(
  instances: Instance[],
  instance: Instance,
): Instance[] {
  return [
    instance,
    ...instances.filter((i) => i.report.source !== instance.report.source),
  ].slice(0, 100);
}
export function parseSavedState(raw: string | null): {
  instances: Instance[];
  settings: Settings;
} {
  if (!raw) return { instances: [], settings: DEFAULT_SETTINGS };
  const data: unknown = JSON.parse(raw);
  if (
    !object(data) ||
    !Array.isArray(data.instances) ||
    data.instances.length > 100 ||
    !object(data.settings)
  )
    throw new Error("本地记录损坏。");
  const instances = data.instances.map((row: unknown) => {
    if (!object(row)) throw new Error("本地实例记录损坏。");
    const date = string(row.importedAt, 64);
    if (!Number.isFinite(Date.parse(date)))
      throw new Error("本地记录时间无效。");
    return {
      id: string(row.id, 128),
      name: string(row.name, 256),
      importedAt: date,
      report: parseReport(row.report),
    };
  });
  const settings = Object.fromEntries(
    Object.keys(DEFAULT_SETTINGS).map((key) => [
      key,
      string((data.settings as Record<string, unknown>)[key] ?? ""),
    ]),
  ) as unknown as Settings;
  return { instances, settings };
}
export function quoteArgument(value: string, windows = false): string {
  if (/[\0\r\n]/.test(value)) throw new Error("路径不能包含换行或空字符。");
  return windows
    ? "'" + value.replaceAll("'", "''") + "'"
    : "'" + value.replaceAll("'", "'\\''") + "'";
}
export function prepareCommand(
  settings: Settings,
  mods: string,
  windows = false,
): string {
  if (
    ![settings.workspace, settings.config, settings.output, mods].every((v) =>
      v.trim(),
    )
  )
    throw new Error("请填写项目目录、构建配置、Mod 目录和输出目录。");
  const path =
    settings.workspace
      .replaceAll(String.fromCharCode(92), "/")
      .replace(/\/+$/, "") + "/tools/mcfao.py";
  const argv = [
    settings.python || (windows ? "python" : "python3"),
    path,
    "build",
    "--version",
    "26.1.2",
    "--loader",
    "fabric",
    "--target",
    "ios-arm64",
    "--config",
    settings.config,
    "--mods",
    mods,
    "--output",
    settings.output,
    "--prepare-only",
  ];
  return (
    (windows ? "& " : "") + argv.map((v) => quoteArgument(v, windows)).join(" ")
  );
}
export const findingLabels: Record<string, string> = {
  LOADER_VERSION_UNVERIFIED: "Loader 版本待核验",
  REMOTE_MOD_METADATA_NOT_FETCHED: "远程 Mod 尚未下载",
  MIXIN_REQUIRES_AOT_WORK: "Mixin 需要构建期转换",
  CLASS_TWEAKER_REQUIRES_AOT_WORK: "需要访问修改适配",
  WRONG_MC_VERSION: "Minecraft 版本不匹配",
  NOT_FABRIC: "缺少 Fabric Loader",
  OTHER_LOADER: "不支持的加载器",
  NO_MOD_DIRECTORY: "未发现 Mod 目录",
  NO_PRISM_META: "缺少 Prism 实例元数据",
  NOT_FOUND: "找不到源文件",
  NATIVE_LIBRARY_REQUIRES_PORT: "原生库需要移植",
  NESTED_JARS_REQUIRE_RESOLUTION: "嵌套依赖需要解析",
  LANGUAGE_ADAPTER_REQUIRES_SUPPORT: "语言适配器待核验",
  SERVER_MOD: "仅服务端 Mod",
};
