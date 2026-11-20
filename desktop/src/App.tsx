import { BuildSetup, setupIsRunning, useSetupProgress } from "./BuildSetup";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  ArrowRight,
  ArrowUpRight,
  Box,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  Clock3,
  Cpu,
  Download,
  FileCheck2,
  FileJson2,
  FolderOpen,
  Hammer,
  HardDrive,
  History,
  Layers3,
  LoaderCircle,
  Monitor,
  Moon,
  Package,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Smartphone,
  Square,
  Sun,
  Terminal,
  TriangleAlert,
  X,
} from "lucide-react";
import {
  DEFAULT_SETTINGS,
  STORAGE_KEY,
  parseReport,
  parseSavedState,
  type Report,
} from "./model";
import {
  chooseIcon,
  choosePath,
  defaultWorkspace,
  inspectSource,
  native,
  pickSource,
  revealPath,
  saveDocument,
  workbench,
} from "./bridge";
import {
  FORM_KEY,
  buildProblems,
  configurationFields,
  defaultForm,
  explainError,
  isActive,
  mergeJob,
  restoreForm,
  stageName,
  stages,
  type AotCompatibility,
  type Bootstrap,
  type BuildForm,
  type BuildJob,
  type Checks,
} from "./workflow";
import ModList from "./ModList";
import ResourceManager from "./ResourceManager";
import { LogView } from "./LogView";
import { SelectMenu } from "./SelectMenu";
import {
  ACCENT_KEY,
  accentOptions,
  applyAccent,
  applyTheme,
  getSystemAccent,
  readAccentPreference,
  readThemePreference,
  resolveTheme,
  syncWindowTheme,
  systemPrefersDark,
  THEME_KEY,
  type ResolvedTheme,
  type ThemePreference,
} from "./theme";
import {
  BUILDER_NAME,
  IOS_APP_NAME,
  PRODUCT_NAME,
  PRODUCT_SHORT_NAME,
  PRODUCT_VERSION,
} from "./version";
import {
  LEGACY_FORM_KEY,
  LEGACY_STORAGE_KEY,
  migrateLegacyKeys,
  readWithLegacy,
} from "./storage";
import { NativeDependencies, DependencyTask } from "./NativeDependencies";
import { jobStateName, type DependencyInventory } from "./workflow";
import { StorageManager } from "./StorageManager";
import {
  StorageChangeDialog,
  type StorageChangePlan,
  type StoragePolicy,
} from "./StorageChangeDialog";
import { QuickStorageDirectory } from "./QuickStorageDirectory";
import { AccountPanel, accountIsVerified, useAccount } from "./Account";
import { storageFormPatch } from "./onboarding";
import {
  useSlidingIndicator,
  useStepContent,
  usePageCrossfade,
  useSelectionPulse,
  formatDuration,
} from "./motion";
import {
  AnimatedNumber,
  MotionIndicator,
  Reveal,
  StatusMark,
  StepBody,
} from "./MotionPrimitives";
import {
  formatBytes as size,
  unifiedStoragePaths,
  type StoragePlan,
} from "./storageManagement";
import { dragVerdict, dropMessage } from "./dropTarget";
type Page = "builder" | "history" | "environment" | "storage" | "settings";

const pages = [
  ["builder", "构建 IPA", Hammer],
  ["history", "构建记录", History],
  ["environment", "环境与资源", Cpu],
  ["storage", "存储管理", HardDrive],
  ["settings", "设置", Settings2],
] as const;

const date = (s: string) =>
  new Date(s).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
const basename = (s: string) =>
  s.replaceAll(String.fromCharCode(92), "/").split("/").filter(Boolean).pop() ||
  s;
function initial() {
  const store = typeof window === "undefined" ? null : window.localStorage;
  migrateLegacyKeys(store);
  try {
    const old = parseSavedState(
      readWithLegacy(store, STORAGE_KEY, LEGACY_STORAGE_KEY),
    );
    const savedForm = readWithLegacy(store, FORM_KEY, LEGACY_FORM_KEY);
    const restored = savedForm
      ? restoreForm(savedForm)
      : {
          ...defaultForm,
          workspace: old.settings.workspace,
          python: old.settings.python,
        };
    return {
      // A game source is picked again on every entry to the builder; only the
      // machine paths and signing choices survive a restart.
      form: { ...restored, source: "", resourceSelection: null },
      error: "",
    };
  } catch {
    return {
      form: { ...defaultForm },
      error: "本地记录无法读取，自动保存已暂停。请先在设置中导出原始记录。",
    };
  }
}
function Pill({ children, tone = "" }: { children: ReactNode; tone?: string }) {
  return (
    <span className={"pill " + tone}>
      <span className="dot" />
      {children}
    </span>
  );
}
function Note({
  children,
  error = false,
}: {
  children: ReactNode;
  error?: boolean;
}) {
  return (
    <div className={"note " + (error ? "error" : "")}>
      <CircleAlert size={17} aria-hidden="true" />
      <div>{children}</div>
    </div>
  );
}

const compatibilityStages = [
  ["static", "静态检查"],
  ["transform", "Fabric 转换"],
  ["aot", "AOT 产物"],
  ["startup", "启动"],
  ["device", "真机"],
] as const;
const compatibilityStatus = {
  PASS: "通过",
  FAIL: "失败",
  SKIPPED: "未执行",
  UNVERIFIED: "待验证",
} as const;
const compatibilitySeverity = {
  blocker: "阻塞",
  warning: "警告",
  fix: "自动修复",
};
const compatibilityReasons: Record<string, string> = {
  FABRIC_DEPENDENCIES: "Fabric 依赖未满足",
  FABRIC_TRANSFORMATION: "Fabric 转换失败",
  MIXIN_TARGET_UNAVAILABLE: "Mixin 目标不可用",
  MIXIN_ACCESSOR_UNVERIFIED: "Mixin 访问器未验证",
  MIXIN_HELPER_UNAVAILABLE: "Mixin 辅助类型不可用",
  GENERATED_CLASS_UNAVAILABLE: "生成类不可用",
  FABRIC_RUNTIME_RESIDUE: "Fabric 运行时行为待验证",
  BYTECODE_ADAPTATION: "静态字节码转换",
  CONFIG_NO_PUBLIC_NOARG: "配置类型缺少公开无参构造器",
  TYPED_GSON_CONFIG: "已注册配置构造器和字段",
  METAL_REFERENCE_ON_GL41: "GL41 引用了原生 Metal 类型",
  METAL_CLASS_ON_GL41: "GL41 类路径包含原生 Metal 类型",
  MISSING_REQUIRED_TYPE: "缺少必需类型",
  MISSING_TYPE: "符号引用的类型缺失",
  LWJGL_MEMBER_MISSING: "LWJGL 方法或字段缺失",
  OPENGL_AFTER_41: "调用超出 GL 4.1 的 API",
  RESOURCE_METADATA: "已注册静态资源",
  RESOURCE_RETAINED: "已保留静态资源",
  RESOURCE_AMBIGUOUS: "资源路径冲突",
  RESOURCE_NOT_ON_CLASSPATH: "资源缺失",
  DYNAMIC_RESOURCE: "动态资源路径待验证",
  MOD_NATIVE_METHOD: "Mod 包含原生方法",
  NATIVE_LINK_UNSUPPORTED: "原生运行库入口尚未实现",
  NATIVE_LIBRARY_LOAD: "动态原生库加载待验证",
  RUNTIME_CLASS_DEFINITION: "运行时定义类待验证",
  REFLECTION_CALL: "反射调用待验证",
  REFLECTION_METADATA_UNRESOLVED: "反射元数据目标未解析",
  PROXY_CALL: "动态代理待验证",
  SERIALIZATION_CALL: "Java 序列化待验证",
};

function CompatibilitySummary({ report }: { report: AotCompatibility }) {
  return (
    <section className="compatibility-summary" aria-label="AOT 兼容性">
      <div role="status">
        <strong>AOT 兼容性</strong>
        <p>
          {report.modCount} 个 Mod · {report.fixes} 项自动修复 ·{" "}
          {report.warnings} 条警告 · {report.blockers} 个阻塞
        </p>
        <p>
          {compatibilityStages
            .map(
              ([key, label]) =>
                `${label} ${compatibilityStatus[report.stages[key]]}`,
            )
            .join(" · ")}
        </p>
      </div>
      {!!report.findings.length && (
        <details open={report.blockers ? true : undefined}>
          <summary>查看兼容性诊断</summary>
          <ul>
            {report.findings.map((finding, index) => (
              <li key={finding.code + index}>
                {compatibilitySeverity[finding.severity]} ·{" "}
                {compatibilityReasons[finding.code] ?? finding.code} ·{" "}
                {finding.target}
                {finding.location && ` · ${finding.location}`}
                {finding.count > 1 && ` · ${finding.count} 处`}
              </li>
            ))}
          </ul>
          {report.findingGroups > report.findings.length && (
            <p>更多条目见构建报告与日志。</p>
          )}
        </details>
      )}
    </section>
  );
}

function JobErrorDetail({ error, stage }: { error: string; stage: string }) {
  const explained = explainError(error, stage);
  if (!explained) return <pre>{error}</pre>;
  return (
    <>
      <p className="job-error-cause">{explained.cause}</p>
      <ul className="job-error-next">
        {explained.next.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ul>
      {!explained.retryHelps && (
        <p className="job-error-retry">
          直接重试会重现同一失败，请先处理上面的条件。
        </p>
      )}
      <details className="job-error-raw">
        <summary>原始诊断输出</summary>
        <pre>{error}</pre>
      </details>
    </>
  );
}

function JobElapsed({ job }: { job: BuildJob }) {
  const [now, setNow] = useState(() => Date.now());
  const running = isActive(job);
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [running, job.id]);
  const started = Date.parse(job.startedAt);
  if (!Number.isFinite(started)) return null;
  const ended = job.finishedAt ? Date.parse(job.finishedAt) : now;
  const elapsed = Math.max(0, ended - started);
  return (
    <span className="job-elapsed" data-live={running ? "true" : "false"}>
      {running ? "已用时 " : "用时 "}
      {formatDuration(elapsed)}
    </span>
  );
}

function PathField({
  label,
  value,
  onChange,
  directory = false,
  hint,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  directory?: boolean;
  hint?: string;
}) {
  const [error, setError] = useState("");
  return (
    <div className="field">
      <label>
        <span>{label}</span>
        <span className="path-input">
          <input
            value={value}
            onChange={(e) => onChange(e.target.value)}
            spellCheck={false}
            placeholder={directory ? "选择文件夹" : "选择文件"}
          />
          <button
            className="path-picker"
            disabled={!native}
            aria-label={"选择" + label}
            onClick={async () => {
              try {
                const p = await choosePath("选择" + label, directory);
                if (p) onChange(p);
                setError("");
              } catch (e) {
                setError(String(e));
              }
            }}
          >
            <FolderOpen size={17} />
          </button>
        </span>
      </label>
      {hint && <small>{hint}</small>}
      {error && <small className="red">{error}</small>}
    </div>
  );
}

const iconBackgrounds = [
  { value: "transparent", label: "透明" },
  { value: "#FFFFFF", label: "白色" },
  { value: "#000000", label: "黑色" },
  { value: "#F5F5F7", label: "浅灰" },
];
function backgroundOptions(current: string) {
  // A restored setting may hold a custom colour; show it rather than
  // silently displaying the first preset.
  return iconBackgrounds.some((option) => option.value === current)
    ? iconBackgrounds
    : [...iconBackgrounds, { value: current, label: current }];
}

function AppIconField({
  form,
  update,
  disabled,
  locked,
}: {
  form: BuildForm;
  update: (patch: Partial<BuildForm>) => void;
  disabled: boolean;
  locked: boolean;
}) {
  const [preview, setPreview] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const icon = form.icon || "";
  const isDocument = icon.toLowerCase().endsWith(".icon");
  useEffect(() => {
    if (!icon || !native || !form.workspace) {
      setPreview("");
      return;
    }
    let disposed = false;
    const timer = window.setTimeout(() => {
      setLoading(true);
      workbench<{ data: string; path: string }>(
        form,
        "icon-preview",
        undefined,
        {
          icon,
          fit: form.iconFit || "fit",
          background: form.iconBackground || "transparent",
          padding: form.iconPadding ?? 0,
        },
      )
        .then((r) => {
          if (disposed) return;
          setPreview(r.data);
          setError("");
        })
        .catch((e) => {
          if (!disposed) setError(String(e));
        })
        .finally(() => {
          if (!disposed) setLoading(false);
        });
    }, 240);
    return () => {
      disposed = true;
      window.clearTimeout(timer);
    };
  }, [
    icon,
    form.workspace,
    form.iconFit,
    form.iconBackground,
    form.iconPadding,
  ]);
  const choose = async (directory: boolean) => {
    try {
      const path = await chooseIcon(directory);
      if (path) {
        update({ icon: path });
        setError("");
      }
    } catch (e) {
      setError(String(e));
    }
  };
  return (
    <div className="app-icon-field">
      <div className="app-icon-heading">
        <div>
          <strong>应用图标</strong>
          <small>
            使用自己的图标；支持 .icon 文档与
            PNG、JPEG、HEIC、WebP、GIF、TIFF、BMP、SVG、PDF、ICNS、ICO。
          </small>
        </div>
        <span className="app-icon-preview" data-loading={loading}>
          {preview ? (
            <img src={preview} alt="应用图标预览" />
          ) : (
            <Package size={30} aria-hidden="true" />
          )}
        </span>
      </div>
      <div className="field">
        <label>
          <span>图标文件</span>
          <span className="path-input">
            <input
              value={icon}
              onChange={(e) => update({ icon: e.target.value })}
              spellCheck={false}
              disabled={locked}
              placeholder="选择 .icon 文档或图片"
            />
            <button
              className="path-picker"
              disabled={disabled}
              aria-label="选择图标图片"
              onClick={() => void choose(false)}
            >
              <FolderOpen size={17} />
            </button>
            <button
              className="path-picker"
              disabled={disabled}
              aria-label="选择图标文档"
              onClick={() => void choose(true)}
            >
              <Box size={17} />
            </button>
          </span>
        </label>
        <small>
          {isDocument
            ? "Icon Composer 文档会保留浅色、深色与透明等系统外观。"
            : "非方形图片默认完整保留并居中，空白处透明。"}
        </small>
        {icon && (
          <button
            className="text-button"
            disabled={locked}
            onClick={() => update({ icon: "" })}
          >
            使用系统默认图标
          </button>
        )}
        {error && <small className="red">{error}</small>}
      </div>
      {icon && !isDocument && (
        <div className="app-icon-options">
          <label>
            <span>图片适配</span>
            <SelectMenu
              label="图标图片适配"
              value={form.iconFit || "fit"}
              onChange={(v) => update({ iconFit: v as "fit" | "fill" })}
              options={[
                { value: "fit", label: "完整保留" },
                { value: "fill", label: "填满裁切" },
              ]}
              disabled={locked}
            />
          </label>
          <label>
            <span>背景</span>
            <SelectMenu
              label="图标背景"
              value={form.iconBackground || "transparent"}
              onChange={(v) => update({ iconBackground: v })}
              options={backgroundOptions(
                form.iconBackground || "transparent",
              ).map((option) => ({
                value: option.value,
                label: option.label,
              }))}
              disabled={locked}
            />
          </label>
          <label>
            <span>留白 {form.iconPadding ?? 0}%</span>
            <input
              type="range"
              min={0}
              max={30}
              step={1}
              value={form.iconPadding ?? 0}
              disabled={locked}
              aria-label="图标留白"
              onChange={(e) => update({ iconPadding: Number(e.target.value) })}
            />
          </label>
        </div>
      )}
    </div>
  );
}
function CheckList({ checks }: { checks: Checks }) {
  return (
    <div className="check-list">
      {checks.checks.map((c) => (
        <div className={"check-row " + c.status} key={c.name}>
          <StatusMark state={c.status} size={19}>
            {c.status === "ready" ? (
              <CheckCircle2 size={19} />
            ) : c.status === "warning" ? (
              <TriangleAlert size={19} />
            ) : (
              <CircleAlert size={19} />
            )}
          </StatusMark>
          <div>
            <strong>{c.name}</strong>
            <p>{c.detail}</p>
          </div>
          <span>
            {c.status === "ready"
              ? "就绪"
              : c.status === "warning"
                ? "警告"
                : "需处理"}
          </span>
        </div>
      ))}
    </div>
  );
}

function ExclusionDialog({
  challenge,
  busy,
  onResolve,
}: {
  challenge: NonNullable<BuildJob["exclusionChallenge"]> | null;
  busy: boolean;
  onResolve: (accepted: boolean) => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (challenge && !dialog.open) dialog.showModal();
    if (!challenge && dialog.open) dialog.close();
  }, [challenge]);
  if (!challenge) return null;
  return (
    <dialog
      ref={ref}
      className="confirm-dialog exclusion-dialog"
      aria-labelledby="exclusion-title"
      aria-describedby="exclusion-summary"
      onCancel={(event) => event.preventDefault()}
    >
      <span className="eyebrow">FABRIC · 静态 AOT 检查</span>
      <h2 id="exclusion-title">发现无法静态转换的 Mod</h2>
      <p id="exclusion-summary">
        {challenge.summary} 这些项目的功能不会进入本次构建；原整合包保持不变。
      </p>
      <div className="exclusion-list" aria-label="将排除的 Mod">
        {challenge.mods.map((mod) => (
          <article className="exclusion-item" key={mod.file}>
            <div className="exclusion-item-heading">
              <strong>{mod.name}</strong>
              {mod.version && <span>{mod.version}</span>}
            </div>
            <code>{mod.file}</code>
            <ul>
              {mod.reasons.map((reason, index) => (
                <li key={index}>{reason}</li>
              ))}
            </ul>
          </article>
        ))}
      </div>
      <p className="exclusion-note">
        确认后将从独立的暂存副本移除上述文件和依赖它们的
        Mod，再重新执行转换。若剩余项目仍有阻断项，会再次提示。
      </p>
      <div className="button-line">
        <button
          className="secondary"
          disabled={busy}
          onClick={() => onResolve(false)}
        >
          停止构建
        </button>
        <button
          className="primary"
          disabled={busy}
          onClick={() => onResolve(true)}
        >
          {busy ? "正在处理…" : "排除并继续"}
        </button>
      </div>
    </dialog>
  );
}

export default function App() {
  const { account } = useAccount();
  const localTesting = account.loginRequired === false;
  const verifiedAccount = accountIsVerified(account);
  const [saved] = useState(initial);
  const [theme, setTheme] = useState<ThemePreference>(readThemePreference);
  const [accent, setAccent] = useState(readAccentPreference);
  const [systemAccent, setSystemAccent] = useState<string | null>(null);
  const [systemDark, setSystemDark] = useState(() =>
    systemPrefersDark(
      typeof window === "undefined"
        ? null
        : window.matchMedia("(prefers-color-scheme: dark)"),
    ),
  );
  const resolvedTheme: ResolvedTheme = resolveTheme(theme, systemDark);
  const [form, setForm] = useState(saved.form);
  const [storagePaths, setStoragePaths] = useState({
    cache: "",
    builds: "",
    jobs: "",
    rust: "",
  });
  const [storageStatus, setStorageStatus] = useState("");
  const [storageChange, setStorageChange] = useState<StorageChangePlan | null>(
    null,
  );
  const [setup, setSetup] = useState<import("./workflow").SetupState | null>(
    null,
  );
  const pendingBuild = useRef<BuildForm | null>(null);
  const [storageIssue, setStorageIssue] = useState(saved.error);
  const [page, setPage] = useState<Page>("builder");
  const [step, setStep] = useState(0);
  const [checkedSteps, setCheckedSteps] = useState<number[]>([]);
  const [report, setReport] = useState<Report | null>(null);
  const [checks, setChecks] = useState<Checks | null>(null);
  const [dependencies, setDependencies] = useState<DependencyInventory | null>(
    null,
  );
  const [dependencyError, setDependencyError] = useState("");
  const [checkingDependencies, setCheckingDependencies] = useState(false);
  const [dependencyRevision, setDependencyRevision] = useState(0);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [jobs, setJobs] = useState<BuildJob[]>([]);
  const [selected, setSelected] = useState("");
  const [busy, setBusy] = useState("");
  const [drag, setDrag] = useState<"none" | "accepted" | "rejected">("none");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [details, setDetails] = useState(false);
  const [search, setSearch] = useState("");
  const [follow, setFollow] = useState(true);
  const [userScrolled, setUserScrolled] = useState(false);
  const [pollError, setPollError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [reset, setReset] = useState(false);
  const [storage, setStorage] = useState<StoragePlan | null>(null);
  const [storageDone, setStorageDone] = useState("");
  useEffect(() => {
    setStorage(null);
    setStorageDone("");
    setStorageStatus("");
  }, [form.workspace]);
  const pendingExclusionJob = jobs.find(
    (item) => item.state === "awaiting-exclusions" && item.exclusionChallenge,
  );
  const lock = useRef(false);
  const formRef = useRef(form);
  formRef.current = form;
  const end = useRef<HTMLDivElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const active = jobs.find((j) => isActive(j));
  const setupRunning = setupIsRunning(setup);
  const canPrepare = native && (localTesting || verifiedAccount);
  const job = jobs.find((j) => j.id === selected) ?? active ?? jobs[0];
  const activeBuildReason = active
    ? "有构建任务正在进行，完成或取消后才能继续。"
    : "";
  const blockedReason = activeBuildReason || (setupRunning
    ? "正在准备构建环境。"
    : !form.config
      ? "构建环境尚未准备。完成上方的自动准备后即可检测。"
      : "");
  const controlReason = !native
    ? "浏览器预览不能执行本地构建，请打开 NCL Builder 桌面应用。"
    : busy
      ? `${busy}，请等待完成。`
      : blockedReason;
  const currentReport = report?.source === form.source ? report : null;
  const steps =
    form.loader === "fabric"
      ? ["游戏内容", "资源管理", "构建环境", "开发签名", "确认构建"]
      : ["游戏内容", "构建环境", "开发签名", "确认构建"];
  const environmentStep = form.loader === "fabric" ? 2 : 1;
  const reviewStep = steps.length - 1;
  const stepView = useStepContent(step);
  const stepper = useSlidingIndicator<HTMLDivElement>(step);
  const { containerRef: stepperRef } = stepper;
  const stepScrollRef = useRef<HTMLDivElement>(null);
  const wizardFooterRef = useRef<HTMLElement>(null);
  const pageIndex = pages.findIndex(([id]) => id === page);
  const sidebar = useSlidingIndicator<HTMLElement>(pageIndex);
  const pageView = usePageCrossfade(page);
  const visiblePage = pageView.page;
  const loaderMoving = useSelectionPulse(form.loader);
  const visibleStep = stepView.phase === "idle" ? step : stepView.step;
  useLayoutEffect(() => {
    const scroll = stepScrollRef.current;
    const top = stepperRef.current;
    const bottom = wizardFooterRef.current;
    if (visiblePage !== "builder" || !scroll || !top || !bottom) return;

    const updateInsets = () => {
      scroll.style.setProperty(
        "--stepper-height",
        `${top.getBoundingClientRect().height}px`,
      );
      scroll.style.setProperty(
        "--wizard-footer-height",
        `${bottom.getBoundingClientRect().height}px`,
      );
    };
    updateInsets();
    const observer = new ResizeObserver(updateInsets);
    observer.observe(top);
    observer.observe(bottom);
    return () => observer.disconnect();
  }, [visiblePage, stepperRef]);

  useLayoutEffect(() => {
    const scroll = stepScrollRef.current;
    if (scroll) scroll.scrollTop = 0;
  }, [stepView.step]);

  function goToStep(target: number) {
    const next = Math.max(0, Math.min(steps.length - 1, target));
    if (next === step) return;
    if (next > step && stepGate(step))
      setCheckedSteps((old) => (old.includes(step) ? old : [...old, step]));
    setStep(next);
  }
  // A step only reads as completed after its own gate has been satisfied and
  // the user has moved past it. Going back does not erase that fact, but a
  // later edit that invalidates the gate does.
  const stepGate = (index: number) =>
    index === 0
      ? form.loader === "vanilla" || (!!currentReport && !currentReport.fatal)
      : form.loader === "fabric" && index === 1
        ? resourceReady &&
          !!currentReport?.resources?.some(
            (r) =>
              r.category === "mods" &&
              r.path.toLowerCase().endsWith(".jar") &&
              form.resourceSelection?.included.includes(r.id),
          )
        : index === environmentStep
          ? !!form.workspace && !!form.output && (!!form.config || canPrepare)
          : true;
  useEffect(() => {
    setCheckedSteps((old) => old.filter((index) => stepGate(index)));
    // stepGate is derived from these inputs; listing them keeps the check in
    // sync when a source, resource choice or path is edited.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    canPrepare,
    form.loader,
    form.source,
    form.resourceSelection,
    form.workspace,
    form.config,
    form.output,
    report,
  ]);
  const resourceReady =
    !!currentReport?.resources &&
    form.resourceSelection?.source === form.source &&
    form.resourceSelection?.fingerprint === currentReport.resources_fingerprint;
  const problems = buildProblems(form, report, native, canPrepare);
  const dependencyJob = jobs.find(
    (j) => j.kind === "dependencies" && j.request.config === form.config,
  );
  useEffect(() => {
    setDependencies(null);
    setDependencyError("");
    if (!native || !form.config || !form.workspace) return;
    let stopped = false;
    setCheckingDependencies(true);
    const timer = setTimeout(() => {
      void workbench<DependencyInventory>(formRef.current, "dependencies")
        .then((result) => {
          if (!stopped) setDependencies(result);
        })
        .catch((e) => {
          if (!stopped) setDependencyError(String(e));
        })
        .finally(() => {
          if (!stopped) setCheckingDependencies(false);
        });
    }, 300);
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [form.workspace, form.config, dependencyRevision, dependencyJob?.state]);
  useEffect(() => {
    if (dependencyJob?.state === "succeeded" && dependencyJob.configFields) {
      setFields(dependencyJob.configFields);
      setChecks(null);
    }
  }, [dependencyJob?.id, dependencyJob?.state]);
  async function rebuildDependencies(keys: string[]) {
    if (active) return;
    await attempt("正在创建依赖库重建任务", async () => {
      const next = await workbench<BuildJob>(
        { ...form, kind: "dependencies", dependencyKeys: keys },
        "start",
      );
      setJobs((old) => mergeJob(old, next));
      setSelected(next.id);
      setRefresh((v) => v + 1);
      setPage("environment");
    });
  }
  async function cancelDependencies(target: BuildJob) {
    await attempt("正在取消依赖库重建", async () => {
      const next = await workbench<BuildJob>(form, "cancel", target.id);
      setJobs((old) => mergeJob(old, next));
      setRefresh((v) => v + 1);
    });
  }
  useEffect(() => {
    applyTheme(resolvedTheme);
    void syncWindowTheme(resolvedTheme);
  }, [resolvedTheme]);
  useEffect(() => {
    void getSystemAccent().then(setSystemAccent);
  }, []);
  useEffect(() => {
    applyAccent(accent, systemAccent, resolvedTheme);
  }, [accent, systemAccent, resolvedTheme]);
  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const update = () => setSystemDark(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  function chooseTheme(next: ThemePreference) {
    setTheme(next);
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch {
      // A blocked storage must not prevent the current session from switching.
    }
  }
  function chooseAccent(next: string) {
    setAccent(next);
    try {
      localStorage.setItem(ACCENT_KEY, next);
    } catch {
      // A blocked storage must not prevent the current session from switching.
    }
  }
  function update(patch: Partial<BuildForm>) {
    setForm((f) => ({
      ...f,
      ...patch,
      ...(patch.source !== undefined || patch.loader !== undefined
        ? {
            forceCompile: false,
            resourceSelection:
              (patch.source !== undefined && patch.source !== f.source) ||
              (patch.loader !== undefined && patch.loader !== f.loader)
                ? null
                : f.resourceSelection,
          }
        : {}),
    }));
    if (
      [
        "workspace",
        "python",
        "config",
        "team",
        "exportOptions",
        "unsigned",
        "output",
      ].some((k) => k in patch)
    )
      setChecks(null);
    setError("");
  }
  useSetupProgress(formRef, setup, setSetup);
  async function loadStorage() {
    await attempt("正在统计磁盘占用", async () => {
      const plan = await workbench<StoragePlan>(
        formRef.current,
        "storage-plan",
      );
      setStorage(plan);
      setStorageDone("");
    });
  }
  async function resetStorageDirectories() {
    await attempt("正在重置目录设置", async () => {
      const result = await workbench<{
        ready: boolean;
        storage: typeof storagePaths;
      }>(formRef.current, "reset-storage");
      setStoragePaths(result.storage);
      update({ output: result.storage.builds });
      setStorage(null);
      setStorageDone("");
      setStorageStatus(
        "已恢复默认目录设置，已有文件保留原位。" +
          (result.ready
            ? "空间预检通过。"
            : "默认目录剩余空间不足，请更换目录后再构建。"),
      );
    });
  }
  async function quickStorageDirectory() {
    await attempt("正在选择储存目录", async () => {
      const directory = await choosePath("选择统一储存目录", true);
      if (!directory) return;
      const paths = unifiedStoragePaths(directory);
      setBusy("正在统计已有文件");
      const plan = await workbench<StorageChangePlan>(
        formRef.current,
        "storage-change-plan",
        undefined,
        { paths },
      );
      setStorageChange(plan);
    });
  }
  async function applyStorageChange(policy: StoragePolicy) {
    if (!storageChange) return;
    const plan = storageChange;
    await attempt(
      policy === "migrate"
        ? "正在迁移并校验文件"
        : policy === "delete"
          ? "正在删除已有文件"
          : "正在保存储存设置",
      async () => {
        const result = await workbench<{
          ready: boolean;
          warnings?: string[];
          pathMappings?: Record<string, string>;
        }>(formRef.current, "storage-change-apply", undefined, {
          paths: plan.paths,
          policy,
          token: plan.token,
        });
        const patch = storageFormPatch(
          formRef.current,
          plan.paths.builds,
          result.pathMappings,
        );
        setStoragePaths(plan.paths);
        update(patch);
        setStorage(null);
        setStorageDone("");
        setStorageChange(null);
        const outcome = {
          keep: "已有文件保留原位。",
          migrate: "已有文件已迁移并完成校验。",
          delete: "已处理原目录内的文件。",
        }[policy];
        setStorageStatus(
          "储存设置已更新。" +
            outcome +
            (result.ready
              ? "空间预检通过。"
              : "剩余空间不足，请更换目录后再构建。") +
            (result.warnings?.length
              ? "部分原文件已保留：" + result.warnings.join("；")
              : ""),
        );
        workbench<BuildJob[]>(formRef.current, "history")
          .then(setJobs)
          .catch((e) => setPollError(String(e)));
      },
    );
  }
  async function cleanStorage(groups: string[]) {
    await attempt("正在清理", async () => {
      const result = await workbench<{ freedBytes: number }>(
        formRef.current,
        "storage-clean",
        undefined,
        { groups, keepBuilds: 2 },
      );
      setStorageDone("已释放 " + size(result.freedBytes));
      setNotice("已释放 " + size(result.freedBytes));
      setStorage(null);
      setStorage(await workbench<StoragePlan>(formRef.current, "storage-plan"));
    });
  }
  async function attempt<T>(
    label: string,
    fn: () => Promise<T>,
  ): Promise<T | undefined> {
    if (lock.current) return;
    lock.current = true;
    setBusy(label);
    setError("");
    setNotice("");
    try {
      return await fn();
    } catch (e) {
      setError(String(e).replace(/^Error: /, ""));
    } finally {
      lock.current = false;
      setBusy("");
    }
  }
  const remember = useCallback((value: unknown) => {
    const r = parseReport(value);
    setReport(r);
    setForm((f) => ({
      ...f,
      resourceSelection:
        r.resources && r.resources_fingerprint
          ? f.resourceSelection?.source === r.source &&
            f.resourceSelection.fingerprint === r.resources_fingerprint
            ? f.resourceSelection
            : {
                source: r.source,
                fingerprint: r.resources_fingerprint,
                included: r.resources
                  .filter((item) => item.default_selected)
                  .map((item) => item.id),
              }
          : null,
    }));
    return r;
  }, []);
  async function inspect(source: string) {
    await attempt("正在检查游戏内容", async () => {
      const r = await inspectSource(source, formRef.current.python);
      return remember(r.report);
    });
  }
  const load = useCallback(async (path: string) => {
    if (!native || !path) return;
    const b = await workbench<Bootstrap>(
      { ...formRef.current, workspace: path },
      "bootstrap",
    );
    // An application update changes the bundled source path. The build
    // configuration is an absolute file outside that tree, so it must survive
    // the switch; only an explicit workspace edit clears it.
    const current = formRef.current;
    const sameWorkspace = current.workspace === path;
    const keptConfig =
      b.config || (sameWorkspace || b.bundled ? current.config : "");
    setForm((f) => {
      const same = f.workspace === path;
      return {
        ...f,
        workspace: path,
        // Packaged source trees omit artifacts/, so their bootstrap cannot
        // rediscover a configuration. Keep the user's absolute file across an
        // application update; an explicit workspace edit still clears it.
        config: b.config || (same || b.bundled ? f.config : ""),
        // The export plist lives inside the application bundle, so a new
        // bundle path needs its own copy. A user-selected file stays put.
        exportOptions: same
          ? f.exportOptions || b.exportOptions
          : b.exportOptions,
        output: f.output || b.output,
      };
    });
    if (b.setup) setSetup(b.setup);
    if (b.storage) setStoragePaths(b.storage);
    setFields(b.configFields);
    setJobs(b.jobs);
    setSelected(b.jobs.find((j) => isActive(j))?.id ?? b.jobs[0]?.id ?? "");
    // Report the configuration the workbench actually keeps, which may be the
    // user's existing file rather than the one found in the source tree.
    return { ...b, config: keptConfig };
  }, []);
  useEffect(() => {
    if (!native) return;
    let disposed = false;
    (async () => {
      const p = (await defaultWorkspace()) || formRef.current.workspace;
      if (p && !disposed) await load(p);
    })().catch((e) => {
      if (!disposed) setError(String(e));
    });
    return () => {
      disposed = true;
    };
  }, [load]);
  useEffect(() => {
    if (storageIssue) return;
    try {
      // Neither the pack nor its resource selection is remembered; writing
      // them would quietly preselect a pack for the next launch.
      localStorage.setItem(
        FORM_KEY,
        JSON.stringify({ ...form, source: "", resourceSelection: null }),
      );
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          settings: {
            ...DEFAULT_SETTINGS,
            ...parseSavedState(
              readWithLegacy(
                typeof window === "undefined" ? null : window.localStorage,
                STORAGE_KEY,
                LEGACY_STORAGE_KEY,
              ),
            ).settings,
            workspace: form.workspace,
            python: form.python,
          },
        }),
      );
    } catch {
      setStorageIssue("无法保存本地记录，已暂停自动保存。");
    }
  }, [form, storageIssue]);
  useEffect(() => {
    if (!native || !job) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const next = await workbench<BuildJob>(
          formRef.current,
          "status",
          job.id,
        );
        if (!stopped) {
          setJobs((old) => mergeJob(old, next));
          setPollError("");
          if (isActive(next)) timer = setTimeout(poll, 1400);
        }
      } catch (e) {
        if (!stopped) {
          setPollError("任务状态暂时无法读取：" + String(e));
          timer = setTimeout(poll, 4000);
        }
      }
    }
    void poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [job?.id, refresh]);
  useEffect(() => {
    if (!native || !active || active.id === job?.id) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    async function pollBackground() {
      try {
        const next = await workbench<BuildJob>(
          formRef.current,
          "status",
          active!.id,
        );
        if (!stopped) {
          setJobs((old) => mergeJob(old, next));
          if (isActive(next)) timer = setTimeout(pollBackground, 1800);
        }
      } catch {
        if (!stopped) timer = setTimeout(pollBackground, 4000);
      }
    }
    void pollBackground();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [active?.id, job?.id]);
  useEffect(() => {
    if (!follow || userScrolled) return;
    end.current?.scrollIntoView({ block: "nearest" });
  }, [job?.log, follow, userScrolled]);
  useEffect(() => {
    setUserScrolled(false);
  }, [job?.id]);
  useEffect(() => {
    if (!reset) return;
    const d = dialog.current!;
    const previous = document.activeElement;
    d.showModal();
    return () => {
      d.close();
      if (previous instanceof HTMLElement) previous.focus();
    };
  }, [reset]);
  useEffect(() => {
    if (!native) return;
    let off: (() => void) | undefined;
    let disposed = false;
    void import("@tauri-apps/api/webview")
      .then(({ getCurrentWebview }) =>
        getCurrentWebview().onDragDropEvent(async (e) => {
          if (active) {
            setDrag("none");
            return;
          }
          if (e.payload.type === "leave") {
            setDrag("none");
            return;
          }
          if (e.payload.type === "enter" || e.payload.type === "over") {
            const paths = e.payload.type === "enter" ? e.payload.paths : [];
            setDrag(
              e.payload.type === "over"
                ? (current) => (current === "none" ? "accepted" : current)
                : dragVerdict(paths),
            );
            return;
          }
          if (e.payload.type !== "drop") return;
          const source = e.payload.paths[0];
          setDrag("none");
          if (source) {
            update({ source, loader: "fabric" });
            setStep(0);
            setPage("builder");
            setNotice("已接收文件，正在读取来源。");
            await inspect(source);
          }
        }),
      )
      .then((fn) => {
        if (disposed) fn();
        else off = fn;
      })
      .catch((e) => setError(String(e)));
    return () => {
      disposed = true;
      off?.();
    };
  }, [active?.id]);
  useEffect(() => {
    if (page !== "builder") return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey) return;
      const target = event.target as HTMLElement | null;
      if (
        target?.closest(
          "input, textarea, select, dialog, [contenteditable='true']",
        )
      )
        return;
      if (
        event.altKey &&
        (event.key === "ArrowRight" || event.key === "ArrowLeft")
      ) {
        event.preventDefault();
        goToStep(step + (event.key === "ArrowRight" ? 1 : -1));
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [page, step, steps.length]);
  async function chooseSource(directory: boolean) {
    try {
      const p = await pickSource(directory);
      if (p) {
        update({ source: p, loader: "fabric" });
        await inspect(p);
      }
    } catch (e) {
      setError(String(e));
    }
  }
  async function detect() {
    await attempt("正在检查构建环境", async () => {
      setChecks(await workbench<Checks>(form, "check"));
    });
  }
  async function startSetup() {
    setSetup(await workbench<import("./workflow").SetupState>(
      formRef.current, "setup-start", undefined, { owned: true },
    ));
  }
  async function buildConfigured(request: BuildForm) {
    await attempt("正在创建构建任务", async () => {
      const result = await workbench<DependencyInventory>(request, "dependencies");
      setDependencies(result);
      if (!result.ready) {
        setNotice("原生依赖已过期、缺失或校验失败，请先一键重建所需依赖。");
        setPage("environment");
        return;
      }
      const j = await workbench<BuildJob>(request, "start");
      setJobs((old) => mergeJob(old, j));
      setSelected(j.id);
      setPage("history");
      setRefresh((v) => v + 1);
    });
  }
  async function begin() {
    if (problems.length || active || setupRunning) return;
    if (form.config) {
      await buildConfigured(form);
      return;
    }
    await attempt("正在启动环境准备", async () => {
      pendingBuild.current = form;
      try {
        await startSetup();
      } catch (error) {
        pendingBuild.current = null;
        throw error;
      }
    });
  }
  useEffect(() => {
    if (!setup) return;
    if (setup.state === "failed") {
      if (pendingBuild.current) setError(setup.error || "环境准备失败，请重试。");
      pendingBuild.current = null;
    }
    if (setup.state !== "ready" || !setup.config) return;
    const config = setup.config;
    const queued = pendingBuild.current;
    pendingBuild.current = null;
    setForm((old) => ({ ...old, config }));
    setChecks(null);
    setDependencyRevision((v) => v + 1);
    if (queued) void buildConfigured({ ...queued, config });
  }, [setup]);
  const environmentPreparation = (
    <BuildSetup
      setup={setup}
      configured={!!form.config}
      disabled={!native || !form.workspace || !!busy || !!active}
      onStart={() => void attempt("正在启动环境准备", startSetup)}
    />
  );
  async function resolveStaticExclusions(accepted: boolean) {
    const target = pendingExclusionJob;
    if (!target?.exclusionChallenge) return;
    await attempt(
      accepted ? "正在应用 Mod 排除方案" : "正在停止构建",
      async () => {
        const next = await workbench<BuildJob>(
          form,
          "resolve-exclusions",
          target.id,
          {
            challengeId: target.exclusionChallenge!.id,
            accepted,
          },
        );
        setJobs((old) => mergeJob(old, next));
        setSelected(target.id);
      },
    );
  }
  function nav(p: Page, fresh = false) {
    // The builder has no source memory: every visit starts at game content
    // with no pack selected, so the next pack is always checked fresh.
    if (p === "builder" && (page !== "builder" || fresh)) {
      setStep(0);
      setCheckedSteps([]);
      setReport(null);
      setForm((f) => ({
        ...f,
        source: "",
        resourceSelection: null,
        forceCompile: false,
      }));
    }
    setPage(p);
    if (p === "storage" && !storage && native && !busy) void loadStorage();
    setError("");
    setNotice("");
  }
  const nextAllowed = stepGate(step);
  const paths = (
    <>
      <PathField
        label="NCL 项目目录"
        value={form.workspace}
        directory
        onChange={(v) =>
          update({ workspace: v, config: "", exportOptions: "", output: "" })
        }
        hint="选择包含 tools、compiler 和 ios 的完整源码目录。"
      />
      <button
        className="text-button"
        disabled={!native || !!busy || !form.workspace}
        onClick={() =>
          void attempt("正在识别本地配置", async () => {
            const found = await load(form.workspace);
            if (found && !found.config)
              setNotice(
                "此项目目录没有可用的构建配置；请在下方选择配置，或在高级配置中填写并保存。",
              );
          })
        }
      >
        <RefreshCw size={15} />
        识别本地配置
      </button>
      <PathField
        label="构建配置"
        value={form.config}
        onChange={(v) => update({ config: v })}
        hint="包含客户端、AOT 工具链和原生后端路径。"
      />
      <PathField
        label="构建产物目录"
        value={form.output}
        directory
        onChange={(v) => update({ output: v })}
        hint="每次构建建立独立目录，保留完整日志和阶段检查点。"
      />
    </>
  );
  const advancedConfiguration = (
    <>
      {paths}
      <p>识别现有配置，或为本机创建独立的构建配置。</p>
      {configurationFields.map(([key, label, type]) => (
        <PathField
          key={key}
          label={label}
          value={fields[key] ?? ""}
          directory={type === "folder"}
          onChange={(v) =>
            setFields((old) => ({ ...old, [key]: v }))
          }
        />
      ))}
      <button
        className="secondary"
        disabled={!native || !!busy || !form.workspace}
        onClick={() =>
          void attempt("正在保存构建配置", async () => {
            const r = await workbench<{ path: string }>(
              form,
              "save-config",
              undefined,
              fields,
            );
            update({ config: r.path });
            setNotice("已创建独立构建配置。");
          })
        }
      >
        <Check size={16} />
        保存为新配置
      </button>
    </>
  );
  const builderPage = visiblePage === "builder";
  const hasPageToolbar = visiblePage === "history";
  const dockedPage = builderPage || hasPageToolbar;
  const pageBanners = (
    <>
      {storageIssue && <Note error>{storageIssue}</Note>}
      {error && !storageChange && (
        <div className="error-banner banner-enter" role="alert">
          <CircleAlert size={19} />
          <span>{error}</span>
          <button aria-label="关闭错误" onClick={() => setError("")}>
            <X size={17} />
          </button>
        </div>
      )}
      {notice && (
        <div className="success-banner banner-enter" role="status">
          <CheckCircle2 size={18} />
          {notice}
        </div>
      )}
      {!native && (
        <div className="preview-banner banner-enter">
          <Cpu size={17} />
          <span>
            当前为浏览器预览。请启动桌面应用，使用本地文件选择、真实编译和开发签名。
          </span>
        </div>
      )}
    </>
  );
  return (
    <div
      className="app-shell"
      data-window-chrome={
        native && /Mac/.test(navigator.platform) ? "overlay" : undefined
      }
    >
      <aside className="sidebar">
        <div
          className="sidebar-titlebar"
          data-tauri-drag-region
          aria-hidden="true"
        />
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            nav("builder");
          }}
        >
          <span>
            NCL Builder<small>LOCAL BUILD STUDIO</small>
          </span>
        </a>
        <div className="workspace-label">
          本地工作空间<span>EXPERIMENTAL</span>
        </div>
        <nav
          aria-label="主导航"
          ref={sidebar.containerRef}
          data-motion-moving={sidebar.moving ? "true" : "false"}
        >
          <MotionIndicator
            indicatorRef={sidebar.indicatorRef}
            moving={sidebar.moving}
          />
          {pages.map(([id, label, Icon]) => (
            <button
              key={id}
              data-motion-item
              className={"nav-item " + (page === id ? "selected" : "")}
              aria-current={page === id ? "page" : undefined}
              onClick={() => nav(id)}
            >
              <Icon size={19} aria-hidden="true" />
              {label}
              {id === "history" && jobs.length > 0 && (
                <span className="nav-count">
                  <AnimatedNumber value={jobs.length} />
                </span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="platform-mark">
            <Smartphone size={23} />
            <span>
              为 iPhone 构建<small>Minecraft Java 26.1.2</small>
            </span>
          </div>
          <p>Java 25 · Fabric · iOS ARM64</p>
          <div className="local-state">
            <span className={"dot " + (native ? "live" : "")} />
            {native ? "本机桌面工作台" : "浏览器预览"}
          </div>
        </div>
      </aside>
      <main>
        <header className="topbar" data-tauri-drag-region>
          <div className="window-breadcrumb">
            <span>工作空间</span>
            <ChevronRight size={14} />
            <strong>
              {
                {
                  builder: "构建 IPA",
                  history: "构建记录",
                  environment: "环境与资源",
                  storage: "存储管理",
                  settings: "设置",
                }[page]
              }
            </strong>
          </div>
          <div className="topbar-right">
            {active && (
              <button
                className="running-callout"
                onClick={() => {
                  setSelected(active.id);
                  nav("history");
                }}
              >
                <LoaderCircle size={14} className="spin" aria-hidden="true" />
                {stageName(active.stage)}
              </button>
            )}
            <span className="local-label">
              <span className="dot live" />
              所有构建在本机完成
            </span>
            <span className="version">
              v{PRODUCT_VERSION} · {localTesting ? "本地测试版" : "实验版"}
            </span>
          </div>
        </header>
        <div className="main-content" data-docked={dockedPage || undefined}>
          {hasPageToolbar && (
            <div className="page-toolbar-row" data-phase={pageView.phase}>
              <div className="page-toolbar">
                <div className="page-toolbar-actions">
                  <button
                    className="primary"
                    onClick={() => {
                      nav("builder", true);
                      setStep(0);
                    }}
                  >
                    <Plus size={17} />
                    新建构建
                  </button>
                  <button
                    className="secondary"
                    disabled={
                      !native ||
                      !!busy ||
                      !!active ||
                      (!form.unsigned && !form.exportOptions)
                    }
                    onClick={() =>
                      void attempt("正在导出现有构建", async () => {
                        const path = await choosePath(
                          "选择已完成的构建目录（含 result.json）",
                          true,
                        );
                        if (!path) return;
                        const next = await workbench<BuildJob>(
                          { ...form, existingBuild: path },
                          "start",
                        );
                        setJobs((old) => mergeJob(old, next));
                        setSelected(next.id);
                        setRefresh((v) => v + 1);
                      })
                    }
                  >
                    <Download size={16} />
                    从已有构建导出 IPA
                  </button>
                </div>
              </div>
            </div>
          )}
          <div
            className="page-column"
            data-phase={pageView.phase}
            data-builder={builderPage || undefined}
          >
            {!builderPage && pageBanners}
            {builderPage && (
              <section className="builder-panel">
                <div
                  className="stepper"
                  aria-label="构建步骤"
                  aria-keyshortcuts="Alt+ArrowLeft Alt+ArrowRight"
                  ref={stepperRef}
                  data-motion-moving={stepper.moving ? "true" : "false"}
                >
                  <MotionIndicator
                    indicatorRef={stepper.indicatorRef}
                    moving={stepper.moving}
                  />
                  {steps.map((s, i) => (
                    <button
                      key={s}
                      data-motion-item
                      data-step-index={i}
                      title={s}
                      className={
                        "step " +
                        (step === i
                          ? "current"
                          : checkedSteps.includes(i)
                            ? "complete"
                            : "")
                      }
                      aria-current={step === i ? "step" : undefined}
                      onClick={() => goToStep(i)}
                      data-locked={
                        i > step &&
                        !steps
                          .slice(step, i)
                          .every((_, offset) => stepGate(step + offset))
                          ? "true"
                          : undefined
                      }
                    >
                      <span
                        className="step-number"
                        data-state={
                          step === i
                            ? "current"
                            : checkedSteps.includes(i)
                              ? "complete"
                              : "pending"
                        }
                      >
                        {step === i ? (
                          <span className="step-digit">{i + 1}</span>
                        ) : checkedSteps.includes(i) ? (
                          <Check
                            className="step-check"
                            size={14}
                            aria-hidden="true"
                          />
                        ) : (
                          <span className="step-digit">{i + 1}</span>
                        )}
                      </span>
                      <span className="step-label">{s}</span>
                      {i < steps.length - 1 && (
                        <ChevronRight className="step-chevron" size={14} />
                      )}
                    </button>
                  ))}
                </div>
                <div className="step-scroll" ref={stepScrollRef}>
                  <div className="step-scroll-column">
                    {pageBanners}
                    <StepBody
                      step={visibleStep}
                      phase={stepView.phase}
                      direction={
                        stepView.phase === "idle" ? "none" : stepView.direction
                      }
                      className="step-content"
                    >
                      <div className="section-heading">
                        <span className="eyebrow">STEP 0{visibleStep + 1}</span>
                        <h2>
                          {
                            [
                              "选择要构建的游戏内容",
                              ...(form.loader === "fabric"
                                ? ["管理整合包资源"]
                                : []),
                              "准备你的构建环境",
                              "设置开发签名",
                              "准备好，开始构建。",
                            ][visibleStep]
                          }
                        </h2>
                        <p>
                          {
                            [
                              "导入 Fabric 整合包或本地 Prism 实例，也可以先构建原版。",
                              ...(form.loader === "fabric"
                                ? ["查看原包资源，勾选本次构建需要保留的内容。"]
                                : []),
                              "复用本机已经准备好的客户端、编译工具链和图形资源。",
                              "使用本机 Xcode 的开发证书和描述文件完成签名。",
                              "核对输入后，自动完成原生编译、签名和 IPA 导出。",
                            ][visibleStep]
                          }
                        </p>
                      </div>
                      {visibleStep === 0 && (
                        <>
                          <div
                            className="segmented"
                            aria-label="游戏类型"
                            data-selection={form.loader}
                            data-motion-moving={loaderMoving ? "true" : "false"}
                          >
                            <span
                              className="segment-plate"
                              aria-hidden="true"
                            />
                            <button
                              className={
                                form.loader === "fabric" ? "selected" : ""
                              }
                              aria-pressed={form.loader === "fabric"}
                              onClick={() => update({ loader: "fabric" })}
                            >
                              <Layers3 size={17} />
                              Fabric 整合包
                            </button>
                            <button
                              className={
                                form.loader === "vanilla" ? "selected" : ""
                              }
                              aria-pressed={form.loader === "vanilla"}
                              onClick={() => update({ loader: "vanilla" })}
                            >
                              <Box size={17} />
                              原版 26.1.2
                            </button>
                          </div>
                          {form.loader === "fabric" ? (
                            <>
                              <div
                                className="source-drop"
                                data-drag={drag}
                                aria-label={
                                  drag === "rejected"
                                    ? "不支持的文件类型"
                                    : undefined
                                }
                              >
                                <div
                                  className="drop-overlay"
                                  aria-hidden="true"
                                >
                                  <Package size={22} />
                                  <strong>
                                    {drag === "rejected"
                                      ? "此文件无法导入"
                                      : "松开以导入"}
                                  </strong>
                                  <span>
                                    {dropMessage(
                                      drag === "rejected"
                                        ? "rejected"
                                        : "accepted",
                                    )}
                                  </span>
                                </div>
                                <div className="source-glyph">
                                  <Package size={31} strokeWidth={1.5} />
                                </div>
                                <h3>
                                  {form.source
                                    ? basename(form.source)
                                    : "从你的整合包开始"}
                                </h3>
                                <p>
                                  {form.source
                                    ? "选择新的整合包会重新检查来源。"
                                    : "拖入 .mrpack 或 Prism 实例目录，也可以点击选择。"}
                                </p>
                                <div className="button-line center">
                                  <button
                                    className="primary"
                                    disabled={!native || !!busy || !!active}
                                    onClick={() => void chooseSource(false)}
                                  >
                                    <Plus size={17} />
                                    选择 .mrpack
                                  </button>
                                  <button
                                    className="secondary"
                                    disabled={!native || !!busy || !!active}
                                    onClick={() => void chooseSource(true)}
                                  >
                                    <FolderOpen size={17} />
                                    Prism 实例
                                  </button>
                                </div>
                                <span className="source-caption">
                                  {busy === "正在检查游戏内容"
                                    ? "正在自动检查来源…"
                                    : "选择后自动检查来源 · Minecraft 26.1.2 · Fabric Loader 0.19.3"}
                                </span>
                                <p className="import-note">
                                  .mrpack
                                  仅自动获取客户端必需文件；可选文件可在资源管理中勾选。自动下载限
                                  Modrinth CDN，其他来源可先通过 Prism 准备。
                                </p>
                              </div>
                              {currentReport && (
                                <div
                                  className="source-report"
                                  key={currentReport.source}
                                >
                                  <div className="report-top">
                                    <span>
                                      <FileCheck2 size={18} />
                                      {currentReport.pack_name ||
                                        basename(form.source)}
                                    </span>
                                    <Pill
                                      tone={
                                        currentReport.fatal ? "red" : "green"
                                      }
                                    >
                                      {currentReport.fatal
                                        ? "需要处理"
                                        : "静态检查通过"}
                                    </Pill>
                                  </div>
                                  <div className="report-metrics">
                                    <span>
                                      <strong>
                                        <AnimatedNumber
                                          value={currentReport.mods.length}
                                        />
                                      </strong>
                                      已读取的 Mod
                                    </span>
                                    <span>
                                      <strong>
                                        {currentReport.manifest_files ===
                                        undefined ? (
                                          "—"
                                        ) : (
                                          <AnimatedNumber
                                            value={currentReport.manifest_files}
                                          />
                                        )}
                                      </strong>
                                      清单文件
                                    </span>
                                    <span>
                                      <strong>
                                        <AnimatedNumber
                                          value={
                                            currentReport.findings.filter(
                                              (f) => f.severity === "error",
                                            ).length
                                          }
                                        />
                                      </strong>
                                      阻断项
                                    </span>
                                  </div>
                                  {currentReport.fabric_loader_version !==
                                    "0.19.3" && (
                                    <Note>
                                      当前来源 Loader 为{" "}
                                      {currentReport.fabric_loader_version ||
                                        "未知"}
                                      ，本次将使用构建器内置的
                                      0.19.3。差异会记录在任务里，构建可以继续。
                                    </Note>
                                  )}
                                  <label className="audit-check">
                                    <input
                                      type="checkbox"
                                      checked={form.forceCompile}
                                      onChange={(e) =>
                                        update({
                                          forceCompile: e.target.checked,
                                        })
                                      }
                                    />
                                    <span>
                                      <strong>
                                        强制编译（忽略 Loader 版本差异）
                                      </strong>
                                      <small>
                                        使用 Fabric Loader 0.19.3
                                        尝试构建；差异会写入任务记录，实际转换或编译失败时保留错误日志。
                                      </small>
                                    </span>
                                  </label>
                                  <ModList
                                    key={currentReport.source}
                                    report={currentReport}
                                  />
                                  <button
                                    className="text-button"
                                    aria-expanded={details}
                                    onClick={() => setDetails(!details)}
                                  >
                                    {details
                                      ? "收起诊断详情"
                                      : "查看兼容性与诊断详情"}
                                    <ChevronRight size={15} />
                                  </button>
                                  <Reveal open={details}>
                                    <div className="diagnostics">
                                      {currentReport.findings.map((f, i) => (
                                        <div
                                          className={"finding " + f.severity}
                                          key={i}
                                        >
                                          <span>
                                            {f.severity === "error"
                                              ? "阻断"
                                              : f.severity === "warning"
                                                ? "注意"
                                                : "信息"}
                                          </span>
                                          <p>
                                            <strong>{f.code}</strong>
                                            {f.message}
                                          </p>
                                        </div>
                                      ))}
                                    </div>
                                  </Reveal>
                                </div>
                              )}
                              <div className="tertiary-row">
                                <label className="text-button">
                                  <FileJson2 size={15} />
                                  导入检查报告
                                  <input
                                    className="visually-hidden"
                                    type="file"
                                    accept=".json,application/json"
                                    onChange={(e) => {
                                      const f = e.target.files?.[0];
                                      e.target.value = "";
                                      if (f)
                                        void attempt(
                                          "正在读取报告",
                                          async () => {
                                            if (f.size > 8 * 1024 * 1024)
                                              throw new Error(
                                                "报告不能超过 8 MiB",
                                              );
                                            const r = parseReport(
                                              JSON.parse(await f.text()),
                                            );
                                            update({ source: r.source });
                                            remember(r);
                                          },
                                        );
                                    }}
                                  />
                                </label>
                                {currentReport && (
                                  <button
                                    className="text-button"
                                    onClick={() =>
                                      void attempt("正在导出报告", () =>
                                        saveDocument(
                                          "ncl-preflight.json",
                                          JSON.stringify(
                                            currentReport,
                                            null,
                                            2,
                                          ),
                                        ),
                                      )
                                    }
                                  >
                                    导出报告
                                    <ArrowUpRight size={14} />
                                  </button>
                                )}
                              </div>
                            </>
                          ) : (
                            <div className="vanilla-card">
                              <Box size={44} strokeWidth={1.25} />
                              <h3>Minecraft Java 26.1.2</h3>
                              <p>
                                使用构建配置中已校验的本地正版客户端和资源，无需导入额外
                                Mod。
                              </p>
                              <Pill tone="green">原版构建路径</Pill>
                            </div>
                          )}
                        </>
                      )}
                      {visibleStep === 1 && form.loader === "fabric" && (
                        <ResourceManager
                          key={form.source}
                          report={currentReport}
                          selection={form.resourceSelection}
                          onChange={(resourceSelection) =>
                            update({ resourceSelection })
                          }
                        />
                      )}
                      {(visibleStep === environmentStep ||
                        visibleStep === reviewStep) && (
                        <section
                          className="dependency-preflight"
                          aria-label="原生依赖预检"
                        >
                          <h3>原生依赖预检</h3>
                          <p>
                            {checkingDependencies
                              ? "正在比对源码与依赖哈希…"
                              : dependencies?.ready
                                ? "所需依赖与当前源码一致"
                                : "构建前需检查原生依赖库。"}
                          </p>
                          {dependencyError && (
                            <Note error>{dependencyError}</Note>
                          )}
                          {dependencies && !dependencies.ready && (
                            <Note error>
                              {dependencies.libraries
                                .filter(
                                  (r) => r.required && r.state !== "current",
                                )
                                .map(
                                  (r) =>
                                    r.name +
                                    "：" +
                                    [...r.reasons, ...r.changedFiles].join(
                                      "；",
                                    ),
                                )
                                .join("\n")}
                            </Note>
                          )}
                          <div className="button-line">
                            <button
                              className="secondary"
                              onClick={() => setPage("environment")}
                            >
                              管理依赖库
                            </button>
                            <button
                              className="primary"
                              disabled={
                                !native ||
                                !!busy ||
                                !!active ||
                                !dependencies ||
                                dependencies.ready
                              }
                              onClick={() =>
                                dependencies &&
                                void rebuildDependencies(
                                  dependencies.libraries
                                    .filter(
                                      (r) =>
                                        r.required && r.state !== "current",
                                    )
                                    .map((r) => r.key),
                                )
                              }
                            >
                              一键重建所需依赖
                            </button>
                          </div>
                        </section>
                      )}
                      {visibleStep === environmentStep && (
                        <>
                          {environmentPreparation}
                          <details className="advanced">
                            <summary>
                              <Settings2 size={16} />
                              高级配置 · 工具链和资源路径
                            </summary>
                            {advancedConfiguration}
                          </details>
                          <div className="check-toolbar">
                            <span>环境状态</span>
                            <button
                              className="secondary"
                              disabled={!native || !!busy || !form.config}
                              onClick={() => void detect()}
                            >
                              <RefreshCw size={16} />
                              检测环境
                            </button>
                          </div>
                          {busy === "正在检查构建环境" ? (
                            <div className="check-list" role="status">
                              <div className="check-row checking">
                                <StatusMark state="checking" size={19}>
                                  <LoaderCircle size={19} className="spin" />
                                </StatusMark>
                                <div>
                                  <strong>正在检测本机构建环境</strong>
                                  <p>
                                    依次检查主机、SDK、AOT
                                    工具链、原生依赖与签名准备情况。
                                  </p>
                                </div>
                                <span>检测中</span>
                              </div>
                            </div>
                          ) : checks ? (
                            <CheckList checks={checks} />
                          ) : (
                            <Note>
                              下一步还可配置签名。构建时会再次核验全部输入和资源哈希。
                            </Note>
                          )}
                        </>
                      )}
                      {visibleStep === environmentStep + 1 && (
                        <>
                          <AppIconField
                            form={form}
                            update={update}
                            disabled={!native || !!busy || !!active}
                            locked={!!busy || !!active}
                          />
                          <label className="setting-row">
                            <span className="setting-label">
                              <strong>导出未签名 IPA</strong>
                              <small>跳过开发签名与 Xcode 归档导出。</small>
                            </span>
                            <span className="setting-control">
                              <input
                                type="checkbox"
                                checked={!!form.unsigned}
                                onChange={(e) =>
                                  update({ unsigned: e.target.checked })
                                }
                              />
                            </span>
                          </label>
                          {form.unsigned && (
                            <Note>
                              未签名 IPA
                              不能直接装机，需要另行签名。构建器会验证构建自带
                              IPA 的内容与哈希。
                            </Note>
                          )}
                          {!form.unsigned && (
                            <>
                              <div className="signing-visual">
                                <div className="signing-icon">
                                  <ShieldCheck size={30} />
                                </div>
                                <div>
                                  <h3>使用你的本机开发签名</h3>
                                  <p>证书与私钥由钥匙串和 Xcode 管理。</p>
                                </div>
                                <Pill>Development</Pill>
                              </div>
                              <div className="field">
                                <label>
                                  <span>
                                    Apple Team ID <small>可选</small>
                                  </span>
                                  <input
                                    value={form.team}
                                    maxLength={10}
                                    placeholder="自动使用本机有效描述文件对应的团队"
                                    onChange={(e) =>
                                      update({
                                        team: e.target.value
                                          .trim()
                                          .toUpperCase(),
                                      })
                                    }
                                    spellCheck={false}
                                  />
                                </label>
                                <small>
                                  填写 10 位 Team
                                  ID，或留空自动选择。证书与描述文件需先在 Xcode
                                  中准备。
                                </small>
                              </div>
                              <PathField
                                label="IPA 导出配置"
                                value={form.exportOptions}
                                onChange={(v) => update({ exportOptions: v })}
                                hint="使用 debugging 开发导出方式，默认复用项目内 ExportOptions.plist。"
                              />
                              <div className="signing-facts">
                                <div>
                                  <span>应用标识</span>
                                  <code>org.fabricaot.research.c0.kexin</code>
                                </div>
                                <div>
                                  <span>安装方式</span>
                                  <strong>导出后由你安装到设备</strong>
                                </div>
                                <div>
                                  <span>Personal Team</span>
                                  <strong>免费描述文件通常 7 天到期</strong>
                                </div>
                              </div>
                              <Note>
                                保持同一应用标识以延续现有数据。安装、更新及存档保留需在真机独立验证。
                              </Note>
                            </>
                          )}
                        </>
                      )}
                      {visibleStep === reviewStep && (
                        <>
                          <div className="review-grid">
                            {[
                              [
                                "游戏内容",
                                form.loader === "fabric"
                                  ? "Fabric · " +
                                    (currentReport?.pack_name ||
                                      basename(form.source) ||
                                      "尚未选择")
                                  : "原版 Minecraft 26.1.2",
                              ],
                              ...(form.loader === "fabric"
                                ? [
                                    [
                                      "资源选择",
                                      resourceReady
                                        ? "保留 " +
                                          form.resourceSelection!.included
                                            .length +
                                          " / " +
                                          currentReport!.resources!.length +
                                          " 项资源"
                                        : "请先确认资源",
                                    ],
                                  ]
                                : []),
                              ["构建目标", "iOS ARM64 · Java 25 AOT"],
                              [
                                "渲染后端",
                                "OpenGL 兼容 · GL41 / Zink / MoltenVK",
                              ],
                              [
                                "编译方式",
                                form.loader === "fabric" && form.forceCompile
                                  ? "强制编译 · Fabric Loader 0.19.3"
                                  : "标准检查",
                              ],
                              [
                                "签名团队",
                                form.unsigned
                                  ? "跳过开发签名"
                                  : form.team || "自动选择本机有效团队",
                              ],
                              [
                                "应用图标",
                                form.icon
                                  ? basename(form.icon)
                                  : "系统默认图标",
                              ],
                              [
                                "最终产物",
                                form.unsigned
                                  ? "未签名 IPA + SHA-256（不能直接装机）"
                                  : "开发签名 IPA + SHA-256",
                              ],
                            ].map(([k, v]) => (
                              <div className="review-item" key={k}>
                                <span>{k}</span>
                                <strong>{v}</strong>
                              </div>
                            ))}
                          </div>
                          <div className="review-path">
                            <span>输出位置</span>
                            <code>{form.output || "尚未选择"}</code>
                          </div>
                          <div className="check-toolbar">
                            <span>构建前检查</span>
                            <button
                              className="text-button"
                              disabled={!native || !!busy || !form.config}
                              title={
                                !native || busy || !form.config
                                  ? controlReason
                                  : undefined
                              }
                              onClick={() => void detect()}
                            >
                              <RefreshCw size={15} />
                              重新检测
                            </button>
                          </div>
                          {checks && <CheckList checks={checks} />}{" "}
                          {problems.length > 0 && (
                            <div className="block-list" role="status">
                              <strong>开始前还需要</strong>
                              {problems.map((s) => (
                                <p key={s}>· {s}</p>
                              ))}
                            </div>
                          )}
                          <div className="build-explainer">
                            <Clock3 size={18} />
                            <p>
                              原生编译可能需要较长时间。日志与检查点实时保存，关闭工作台后任务会继续运行。
                            </p>
                          </div>
                        </>
                      )}
                    </StepBody>
                  </div>
                </div>
                <footer className="wizard-footer" ref={wizardFooterRef}>
                  <button
                    className="text-button"
                    disabled={step === 0 || !!busy}
                    onClick={() => goToStep(step - 1)}
                  >
                    <ChevronLeft size={16} />
                    上一步
                  </button>
                  <span
                    className="wizard-count"
                    aria-label={`第 ${step + 1} 步，共 ${steps.length} 步`}
                  >
                    <span aria-hidden="true">
                      <AnimatedNumber value={step + 1} /> / {steps.length}
                    </span>
                  </span>
                  {step < reviewStep ? (
                    <button
                      className="primary"
                      data-action="next"
                      disabled={!nextAllowed || !!busy}
                      onClick={() => goToStep(step + 1)}
                    >
                      下一步
                      <ArrowRight size={17} />
                    </button>
                  ) : (
                    <button
                      className="primary"
                      data-action="build"
                      disabled={
                        problems.length > 0 ||
                        !!busy ||
                        !!active ||
                        setupRunning ||
                        checks?.ready === false
                      }
                      title={
                        problems.length > 0
                          ? problems[0]
                          : busy || active
                            ? controlReason
                            : checks?.ready === false
                              ? "环境检查未通过，请先处理上方标出的项目。"
                              : undefined
                      }
                      onClick={() => void begin()}
                    >
                      <Hammer size={17} />
                      {setupRunning ? "正在准备环境" : !form.config && canPrepare ? "准备并构建 IPA" : "构建 IPA"}
                    </button>
                  )}
                </footer>
              </section>
            )}
            {visiblePage === "history" && (
              <>
                <div className="history-layout">
                  <section className="job-list-panel flat">
                    <div className="list-heading">
                      <h2>
                        构建任务 <span>{jobs.length}</span>
                      </h2>
                      <button
                        className="icon-button"
                        aria-label="刷新构建记录"
                        disabled={!native || !!busy}
                        onClick={() =>
                          void attempt("正在刷新记录", async () => {
                            setJobs(
                              await workbench<BuildJob[]>(form, "history"),
                            );
                            setRefresh((v) => v + 1);
                          })
                        }
                      >
                        <RefreshCw size={16} />
                      </button>
                    </div>
                    <label className="search-field">
                      <Search size={16} />
                      <input
                        aria-label="搜索构建"
                        value={search}
                        placeholder="搜索任务"
                        onChange={(e) => setSearch(e.target.value)}
                      />
                    </label>
                    {jobs.length === 0 ? (
                      <div className="small-empty">
                        <History size={25} />
                        <p>还没有构建任务</p>
                        <small>开始构建后，进度与产物会出现在这里。</small>
                      </div>
                    ) : (
                      jobs
                        .filter((j) =>
                          (j.name + " " + j.id)
                            .toLowerCase()
                            .includes(search.toLowerCase()),
                        )
                        .map((j) => (
                          <button
                            className={
                              "job-list-item " +
                              (job?.id === j.id ? "selected" : "")
                            }
                            key={j.id}
                            onClick={() => setSelected(j.id)}
                          >
                            <div className={"job-icon " + j.state}>
                              {isActive(j) ? (
                                <LoaderCircle size={19} className="spin" />
                              ) : j.state === "succeeded" ? (
                                <CheckCircle2 size={19} />
                              ) : (
                                <Package size={19} />
                              )}
                            </div>
                            <div>
                              <strong>{j.name}</strong>
                              <small>{date(j.startedAt)}</small>
                              <span>{jobStateName(j)}</span>
                            </div>
                            <ChevronRight size={15} />
                          </button>
                        ))
                    )}
                  </section>
                  <section className="job-detail flat">
                    {!job ? (
                      <div className="history-empty">
                        <div className="empty-art">
                          <Package size={45} strokeWidth={1.3} />
                        </div>
                        <h2>准备好你的第一个 IPA。</h2>
                        <p>从选择游戏内容开始，工作台会完成后续编译与打包。</p>
                        <button
                          className="primary"
                          onClick={() => nav("builder")}
                        >
                          前往构建
                          <ArrowRight size={16} />
                        </button>
                      </div>
                    ) : job.kind === "dependencies" ? (
                      <DependencyTask
                        job={job}
                        disabled={!native || !!busy}
                        onCancel={() => void cancelDependencies(job)}
                      />
                    ) : (
                      <>
                        <div className="job-detail-head">
                          <div>
                            <span className="eyebrow">
                              BUILD {job.id.slice(0, 8).toUpperCase()}
                            </span>
                            <h2>{job.name}</h2>
                            <p>
                              {date(job.startedAt)} 开始
                              {job.finishedAt
                                ? " · " + date(job.finishedAt) + " 结束"
                                : ""}
                              {" · "}
                              <JobElapsed job={job} />
                            </p>
                          </div>
                          <Pill
                            tone={
                              job.state === "succeeded"
                                ? "green"
                                : ["failed", "interrupted"].includes(job.state)
                                  ? "red"
                                  : ""
                            }
                          >
                            {jobStateName(job)}
                          </Pill>
                        </div>
                        {job.compatibility && (
                          <CompatibilitySummary report={job.compatibility} />
                        )}
                        {job.request.forceCompile &&
                          !job.request.existingBuild && (
                            <Note>
                              此任务启用了强制编译。
                              {job.compatibilityOverrides
                                ?.map((override) => override.message)
                                .join("；") ||
                                "使用构建器内置的 Fabric Loader 0.19.3。"}
                            </Note>
                          )}
                        {!!job.acceptedExclusions?.length && (
                          <Note>
                            <strong>
                              本次构建已按确认排除静态 AOT 不支持项。
                            </strong>
                            <p>
                              排除项仅对本次构建副本生效，不代表其余 Mod
                              已通过真机功能验证。
                            </p>
                            <details>
                              <summary>查看排除的 Mod 文件</summary>
                              <ul>
                                {job.acceptedExclusions.flatMap(
                                  (challenge) =>
                                    challenge?.mods.map((mod) => (
                                      <li key={challenge.id + mod.file}>
                                        {mod.name} · {mod.file}
                                      </li>
                                    )) ?? [],
                                )}
                              </ul>
                            </details>
                          </Note>
                        )}
                        {pollError && <Note error>{pollError}</Note>}
                        {job.error && (
                          <div className="job-error" role="alert">
                            <CircleAlert size={20} />
                            <div>
                              <strong>
                                {job.state === "cancelled"
                                  ? "任务已停止"
                                  : (explainError(job.error, job.stage)
                                      ?.title ?? "构建需要处理")}
                              </strong>
                              <JobErrorDetail
                                error={job.error}
                                stage={job.stage}
                              />
                              <small>
                                完整诊断保存在任务文件夹。修复后可重试，输入指纹一致的阶段会复用。
                              </small>
                            </div>
                          </div>
                        )}
                        {job.state === "succeeded" && (
                          <div className="ipa-result">
                            <div className="ipa-icon">
                              <FileCheck2 size={35} />
                            </div>
                            <div>
                              <h3>IPA 已导出并通过校验</h3>
                              <p>
                                {basename(job.ipa || "")} ·{" "}
                                {((job.bytes ?? 0) / 1024 / 1024).toFixed(1)}{" "}
                                MiB
                              </p>
                              <small>
                                {job.signature === "UNSIGNED"
                                  ? "未签名 IPA 不能直接装机，需要另行签名。"
                                  : "安装与游戏行为仍需在你的设备上验证。"}
                              </small>
                            </div>
                            <button
                              className="primary"
                              disabled={!native || !!busy}
                              onClick={() =>
                                void attempt("正在显示 IPA", () =>
                                  workbench(form, "reveal", job.id),
                                )
                              }
                            >
                              <FolderOpen size={16} />在 Finder 中显示
                            </button>
                            <button
                              className="secondary"
                              disabled={!!busy}
                              onClick={() =>
                                void attempt("正在导出日志", () =>
                                  saveDocument(
                                    "ncl-build-" + job.id.slice(0, 8) + ".txt",
                                    [
                                      job.name,
                                      jobStateName(job),
                                      job.build,
                                      job.error,
                                      job.log ?? "",
                                    ].join(String.fromCharCode(10)),
                                  ),
                                )
                              }
                            >
                              <Download size={16} />
                              查看构建日志
                            </button>
                            <code>SHA-256 {job.sha256}</code>
                          </div>
                        )}
                        <div className="job-stage-strip" aria-hidden="true">
                          {["validate", "aot", "package", "verify"].map(
                            (id) => {
                              const i = stages.findIndex((s) => s[0] === id);
                              const current = stages.findIndex(
                                (s) => s[0] === job.stage,
                              );
                              const done =
                                job.state === "succeeded" || i < current;
                              const running = id === job.stage && isActive(job);
                              return (
                                <span
                                  key={id}
                                  data-state={
                                    done
                                      ? "done"
                                      : running
                                        ? "running"
                                        : "pending"
                                  }
                                >
                                  <i />
                                  {stageName(id)}
                                </span>
                              );
                            },
                          )}
                        </div>
                        <div className="pipeline-heading">
                          <h3 key={job.stage} className="pipeline-live-stage">
                            {isActive(job)
                              ? stageName(job.stage)
                              : "构建流水线"}
                          </h3>
                          <span>阶段状态来自实际构建输出</span>
                        </div>
                        <div
                          className="pipeline"
                          data-state={
                            job.state === "succeeded"
                              ? "done"
                              : ["failed", "cancelled", "interrupted"].includes(
                                    job.state,
                                  )
                                ? "stopped"
                                : "running"
                          }
                        >
                          {stages
                            .filter(
                              ([id]) =>
                                !job.request.unsigned ||
                                !["archive", "export-log"].includes(id),
                            )
                            .filter(([id]) =>
                              job.request.existingBuild
                                ? [
                                    "validate",
                                    "archive",
                                    "export-log",
                                    "verify",
                                  ].includes(id)
                                : job.request.loader === "fabric" ||
                                  !["source", "fabric"].includes(id),
                            )
                            .map(([id, label]) => {
                              const i = stages.findIndex((s) => s[0] === id);
                              const current = stages.findIndex(
                                (s) => s[0] === job.stage,
                              );
                              const done =
                                job.state === "succeeded" || i < current;
                              const running = id === job.stage && isActive(job);
                              const stopped =
                                id === job.stage &&
                                job.state !== "awaiting-exclusions" &&
                                ["failed", "cancelled", "interrupted"].includes(
                                  job.state,
                                );
                              return (
                                <div
                                  key={id}
                                  className={
                                    done
                                      ? "done"
                                      : running
                                        ? "running"
                                        : stopped
                                          ? "stopped"
                                          : ""
                                  }
                                >
                                  <span className="pipeline-mark">
                                    {done ? (
                                      <Check size={13} />
                                    ) : running ? (
                                      <LoaderCircle
                                        size={13}
                                        className="spin"
                                      />
                                    ) : stopped ? (
                                      <X size={13} />
                                    ) : (
                                      <span className="tiny-dot" />
                                    )}
                                  </span>
                                  <span className="pipeline-label">
                                    {job.request.unsigned && id === "package"
                                      ? "构建未签名应用"
                                      : job.request.unsigned && id === "verify"
                                        ? "验证应用与 IPA"
                                        : label}
                                  </span>
                                </div>
                              );
                            })}
                        </div>
                        <div className="log-panel">
                          <div className="log-heading">
                            <span>
                              <Terminal size={16} />
                              构建日志
                            </span>
                            <label
                              className="follow-toggle"
                              data-paused={userScrolled ? "true" : "false"}
                            >
                              <input
                                type="checkbox"
                                checked={follow}
                                onChange={(e) => {
                                  setFollow(e.target.checked);
                                  if (e.target.checked) setUserScrolled(false);
                                }}
                              />
                              自动跟随
                            </label>
                          </div>
                          <div
                            className="log-scroll"
                            tabIndex={0}
                            aria-label="构建日志"
                            onScroll={(event) => {
                              const element = event.currentTarget;
                              const atEnd =
                                element.scrollHeight -
                                  element.scrollTop -
                                  element.clientHeight <
                                24;
                              setUserScrolled(!atEnd);
                            }}
                          >
                            <LogView
                              text={job.log ?? ""}
                              label="构建日志内容"
                            />
                            <div ref={end} />
                          </div>
                        </div>
                        <div className="job-actions">
                          <button
                            className="secondary"
                            disabled={!native || !!busy}
                            onClick={() =>
                              void attempt("正在打开任务目录", () =>
                                workbench(form, "reveal-folder", job.id),
                              )
                            }
                          >
                            <FolderOpen size={16} />
                            任务文件夹
                          </button>
                          <button
                            className="secondary"
                            disabled={!!busy}
                            onClick={() =>
                              void attempt("正在导出日志", () =>
                                saveDocument(
                                  "ncl-build-" + job.id.slice(0, 8) + ".txt",
                                  [
                                    job.name,
                                    jobStateName(job),
                                    job.build,
                                    job.error,
                                    job.log ?? "",
                                  ].join(String.fromCharCode(10)),
                                ),
                              )
                            }
                          >
                            <Download size={16} />
                            导出日志
                          </button>
                          <div className="spacer" />
                          {isActive(job) ? (
                            <button
                              className="danger"
                              disabled={
                                !native || !!busy || job.state === "cancelling"
                              }
                              onClick={() =>
                                void attempt("正在取消任务", async () => {
                                  const next = await workbench<BuildJob>(
                                    form,
                                    "cancel",
                                    job.id,
                                  );
                                  setJobs((old) => mergeJob(old, next));
                                  setRefresh((v) => v + 1);
                                })
                              }
                            >
                              <Square size={14} />
                              {job.state === "cancelling"
                                ? "正在停止…"
                                : "取消构建"}
                            </button>
                          ) : (
                            job.state !== "succeeded" && (
                              <button
                                className="primary"
                                disabled={!native || !!busy || !!active}
                                onClick={() =>
                                  void attempt("正在恢复构建", async () => {
                                    // Retry keeps the recorded pack and uses the current build preference.
                                    const next = await workbench<BuildJob>(
                                      { ...job.request, quickBuild: form.quickBuild },
                                      "retry",
                                      job.id,
                                    );
                                    setJobs((old) => mergeJob(old, next));
                                    setSelected(next.id);
                                    setRefresh((v) => v + 1);
                                  })
                                }
                              >
                                <RefreshCw size={16} />
                                重试构建
                              </button>
                            )
                          )}
                        </div>
                      </>
                    )}
                  </section>
                </div>
              </>
            )}
            {visiblePage === "environment" && (
              <div className="environment-layout">
                {environmentPreparation}
                {activeBuildReason && (
                  <div className="blocked-banner" role="status">
                    <CircleAlert size={18} aria-hidden="true" />
                    <span>{activeBuildReason}</span>
                  </div>
                )}
                <section className="environment-check" aria-labelledby="environment-check-title">
                  <div className="environment-row">
                    <div>
                      <h2 id="environment-check-title">环境检查</h2>
                      <p>
                        {busy === "正在检查构建环境"
                          ? "正在检查主机、SDK、AOT 输入和签名…"
                          : form.config
                            ? "核对主机、SDK、AOT 输入和签名。"
                            : "自动准备完成后即可检测环境。"}
                      </p>
                    </div>
                    <button
                      className="secondary"
                      disabled={!native || !!busy || !!active || setupRunning || !form.config}
                      title={controlReason || undefined}
                      onClick={() => void detect()}
                    >
                      <RefreshCw size={16} />
                      检测环境
                    </button>
                  </div>
                  {checks && <CheckList checks={checks} />}
                </section>
                {dependencyJob && (
                  <DependencyTask
                    job={dependencyJob}
                    disabled={!native || !!busy}
                    onCancel={() => void cancelDependencies(dependencyJob)}
                  />
                )}
                <details className="advanced environment-disclosure">
                  <summary>
                    <span>原生依赖库</span>
                    <small>{checkingDependencies
                      ? "检查中"
                      : dependencyError
                        ? "检查失败"
                        : dependencies
                          ? dependencies.ready ? "所需依赖就绪" : "所需依赖待处理"
                          : form.config ? "等待检查" : "等待环境准备"}</small>
                  </summary>
                  <NativeDependencies
                    report={dependencies}
                    error={dependencyError}
                    checking={checkingDependencies}
                    disabled={!native || !!busy || !!active || setupRunning || !form.config}
                    disabledReason={controlReason}
                    onRefresh={() => setDependencyRevision((v) => v + 1)}
                    onRebuild={(keys) => void rebuildDependencies(keys)}
                  />
                </details>
                <details className="advanced environment-disclosure">
                  <summary><span>高级配置</span><small>本地路径与手动配置</small></summary>
                  <div className="environment-advanced-fields">{advancedConfiguration}</div>
                </details>
              </div>
            )}
            {visiblePage === "storage" && (
              <StorageManager
                plan={storage}
                busy={busy}
                available={native}
                active={
                  !!active || ["queued", "running"].includes(setup?.state || "")
                }
                done={storageDone}
                onScan={() => void loadStorage()}
                onClean={(groups) => void cleanStorage(groups)}
                onReveal={(path) =>
                  void attempt("正在打开 Finder", async () => {
                    await revealPath(path);
                  })
                }
                locations={
                  <>
                    {(
                      [
                        ["cache", "编译缓存目录"],
                        ["builds", "构建产物根目录"],
                        ["jobs", "任务记录目录"],
                        ["rust", "Rust 缓存目录"],
                      ] as const
                    ).map(([key, label]) => (
                      <PathField
                        key={key}
                        label={label}
                        directory
                        value={storagePaths[key]}
                        onChange={(v) =>
                          setStoragePaths((p) => ({ ...p, [key]: v }))
                        }
                      />
                    ))}
                    <div className="sm-location-save">
                      <button
                        className="button secondary"
                        disabled={
                          !native ||
                          !!busy ||
                          !!active ||
                          ["queued", "running"].includes(setup?.state || "")
                        }
                        onClick={() =>
                          void attempt("正在保存存储位置", async () => {
                            const result = await workbench<{
                              ready: boolean;
                            }>(
                              formRef.current,
                              "save-storage",
                              undefined,
                              storagePaths,
                            );
                            update({ output: storagePaths.builds });
                            setStorage(null);
                            setStorageDone("");
                            setStorageStatus(
                              result.ready
                                ? "存储位置已保存，空间预检通过。现有数据未迁移。"
                                : "存储位置已保存，剩余空间不足，请更换目录后再构建。",
                            );
                          })
                        }
                      >
                        保存存储位置并检查空间
                      </button>
                      {storageStatus && <p role="status">{storageStatus}</p>}
                    </div>
                  </>
                }
              />
            )}
            {visiblePage === "settings" && (
              <section className="settings-page">
                <div className="settings-group settings-account">
                  <h2>{localTesting ? "本地测试版" : "账号管理"}</h2>
                  {localTesting ? (
                    <p>准备环境和构建 IPA 无需 Microsoft 登录。</p>
                  ) : (
                    <AccountPanel disabled={!!active || !!busy} />
                  )}
                </div>
                <div className="settings-group">
                  <h2>构建</h2>
                  <label className="setting-row setting-switch-row">
                    <span className="setting-label">
                      <strong id="quick-build-label">快速构建</strong>
                      <small id="quick-build-description">
                        开启时复用匹配的编译产物，或快速编译。关闭时从头编译。适用于新建和重试。
                      </small>
                    </span>
                    <input
                      className="setting-switch"
                      type="checkbox"
                      role="switch"
                      aria-labelledby="quick-build-label"
                      aria-describedby="quick-build-description"
                      checked={form.quickBuild === true}
                      onChange={(event) => update({ quickBuild: event.target.checked })}
                    />
                  </label>
                </div>
                <div className="settings-group">
                  <h2>外观</h2>
                  <div className="setting-row">
                    <div className="setting-label">
                      <strong>外观主题</strong>
                      <small>深色与浅色配色都适配全部页面。</small>
                    </div>
                    <div
                      className="theme-options"
                      role="group"
                      aria-label="外观主题"
                    >
                      {(
                        [
                          ["system", "跟随系统", Monitor],
                          ["light", "浅色", Sun],
                          ["dark", "深色", Moon],
                        ] as const
                      ).map(([value, label, Icon]) => (
                        <button
                          key={value}
                          className={
                            "theme-option " +
                            (theme === value ? "selected" : "")
                          }
                          aria-label={label}
                          aria-pressed={theme === value}
                          onClick={() => chooseTheme(value)}
                        >
                          <Icon size={16} aria-hidden="true" />
                          <strong>{label}</strong>
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="setting-row">
                    <div className="setting-label">
                      <strong>交互强调色</strong>
                      <small>
                        选中、焦点和主要操作使用此颜色；状态色保持不变。
                      </small>
                    </div>
                    <div className="setting-control accent-setting">
                      <SelectMenu
                        label="交互强调色"
                        value={accent}
                        onChange={chooseAccent}
                        options={accentOptions.map((option) => ({
                          value: option.value,
                          label: option.label,
                        }))}
                      />
                    </div>
                  </div>
                </div>

                <div className="settings-group">
                  <h2>本地执行</h2>
                  <button className="secondary" onClick={() => nav("environment")}>
                    打开环境与资源
                  </button>
                  <div className="field">
                    <label>
                      <span>Python 解释器</span>
                      <input
                        placeholder="python3 · 自动从系统环境查找"
                        value={form.python}
                        onChange={(e) => update({ python: e.target.value })}
                        spellCheck={false}
                      />
                    </label>
                    <small>
                      完整构建需要原生 ARM64 Python 3.11 或更高版本。
                    </small>
                  </div>
                  <PathField
                    label="NCL 项目目录"
                    value={form.workspace}
                    directory
                    onChange={(v) => update({ workspace: v })}
                  />
                </div>

                <QuickStorageDirectory
                  busy={busy}
                  disabled={
                    !native ||
                    !!busy ||
                    !!active ||
                    ["queued", "running"].includes(setup?.state || "")
                  }
                  status={storageStatus}
                  onChoose={() => void quickStorageDirectory()}
                  onReset={() => void resetStorageDirectories()}
                />
                <div className="settings-group">
                  <h2>本地记录</h2>
                  <div className="setting-row">
                    <div className="setting-label">
                      <strong>界面记录</strong>
                      <small>
                        任务历史保存在所选任务记录目录，重置界面不会删除构建文件。
                      </small>
                    </div>
                    <div className="setting-control button-line">
                      <button
                        className="secondary"
                        onClick={() =>
                          void attempt("正在导出本地记录", () =>
                            saveDocument(
                              "ncl-workspace.json",
                              JSON.stringify(
                                {
                                  builder: localStorage.getItem(FORM_KEY),
                                  legacy: readWithLegacy(
                                    window.localStorage,
                                    STORAGE_KEY,
                                    LEGACY_STORAGE_KEY,
                                  ),
                                },
                                null,
                                2,
                              ),
                            ),
                          )
                        }
                      >
                        <Download size={16} />
                        导出原始记录
                      </button>
                      <button
                        className="danger subtle"
                        onClick={() => setReset(true)}
                      >
                        重置界面记录
                      </button>
                    </div>
                  </div>
                </div>

                <div className="settings-group">
                  <h2>关于 {BUILDER_NAME}</h2>
                  <div className="setting-row">
                    <div className="setting-label">
                      <strong>{PRODUCT_NAME}</strong>
                      <small>
                        {PRODUCT_SHORT_NAME} · Mac 构建工具 {BUILDER_NAME} · iOS
                        应用 {IOS_APP_NAME}
                      </small>
                    </div>
                    <div className="setting-control">
                      <span className="pill">
                        v{PRODUCT_VERSION} · {localTesting ? "本地测试版" : "实验版"}
                      </span>
                    </div>
                  </div>
                  <div className="setting-row">
                    <div className="setting-label">
                      <strong>技术标识</strong>
                      <small>
                        Bundle ID、配置键值、AOT 与 GL41/Zink
                        构建链保持不变，已有项目和存档继续使用。
                      </small>
                    </div>
                    <div className="setting-control">
                      <span className="pill">GL41 / Zink</span>
                    </div>
                  </div>
                </div>
              </section>
            )}
          </div>
        </div>
      </main>
      {busy && (
        <div className="busy-toast" role="status">
          <LoaderCircle size={18} className="spin" />
          {busy}
        </div>
      )}
      {storageChange && (
        <StorageChangeDialog
          plan={storageChange}
          busy={busy}
          error={error}
          onCancel={() => {
            setStorageChange(null);
            setError("");
          }}
          onApply={(policy) => void applyStorageChange(policy)}
        />
      )}
      <ExclusionDialog
        challenge={pendingExclusionJob?.exclusionChallenge ?? null}
        busy={!!busy}
        onResolve={(accepted) => void resolveStaticExclusions(accepted)}
      />
      {reset && (
        <dialog
          ref={dialog}
          className="confirm-dialog"
          aria-labelledby="reset-title"
          onCancel={(e) => {
            e.preventDefault();
            setReset(false);
          }}
        >
          <h2 id="reset-title">重置界面记录？</h2>
          <p>表单设置会被重置，构建任务、IPA、游戏内容和存档仍保留。</p>
          <div className="button-line">
            <button className="secondary" onClick={() => setReset(false)}>
              保留记录
            </button>
            <button
              className="danger"
              onClick={() => {
                localStorage.removeItem(FORM_KEY);
                localStorage.removeItem(STORAGE_KEY);
                localStorage.removeItem(LEGACY_FORM_KEY);
                localStorage.removeItem(LEGACY_STORAGE_KEY);
                setForm({ ...defaultForm });
                setReport(null);
                setStorageIssue("");
                setReset(false);
              }}
            >
              重置记录
            </button>
          </div>
        </dialog>
      )}
    </div>
  );
}
