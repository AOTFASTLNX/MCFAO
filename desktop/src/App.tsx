import {
  useCallback,
  useEffect,
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
  Trash2,
  X,
} from "lucide-react";
import {
  DEFAULT_SETTINGS,
  STORAGE_KEY,
  makeInstance,
  parseReport,
  parseSavedState,
  upsertInstance,
  type Instance,
  type Report,
} from "./model";
import {
  choosePath,
  defaultWorkspace,
  inspectSource,
  native,
  pickSource,
  saveDocument,
  workbench,
} from "./bridge";
import {
  FORM_KEY,
  buildProblems,
  configurationFields,
  defaultForm,
  isActive,
  mergeJob,
  restoreForm,
  stageName,
  stages,
  stateNames,
  type Bootstrap,
  type BuildForm,
  type BuildJob,
  type Checks,
} from "./workflow";
import ModList from "./ModList";
import ResourceManager from "./ResourceManager";
import { LogView } from "./LogView";
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
  themeLabels,
  toggleTheme,
  type ResolvedTheme,
  type ThemePreference,
} from "./theme";
type Page = "builder" | "history" | "environment" | "settings";

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
  try {
    const old = parseSavedState(localStorage.getItem(STORAGE_KEY));
    return {
      form: localStorage.getItem(FORM_KEY)
        ? restoreForm(localStorage.getItem(FORM_KEY))
        : {
            ...defaultForm,
            workspace: old.settings.workspace,
            python: old.settings.python,
          },
      instances: old.instances,
      error: "",
    };
  } catch {
    return {
      form: { ...defaultForm },
      instances: [] as Instance[],
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
function CheckList({ checks }: { checks: Checks }) {
  return (
    <div className="check-list">
      {checks.checks.map((c) => (
        <div className={"check-row " + c.status} key={c.name}>
          {c.status === "ready" ? (
            <CheckCircle2 size={19} />
          ) : c.status === "warning" ? (
            <TriangleAlert size={19} />
          ) : (
            <CircleAlert size={19} />
          )}
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
        确认后将从独立的暂存副本移除上述文件和依赖它们的 Mod，再重新执行转换。若剩余项目仍有阻断项，会再次提示。
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
  const [instances, setInstances] = useState(saved.instances);
  const [storageIssue, setStorageIssue] = useState(saved.error);
  const [page, setPage] = useState<Page>("builder");
  const [step, setStep] = useState(0);
  const [report, setReport] = useState<Report | null>(null);
  const [checks, setChecks] = useState<Checks | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [jobs, setJobs] = useState<BuildJob[]>([]);
  const [selected, setSelected] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [details, setDetails] = useState(false);
  const [search, setSearch] = useState("");
  const [follow, setFollow] = useState(true);
  const [pollError, setPollError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [reset, setReset] = useState(false);
  const pendingExclusionJob = jobs.find(
    (item) => item.state === "awaiting-exclusions" && item.exclusionChallenge,
  );
  const lock = useRef(false);
  const formRef = useRef(form);
  formRef.current = form;
  const end = useRef<HTMLDivElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const active = jobs.find((j) => isActive(j));
  const job = jobs.find((j) => j.id === selected) ?? active ?? jobs[0];
  const currentReport = report?.source === form.source ? report : null;
  const steps =
    form.loader === "fabric"
      ? ["游戏内容", "资源管理", "构建环境", "开发签名", "确认构建"]
      : ["游戏内容", "构建环境", "开发签名", "确认构建"];
  const environmentStep = form.loader === "fabric" ? 2 : 1;
  const reviewStep = steps.length - 1;
  const resourceReady =
    !!currentReport?.resources &&
    form.resourceSelection?.source === form.source &&
    form.resourceSelection?.fingerprint === currentReport.resources_fingerprint;
  const problems = buildProblems(form, report, native);
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
      ...(patch.resourceSelection !== undefined ? { audited: false } : {}),
      ...(patch.source !== undefined || patch.loader !== undefined
        ? {
            audited: false,
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
      ["workspace", "python", "config", "team", "exportOptions"].some(
        (k) => k in patch,
      )
    )
      setChecks(null);
    setError("");
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
      audited: false,
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
    setInstances((old) =>
      upsertInstance(
        old,
        makeInstance(
          r,
          old.find((i) => i.report.source === r.source),
        ),
      ),
    );
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
    setForm((f) => ({
      ...f,
      workspace: path,
      config: f.workspace !== path ? b.config : f.config || b.config,
      exportOptions:
        f.workspace !== path
          ? b.exportOptions
          : f.exportOptions || b.exportOptions,
      output: f.workspace !== path ? b.output : f.output || b.output,
    }));
    setFields(b.configFields);
    setJobs(b.jobs);
    setSelected(b.jobs.find((j) => isActive(j))?.id ?? b.jobs[0]?.id ?? "");
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
      localStorage.setItem(
        FORM_KEY,
        JSON.stringify({ ...form, audited: false, forceCompile: false }),
      );
      const old = parseSavedState(localStorage.getItem(STORAGE_KEY));
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          instances,
          settings: {
            ...DEFAULT_SETTINGS,
            ...old.settings,
            workspace: form.workspace,
            python: form.python,
          },
        }),
      );
    } catch {
      setStorageIssue("无法保存本地记录，已暂停自动保存。");
    }
  }, [form, instances, storageIssue]);
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
    if (follow) end.current?.scrollIntoView({ block: "nearest" });
  }, [job?.log, follow]);
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
          if (e.payload.type !== "drop" || active) return;
          const source = e.payload.paths[0];
          if (source) {
            update({ source, loader: "fabric" });
            setStep(0);
            setPage("builder");
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
  async function begin() {
    if (problems.length || active) return;
    await attempt("正在创建构建任务", async () => {
      const j = await workbench<BuildJob>(form, "start");
      setJobs((old) => mergeJob(old, j));
      setSelected(j.id);
      setPage("history");
      setRefresh((v) => v + 1);
    });
  }
  async function resolveStaticExclusions(accepted: boolean) {
    const target = pendingExclusionJob;
    if (!target?.exclusionChallenge) return;
    await attempt(accepted ? "正在应用 Mod 排除方案" : "正在停止构建", async () => {
      const next = await workbench<BuildJob>(form, "resolve-exclusions", target.id, {
        challengeId: target.exclusionChallenge!.id,
        accepted,
      });
      setJobs((old) => mergeJob(old, next));
      setSelected(target.id);
    });
  }
  function nav(p: Page) {
    setPage(p);
    setError("");
    setNotice("");
  }
  const nextAllowed =
    step === 0
      ? form.loader === "vanilla" || (!!currentReport && !currentReport.fatal)
      : form.loader === "fabric" && step === 1
        ? resourceReady &&
          !!currentReport?.resources?.some(
            (r) =>
              r.category === "mods" &&
              r.path.toLowerCase().endsWith(".jar") &&
              form.resourceSelection?.included.includes(r.id),
          )
        : step === environmentStep
          ? !!form.workspace && !!form.config && !!form.output
          : true;
  const paths = (
    <>
      <PathField
        label="FabricAOT 项目目录"
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
          void attempt("正在识别本地配置", () => load(form.workspace))
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
          <img src="/mark.svg" alt="" />
          <span>
            FabricAOT<small>LOCAL BUILD STUDIO</small>
          </span>
        </a>
        <div className="workspace-label">
          本地工作空间<span>EXPERIMENTAL</span>
        </div>
        <nav aria-label="主导航">
          {(
            [
              ["builder", "构建 IPA", Hammer],
              ["history", "构建记录", History],
              ["environment", "环境与资源", Cpu],
              ["settings", "设置", Settings2],
            ] as const
          ).map(([id, label, Icon]) => (
            <button
              key={id}
              className={"nav-item " + (page === id ? "selected" : "")}
              aria-current={page === id ? "page" : undefined}
              onClick={() => nav(id)}
            >
              <Icon size={19} aria-hidden="true" />
              {label}
              {id === "history" && jobs.length > 0 && (
                <span className="nav-count">{jobs.length}</span>
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
                  settings: "设置",
                }[page]
              }
            </strong>
          </div>
          <div className="topbar-right">
            <span className="local-label">
              <span className="dot live" />
              所有构建在本机完成
            </span>
            <button
              className="theme-toggle"
              aria-label={
                "切换为" +
                themeLabels[resolvedTheme === "dark" ? "light" : "dark"] +
                "模式"
              }
              aria-pressed={resolvedTheme === "light"}
              title={"当前：" + themeLabels[theme]}
              onClick={() => chooseTheme(toggleTheme(theme, systemDark))}
            >
              {resolvedTheme === "dark" ? (
                <Sun size={17} aria-hidden="true" />
              ) : (
                <Moon size={17} aria-hidden="true" />
              )}
              <span>{themeLabels[theme]}</span>
            </button>
            <span className="version">v0.2 · 实验版</span>
          </div>
        </header>
        <div className="main-content">
          {storageIssue && <Note error>{storageIssue}</Note>}
          {error && (
            <div className="error-banner" role="alert">
              <CircleAlert size={19} />
              <span>{error}</span>
              <button aria-label="关闭错误" onClick={() => setError("")}>
                <X size={17} />
              </button>
            </div>
          )}
          {notice && (
            <div className="success-banner" role="status">
              <CheckCircle2 size={18} />
              {notice}
            </div>
          )}
          {!native && (
            <div className="preview-banner">
              <Cpu size={17} />
              <span>
                当前为浏览器预览。请启动桌面应用，使用本地文件选择、真实编译和开发签名。
              </span>
            </div>
          )}
          {page === "builder" && (
            <>
              <section className="page-intro">
                <div>
                  <span className="eyebrow">FROM YOUR MAC TO YOUR IPHONE</span>
                  <h1>把你的世界，装进 iPhone。</h1>
                  <p>从整合包到签名 IPA，在一个工作台里完成。</p>
                </div>
                <div className="target-card">
                  <div className="target-icon">
                    <Package size={26} />
                  </div>
                  <div>
                    <span>构建目标</span>
                    <strong>iOS · ARM64</strong>
                    <small>本地原生执行 · 无 Java JIT</small>
                  </div>
                </div>
              </section>
              <div className="workflow-layout">
                <section className="builder-panel">
                  <div className="stepper" aria-label="构建步骤">
                    {steps.map((s, i) => (
                      <button
                        key={s}
                        className={
                          "step " +
                          (step === i ? "current" : i < step ? "complete" : "")
                        }
                        aria-current={step === i ? "step" : undefined}
                        onClick={() => setStep(i)}
                      >
                        <span className="step-number">
                          {i < step ? <Check size={15} /> : i + 1}
                        </span>
                        <span>{s}</span>
                        {i < steps.length - 1 && (
                          <ChevronRight className="step-chevron" size={14} />
                        )}
                      </button>
                    ))}
                  </div>
                  <div className="step-content">
                    <div className="section-heading">
                      <span className="eyebrow">STEP 0{step + 1}</span>
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
                          ][step]
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
                          ][step]
                        }
                      </p>
                    </div>
                    {step === 0 && (
                      <>
                        <div className="segmented" aria-label="游戏类型">
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
                            <div className="source-drop">
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
                                  ? "重新选择来源，或检查当前本地内容。"
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
                                Minecraft 26.1.2 · Fabric Loader 0.19.3
                              </span>
                              <p className="import-note">
                                .mrpack
                                仅自动获取客户端必需文件；可选文件可在资源管理中勾选。自动下载限
                                Modrinth CDN，其他来源可先通过 Prism 准备。
                              </p>
                            </div>
                            <div className="source-manual">
                              <label>
                                来源路径
                                <input
                                  value={form.source}
                                  onChange={(e) =>
                                    update({ source: e.target.value })
                                  }
                                  placeholder="也可粘贴本地整合包或实例路径"
                                  spellCheck={false}
                                />
                              </label>
                              <button
                                className="secondary"
                                disabled={!native || !!busy || !form.source}
                                onClick={() => void inspect(form.source)}
                              >
                                <Search size={16} />
                                检查来源
                              </button>
                            </div>
                            {instances.length > 0 && (
                              <label className="recent-source">
                                最近导入
                                <select
                                  value={
                                    instances.some(
                                      (i) => i.report.source === form.source,
                                    )
                                      ? form.source
                                      : ""
                                  }
                                  onChange={async (e) => {
                                    const v = e.target.value;
                                    if (v) {
                                      update({ source: v });
                                      if (native) await inspect(v);
                                      else
                                        remember(
                                          instances.find(
                                            (i) => i.report.source === v,
                                          )!.report,
                                        );
                                    }
                                  }}
                                >
                                  <option value="">选择最近的来源</option>
                                  {instances.map((i) => (
                                    <option key={i.id} value={i.report.source}>
                                      {i.name}
                                    </option>
                                  ))}
                                </select>
                              </label>
                            )}
                            {currentReport && (
                              <div className="source-report">
                                <div className="report-top">
                                  <span>
                                    <FileCheck2 size={18} />
                                    {currentReport.pack_name ||
                                      basename(form.source)}
                                  </span>
                                  <Pill
                                    tone={currentReport.fatal ? "red" : "green"}
                                  >
                                    {currentReport.fatal
                                      ? "需要处理"
                                      : "静态检查通过"}
                                  </Pill>
                                </div>
                                <div className="report-metrics">
                                  <span>
                                    <strong>{currentReport.mods.length}</strong>
                                    已读取的 Mod
                                  </span>
                                  <span>
                                    <strong>
                                      {currentReport.manifest_files ?? "—"}
                                    </strong>
                                    清单文件
                                  </span>
                                  <span>
                                    <strong>
                                      {
                                        currentReport.findings.filter(
                                          (f) => f.severity === "error",
                                        ).length
                                      }
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
                                      update({ forceCompile: e.target.checked })
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
                                  onClick={() => setDetails(!details)}
                                >
                                  {details
                                    ? "收起诊断详情"
                                    : "查看兼容性与诊断详情"}
                                  <ChevronRight size={15} />
                                </button>
                                {details && (
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
                                )}
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
                                      void attempt("正在读取报告", async () => {
                                        if (f.size > 8 * 1024 * 1024)
                                          throw new Error("报告不能超过 8 MiB");
                                        const r = parseReport(
                                          JSON.parse(await f.text()),
                                        );
                                        update({ source: r.source });
                                        remember(r);
                                      });
                                  }}
                                />
                              </label>
                              {currentReport && (
                                <button
                                  className="text-button"
                                  onClick={() =>
                                    void attempt("正在导出报告", () =>
                                      saveDocument(
                                        "fabricaot-preflight.json",
                                        JSON.stringify(currentReport, null, 2),
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
                    {step === 1 && form.loader === "fabric" && (
                      <ResourceManager
                        key={form.source}
                        report={currentReport}
                        selection={form.resourceSelection}
                        onChange={(resourceSelection) =>
                          update({ resourceSelection })
                        }
                      />
                    )}
                    {step === environmentStep && (
                      <>
                        {paths}
                        <details className="advanced">
                          <summary>
                            <Settings2 size={16} />
                            高级配置 · 工具链和资源路径
                          </summary>
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
                        {checks ? (
                          <CheckList checks={checks} />
                        ) : (
                          <Note>
                            下一步还可配置签名。构建时会再次核验全部输入和资源哈希。
                          </Note>
                        )}
                      </>
                    )}
                    {step === environmentStep + 1 && (
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
                                  team: e.target.value.trim().toUpperCase(),
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
                    {step === reviewStep && (
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
                            ["签名团队", form.team || "自动选择本机有效团队"],
                            ["最终产物", "开发签名 IPA + SHA-256"],
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
                        {form.loader === "fabric" && (
                          <label className="audit-check">
                            <input
                              type="checkbox"
                              checked={form.audited}
                              onChange={(e) =>
                                update({ audited: e.target.checked })
                              }
                            />
                            <span>
                              <strong>
                                此来源中的 Mod 已完成构建期代码审计
                              </strong>
                              <small>
                                允许既有隔离流程执行这些 Mod 的 Mixin /
                                构建期转换。静态检查不代表 iOS 兼容性验证。
                              </small>
                            </span>
                          </label>
                        )}
                        <div className="check-toolbar">
                          <span>构建前检查</span>
                          <button
                            className="text-button"
                            disabled={!native || !!busy || !form.config}
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
                  </div>
                  <footer className="wizard-footer">
                    <button
                      className="text-button"
                      disabled={step === 0 || !!busy}
                      onClick={() => setStep((s) => s - 1)}
                    >
                      <ChevronLeft size={16} />
                      上一步
                    </button>
                    <span>
                      {step + 1} / {steps.length}
                    </span>
                    {step < reviewStep ? (
                      <button
                        className="primary"
                        disabled={!nextAllowed || !!busy}
                        onClick={() => setStep((s) => s + 1)}
                      >
                        下一步
                        <ArrowRight size={17} />
                      </button>
                    ) : (
                      <button
                        className="primary"
                        disabled={
                          problems.length > 0 ||
                          !!busy ||
                          !!active ||
                          checks?.ready === false
                        }
                        onClick={() => void begin()}
                      >
                        <Hammer size={17} />
                        构建 IPA
                      </button>
                    )}
                  </footer>
                </section>
                <aside className="build-aside">
                  <div className="world-card">
                    <img src="/landscape.svg" alt="" />
                    <div>
                      <span className="eyebrow">
                        BUILT LOCALLY. PLAYED LOCALLY.
                      </span>
                      <h3>
                        从本地出发。
                        <br />
                        在掌心继续。
                      </h3>
                      <p>
                        你的游戏内容，在 Mac 上编译，
                        <br />在 iPhone 上原生运行。
                      </p>
                    </div>
                  </div>
                  <div className="aside-checklist">
                    <h3>这次构建会完成</h3>
                    {[
                      ["验证输入", "版本、资源和依赖指纹"],
                      ["原生编译", "Fabric 静态转换与 Java 25 AOT"],
                      ["签名打包", "Xcode 归档和开发签名"],
                      ["校验导出", "IPA 签名、平台和 SHA-256"],
                    ].map(([title, detail], i) => (
                      <div key={title}>
                        <span>{i + 1}</span>
                        <p>
                          <strong>{title}</strong>
                          <small>{detail}</small>
                        </p>
                      </div>
                    ))}
                  </div>
                  {active && (
                    <button
                      className="active-callout"
                      onClick={() => {
                        setSelected(active.id);
                        nav("history");
                      }}
                    >
                      <LoaderCircle size={18} className="spin" />
                      <span>
                        有构建正在进行<small>{stageName(active.stage)}</small>
                      </span>
                      <ArrowRight size={16} />
                    </button>
                  )}
                  <p className="aside-footnote">
                    独立、非官方的本地构建工具。仅使用你合法拥有的游戏内容；Mod
                    兼容性与真机游玩按项目验收标准分别验证。
                  </p>
                </aside>
              </div>
            </>
          )}
          {page === "history" && (
            <>
              <section className="page-intro compact">
                <div>
                  <span className="eyebrow">BUILD HISTORY</span>
                  <h1>每一次构建，都有迹可循。</h1>
                  <p>查看真实阶段、保留的日志和已验证的 IPA。</p>
                </div>
                <div className="page-intro-actions">
                  <button
                    className="primary"
                    onClick={() => {
                      nav("builder");
                      setStep(0);
                    }}
                  >
                    <Plus size={17} />
                    新建构建
                  </button>
                  <button
                    className="secondary"
                  disabled={
                    !native || !!busy || !!active || !form.exportOptions
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
              </section>
              <div className="history-layout">
                <section className="job-list-panel">
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
                          setJobs(await workbench<BuildJob[]>(form, "history"));
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
                            <span>{stateNames[j.state]}</span>
                          </div>
                          <ChevronRight size={15} />
                        </button>
                      ))
                  )}
                </section>
                <section className="job-detail">
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
                          {stateNames[job.state]}
                        </Pill>
                      </div>
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
                          <strong>本次构建已按确认排除静态 AOT 不支持项。</strong>
                          <p>排除项仅对本次构建副本生效，不代表其余 Mod 已通过真机功能验证。</p>
                          <details>
                            <summary>查看排除的 Mod 文件</summary>
                            <ul>
                              {job.acceptedExclusions.flatMap((challenge) =>
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
                                : "构建需要处理"}
                            </strong>
                            <pre>{job.error}</pre>
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
                              {((job.bytes ?? 0) / 1024 / 1024).toFixed(1)} MiB
                            </p>
                            <small>安装与游戏行为仍需在你的设备上验证。</small>
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
                          <code>SHA-256 {job.sha256}</code>
                        </div>
                      )}
                      <div className="pipeline-heading">
                        <h3>
                          {isActive(job) ? stageName(job.stage) : "构建流水线"}
                        </h3>
                        <span>阶段状态来自实际构建输出</span>
                      </div>
                      <div className="pipeline">
                        {stages
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
                            return (
                              <div
                                key={id}
                                className={
                                  done ? "done" : running ? "running" : ""
                                }
                              >
                                <span>
                                  {done ? (
                                    <Check size={13} />
                                  ) : running ? (
                                    <LoaderCircle size={13} className="spin" />
                                  ) : (
                                    <span className="tiny-dot" />
                                  )}
                                </span>
                                {label}
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
                          <label>
                            <input
                              type="checkbox"
                              checked={follow}
                              onChange={(e) => setFollow(e.target.checked)}
                            />
                            自动跟随
                          </label>
                        </div>
                        <div
                          className="log-scroll"
                          tabIndex={0}
                          aria-label="构建日志"
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
                                "fabricaot-build-" +
                                  job.id.slice(0, 8) +
                                  ".txt",
                                [
                                  job.name,
                                  stateNames[job.state],
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
                                  const next = await workbench<BuildJob>(
                                    form,
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
          {page === "environment" && (
            <>
              <section className="page-intro compact">
                <div>
                  <span className="eyebrow">ENVIRONMENT & RESOURCES</span>
                  <h1>所有构建条件，一目了然。</h1>
                  <p>本地客户端、编译工具链和原生后端是实际构建输入。</p>
                </div>
                <button
                  className="primary"
                  disabled={!native || !!busy || !form.config}
                  onClick={() => void detect()}
                >
                  <RefreshCw size={17} />
                  检测环境
                </button>
              </section>
              <div className="settings-layout">
                <section className="panel">
                  <h2>构建资源</h2>
                  <p className="section-description">
                    自动识别已经准备好的本地配置。
                  </p>
                  {paths}
                  <button
                    className="secondary"
                    onClick={() => {
                      nav("builder");
                      setStep(environmentStep);
                    }}
                  >
                    <Settings2 size={16} />
                    编辑高级资源配置
                  </button>
                </section>
                <section className="panel">
                  <h2>环境检查</h2>
                  <p className="section-description">
                    检查主机、SDK、AOT 输入和签名准备情况。
                  </p>
                  {checks ? (
                    <CheckList checks={checks} />
                  ) : (
                    <div className="small-empty">
                      <Cpu size={31} />
                      <h3>等待环境检查</h3>
                      <p>选择构建配置后点击「检测环境」。</p>
                    </div>
                  )}
                  <Note>
                    版本检查通过后，构建还会逐个核验客户端、运行库、资源、着色器和阶段产物指纹。
                  </Note>
                </section>
              </div>
            </>
          )}
          {page === "settings" && (
            <>
              <section className="page-intro compact">
                <div>
                  <span className="eyebrow">WORKSPACE SETTINGS</span>
                  <h1>让工作台适合你的习惯。</h1>
                  <p>设置仅保存在本机，不保存账户密码和签名私钥。</p>
                </div>
              </section>
              <section className="panel narrow">
                <h2>外观</h2>
                <p className="section-description">
                  深色与浅色配色都适配工作台的全部页面；选择会保存在本机。
                </p>
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
                        "theme-option " + (theme === value ? "selected" : "")
                      }
                      aria-label={label}
                      aria-pressed={theme === value}
                      onClick={() => chooseTheme(value)}
                    >
                      <Icon size={19} aria-hidden="true" />
                      <strong>{label}</strong>
                      <small>
                        {value === "system"
                          ? systemDark
                            ? "当前跟随为深色"
                            : "当前跟随为浅色"
                          : value === "light"
                            ? "明亮背景，适合白天"
                            : "深色背景，减少眩光"}
                      </small>
                    </button>
                  ))}
                </div>
                <div className="field accent-setting">
                  <label>
                    <span>交互强调色</span>
                    <select
                      aria-label="交互强调色"
                      value={accent}
                      onChange={(e) => chooseAccent(e.target.value)}
                    >
                      {accentOptions.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <small>
                    选中、焦点和主要操作使用此颜色；成功、警告与错误状态保持不变。
                  </small>
                </div>
                <div className="divider" />
                <h2>本地执行</h2>
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
                  <small>完整构建需要原生 ARM64 Python 3.11 或更高版本。</small>
                </div>
                <PathField
                  label="FabricAOT 项目目录"
                  value={form.workspace}
                  directory
                  onChange={(v) => update({ workspace: v })}
                />
                <div className="divider" />
                <h2>来源记录</h2>
                <p className="section-description">
                  移除记录只影响工作台列表，原始文件与产物仍保留。
                </p>
                {instances.map((i) => (
                  <div className="instance-setting" key={i.id}>
                    <Package size={18} />
                    <span>
                      {i.name}
                      <small>{i.report.source}</small>
                    </span>
                    <button
                      className="icon-button"
                      aria-label={"移除来源记录 " + i.name}
                      onClick={() =>
                        setInstances((old) => old.filter((x) => x.id !== i.id))
                      }
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                ))}
                {!instances.length && (
                  <p className="muted">还没有导入的来源。</p>
                )}
                <div className="divider" />
                <h2>本地记录</h2>
                <div className="button-line">
                  <button
                    className="secondary"
                    onClick={() =>
                      void attempt("正在导出本地记录", () =>
                        saveDocument(
                          "fabricaot-workspace.json",
                          JSON.stringify(
                            {
                              builder: localStorage.getItem(FORM_KEY),
                              legacy: localStorage.getItem(STORAGE_KEY),
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
                <small className="muted">
                  任务历史保存在项目
                  artifacts/desktop-jobs，重置界面不会删除构建文件。
                </small>
              </section>
            </>
          )}
          <footer className="page-footer">
            <span>FabricAOT · 本地构建，内容由你掌控。</span>
            <span>Minecraft 26.1.2 / Java 25 / Fabric Only</span>
          </footer>
        </div>
      </main>
      {busy && (
        <div className="busy-toast" role="status">
          <LoaderCircle size={18} className="spin" />
          {busy}
        </div>
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
          <p>
            来源列表和表单设置会被重置，构建任务、IPA、游戏内容和存档仍保留。
          </p>
          <div className="button-line">
            <button className="secondary" onClick={() => setReset(false)}>
              保留记录
            </button>
            <button
              className="danger"
              onClick={() => {
                localStorage.removeItem(FORM_KEY);
                localStorage.removeItem(STORAGE_KEY);
                setInstances([]);
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
