import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type DragEvent,
  type ReactNode,
} from "react";
import {
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Box,
  Check,
  CheckCircle2,
  ChevronRight,
  Circle,
  CircleAlert,
  Clock3,
  Code2,
  Copy,
  Cpu,
  FileCheck2,
  FileJson2,
  FileUp,
  Folder,
  FolderOpen,
  HardDrive,
  HelpCircle,
  Import,
  Layers3,
  LayoutDashboard,
  ListFilter,
  LoaderCircle,
  Monitor,
  Package,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Smartphone,
  Terminal,
  Trash2,
  TriangleAlert,
  X,
} from "lucide-react";
import {
  DEFAULT_SETTINGS,
  STORAGE_KEY,
  findingLabels,
  makeInstance,
  parseReport,
  parseSavedState,
  prepareCommand,
  upsertInstance,
  type Environment,
  type Instance,
  type Report,
  type Task,
} from "./model";
import {
  buildInstructions,
  defaultWorkspace,
  detectPlatform,
  getEnvironment,
  inspectSource,
  native,
  pickSource,
  pickWorkspace,
  saveDocument,
} from "./bridge";

type Page =
  "home" | "instances" | "reports" | "builds" | "environment" | "settings";
const pages = [
  { id: "home", label: "工作台", icon: LayoutDashboard },
  { id: "instances", label: "实例库", icon: Layers3 },
  { id: "reports", label: "兼容性报告", icon: ShieldCheck },
  { id: "builds", label: "构建与日志", icon: Terminal },
  { id: "environment", label: "工作环境", icon: Cpu },
] as const;
const date = (value: string) =>
  new Date(value).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
function initialState() {
  try {
    return { ...parseSavedState(localStorage.getItem(STORAGE_KEY)), error: "" };
  } catch {
    return {
      instances: [] as Instance[],
      settings: DEFAULT_SETTINGS,
      error:
        "无法读取本地记录。为保留原始数据，已暂停自动保存；可在设置中导出并重置。",
    };
  }
}
function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "green" | "amber" | "red" | "neutral";
}) {
  return (
    <span className={"badge " + tone}>
      <span className="status-dot" />
      {children}
    </span>
  );
}
function Empty({
  title,
  children,
  action,
  icon = <Package size={27} />,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="empty-icon">{icon}</div>
      <h3>{title}</h3>
      <p>{children}</p>
      {action}
    </div>
  );
}
function Modal({
  title,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useLayoutEffect(() => {
    const dialog = ref.current!;
    const previous = document.activeElement;
    dialog.showModal();
    return () => {
      dialog.close();
      if (previous instanceof HTMLElement && previous.isConnected) previous.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className={"modal " + (wide ? "wide" : "")}
      aria-labelledby="modal-title"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
    >
      <div className="modal-head">
        <div>
          <span className="eyebrow">FABRICAOT WORKSPACE</span>
          <h2 id="modal-title">{title}</h2>
        </div>
        <button
          className="icon-button"
          onClick={onClose}
          aria-label="关闭对话框"
        >
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}

export default function App() {
  const [initial] = useState(initialState);
  const [instances, setInstances] = useState(initial.instances);
  const [settings, setSettings] = useState(initial.settings);
  const [storageIssue, setStorageIssue] = useState(initial.error);
  const [page, setPage] = useState<Page>("home");
  const [selectedId, setSelectedId] = useState(initial.instances[0]?.id ?? "");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [modal, setModal] = useState<
    "import" | "help" | "delete" | "reset" | null
  >(null);
  const [toast, setToast] = useState<{
    message: string;
    error?: boolean;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const importLock = useRef(false);
  const [environment, setEnvironment] = useState<Environment | null>(null);
  const [checking, setChecking] = useState(false);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [activeTask, setActiveTask] = useState("");
  const [modsPath, setModsPath] = useState("");
  const [command, setCommand] = useState("");
  const [formError, setFormError] = useState("");
  const [importError, setImportError] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const selected = instances.find((i) => i.id === selectedId) ?? instances[0];
  const selectedTask = tasks.find((t) => t.id === activeTask) ?? tasks[0];
  useEffect(() => {
    setCommand("");
    setModsPath("");
    setFormError("");
  }, [selectedId]);
  const notify = useCallback(
    (message: string, error = false) => setToast({ message, error }),
    [],
  );
  useEffect(() => {
    if (toast) {
      const id = setTimeout(() => setToast(null), 5000);
      return () => clearTimeout(id);
    }
  }, [toast]);
  useEffect(() => {
    if (storageIssue) return;
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ instances, settings }),
      );
    } catch {
      setStorageIssue(
        "本地存储空间不足或不可用。当前更改尚未保存，请导出重要报告。",
      );
    }
  }, [instances, settings, storageIssue]);
  useEffect(() => {
    if (native && !initial.settings.workspace)
      void defaultWorkspace()
        .then((path) => {
          if (path)
            setSettings((s) => ({ ...s, workspace: s.workspace || path }));
        })
        .catch(() => {});
  }, [initial.settings.workspace]);
  const refreshEnvironment = useCallback(async () => {
    if (!native) {
      notify("环境检测需要桌面应用。浏览器可查看界面和导入预检报告。");
      return;
    }
    setChecking(true);
    try {
      setEnvironment(await getEnvironment(settings.python));
    } catch (error) {
      notify(String(error), true);
    } finally {
      setChecking(false);
    }
  }, [settings.python, notify]);
  const addReport = useCallback((report: Report) => {
    const item = makeInstance(report);
    setInstances((previous) => upsertInstance(previous, item));
    setSelectedId(item.id);
  }, []);
  const importFile = useCallback(
    async (file: File) => {
      if (!file.name.toLowerCase().endsWith(".json"))
        throw new Error(
          "浏览器中请选择预检 JSON 报告；.mrpack 和 Prism 目录请用桌面应用导入。",
        );
      if (file.size > 8 * 1024 * 1024)
        throw new Error("报告超过 8 MiB，请使用较小的预检报告。");
      const report = parseReport(JSON.parse(await file.text()));
      addReport(report);
      setModal(null);
      setPage("reports");
      notify(
        report.fatal
          ? "报告已导入，发现需要处理的阻断项。"
          : "预检报告已导入。",
      );
    },
    [addReport, notify],
  );
  const scanSource = useCallback(
    async (source: string) => {
      if (importLock.current) return;
      importLock.current = true;
      setBusy(true);
      setImportError("");
      const id = crypto.randomUUID();
      const startedAt = new Date().toISOString();
      setTasks((t) =>
        [
          {
            id,
            name: "整合包静态预检",
            startedAt,
            state: "running" as const,
            lines: [
              "开始读取整合包元数据",
              "源路径：" + source,
              "仅扫描元数据，不执行 Mod。",
            ],
          },
          ...t,
        ].slice(0, 30),
      );
      setActiveTask(id);
      try {
        const result = await inspectSource(source, settings.python);
        const report = parseReport(result.report);
        addReport(report);
        setTasks((t) =>
          t.map((task) =>
            task.id === id
              ? {
                  ...task,
                  state: report.fatal ? "blocked" : "done",
                  lines: [
                    ...task.lines,
                    ...report.findings.map(
                      (f) =>
                        "[" +
                        f.severity.toUpperCase() +
                        "] " +
                        f.code +
                        ": " +
                        f.message,
                    ),
                    "预检结束，用时 " +
                      (result.elapsedMs / 1000).toFixed(2) +
                      " 秒。",
                    "AOT / iOS 行为验证：NOT TESTED",
                  ],
                }
              : task,
          ),
        );
        setModal(null);
        setPage("reports");
        notify(
          report.fatal
            ? "预检结束，发现阻断项。"
            : "静态预检完成，报告已保存。",
        );
      } catch (error) {
        const message = String(error);
        setImportError(message);
        notify(message, true);
        setTasks((t) =>
          t.map((task) =>
            task.id === id
              ? {
                  ...task,
                  state: "failed",
                  lines: [...task.lines, "[ERROR] " + message],
                }
              : task,
          ),
        );
      } finally {
        importLock.current = false;
        setBusy(false);
      }
    },
    [settings.python, addReport, notify],
  );
  useEffect(() => {
    if (!native) return;
    let disposed = false;
    let cleanup: (() => void) | undefined;
    void import("@tauri-apps/api/webview")
      .then(({ getCurrentWebview }) =>
        getCurrentWebview().onDragDropEvent((event) => {
          if (
            !disposed &&
            event.payload.type === "drop" &&
            event.payload.paths.length
          )
            void scanSource(event.payload.paths[0]);
        }),
      )
      .then((unlisten) => {
        if (disposed) unlisten();
        else cleanup = unlisten;
      })
      .catch((error) => notify(String(error), true));
    return () => {
      disposed = true;
      cleanup?.();
    };
  }, [scanSource, notify]);
  async function chooseSource(directory: boolean) {
    try {
      const source = await pickSource(directory);
      if (source) await scanSource(source);
    } catch (error) {
      setImportError(String(error));
    }
  }
  async function download(name: string, content: string) {
    try {
      if (await saveDocument(name, content)) notify("文件已导出。");
    } catch (error) {
      notify("导出失败：" + String(error), true);
    }
  }
  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      notify("已复制。");
    } catch {
      notify("无法访问剪贴板，请使用导出按钮。", true);
    }
  }
  function navigate(next: Page) {
    setPage(next);
    setSearch("");
    setFilter("all");
  }
  function openImport() {
    setImportError("");
    setModal("import");
  }
  async function drop(event: DragEvent) {
    event.preventDefault();
    if (native) return;
    const file = event.dataTransfer.files[0];
    if (file)
      try {
        await importFile(file);
      } catch (error) {
        notify(String(error), true);
      }
  }
  const importButton = (
    <button className="button primary" onClick={openImport} disabled={busy}>
      <Plus size={17} />
      导入整合包
    </button>
  );
  const filteredInstances = instances.filter(
    (i) =>
      i.name.toLowerCase().includes(search.toLowerCase()) &&
      (filter === "all" ||
        (filter === "blocked" ? i.report.fatal : !i.report.fatal)),
  );
  const checks = environment?.checks ?? [
    { name: "Python", status: "unavailable", detail: "静态预检运行环境" },
    { name: "Java 25", status: "unavailable", detail: "Java 与 Native Image" },
    { name: "Xcode", status: "unavailable", detail: "iOS 编译与签名" },
  ];
  const readyChecks =
    environment?.checks.filter((c) => c.status === "ready").length ?? 0;
  function environmentPanel(compact = false) {
    return (
      <section
        className={"panel environment-panel " + (compact ? "compact" : "")}
      >
        <div className="section-heading">
          <h2>
            <Cpu size={17} />
            本机构建环境
          </h2>
          <button
            className="icon-button"
            aria-label="检测环境"
            onClick={() => void refreshEnvironment()}
            disabled={checking}
          >
            <RefreshCw size={16} className={checking ? "spin" : ""} />
          </button>
        </div>
        <p className="section-description">
          {environment
            ? environment.os + " / " + environment.arch
            : "连接本地工具，开始构建前的检查。"}
        </p>
        <div className="environment-list">
          {checks.map((check) => (
            <div className="environment-row" key={check.name}>
              <div className="tool-icon">
                {check.name.includes("Xcode") ? (
                  <Code2 size={18} />
                ) : check.name.includes("Java") ? (
                  <Box size={18} />
                ) : (
                  <Terminal size={18} />
                )}
              </div>
              <div className="tool-info">
                <strong>{check.name}</strong>
                <span title={check.detail}>{check.detail}</span>
              </div>
              {check.status === "ready" ? (
                <CheckCircle2
                  size={16}
                  className="green-text"
                  aria-label="可用"
                />
              ) : (
                <span className="muted small">
                  {environment
                    ? check.status === "missing"
                      ? "缺失"
                      : "不可用"
                    : "未检测"}
                </span>
              )}
            </div>
          ))}
        </div>
        <button
          className="button subtle full"
          onClick={() => void refreshEnvironment()}
          disabled={checking}
        >
          {checking ? (
            <LoaderCircle size={16} className="spin" />
          ) : (
            <RefreshCw size={15} />
          )}
          {checking ? "正在检测…" : "检测本机环境"}
        </button>
        {!compact && (
          <div className="inline-note">
            <CircleAlert size={16} />
            <span>
              iOS AOT 编译与签名需要 macOS Apple
              Silicon。工具可用性检测不代表完整 iOS 工具链已验证。
            </span>
          </div>
        )}
      </section>
    );
  }
  function instanceCard(instance: Instance) {
    return (
      <article className="instance-card" key={instance.id}>
        <button
          className="instance-open"
          onClick={() => {
            setSelectedId(instance.id);
            navigate("reports");
          }}
          aria-label={"查看 " + instance.name + " 的报告"}
        >
          <div className="instance-art">
            <img src="/landscape.svg" alt="" />
            <span className="instance-art-icon">
              <Package size={22} />
            </span>
            <Badge tone={instance.report.fatal ? "red" : "amber"}>
              {instance.report.fatal ? "存在阻断" : "待验证"}
            </Badge>
          </div>
          <div className="instance-body">
            <h3>
              {instance.name}
              <ArrowUpRight size={15} />
            </h3>
            <p>
              Fabric {instance.report.fabric_loader_version ?? "版本待核验"}
              <span>·</span>
              {instance.report.target_minecraft}
            </p>
            <div className="instance-meta">
              <span>
                <Box size={13} />
                {instance.report.mods.length} 个已扫描 Mod
              </span>
              <span>{date(instance.importedAt)}</span>
            </div>
          </div>
        </button>
      </article>
    );
  }
  return (
    <div
      className="app-shell"
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => void drop(e)}
    >
      <aside className="sidebar">
        <button
          className="brand"
          onClick={() => navigate("home")}
          aria-label="FabricAOT 工作台"
        >
          <img src="/mark.svg" alt="" />
          <div>
            <strong>
              FabricAOT<span>实验版</span>
            </strong>
            <small>YOUR WORLD. COMPILED.</small>
          </div>
        </button>
        <div className="workspace-label">
          个人工作空间<span>LOCAL</span>
        </div>
        <nav aria-label="主导航">
          {pages.map((item) => (
            <button
              className={"nav-item " + (page === item.id ? "active" : "")}
              aria-label={item.label}
              key={item.id}
              onClick={() => navigate(item.id)}
              aria-current={page === item.id ? "page" : undefined}
            >
              <item.icon size={18} />
              <span>{item.label}</span>
              {item.id === "instances" && instances.length > 0 && (
                <small>{instances.length}</small>
              )}
              {item.id === "builds" && busy && (
                <span className="status-dot green" />
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-note">
          <div className="tiny-cube">
            <Box size={18} />
          </div>
          <strong>从桌面，到口袋。</strong>
          <p>
            为 iPhone 构建你的
            <br />
            Fabric 世界。
          </p>
          <span>
            26.1.2 <span className="dot-separator">/</span> Java 25
          </span>
        </div>
        <div className="sidebar-bottom">
          <button
            className={"nav-item " + (page === "settings" ? "active" : "")}
            aria-label="设置"
            onClick={() => navigate("settings")}
          >
            <Settings2 size={18} />
            <span>设置</span>
          </button>
          <button className="nav-item" aria-label="使用指南" onClick={() => setModal("help")}>
            <HelpCircle size={18} />
            <span>使用指南</span>
            <ArrowUpRight size={14} />
          </button>
          <div className="local-status">
            <span className="status-dot green" />
            <div>
              <strong>本地工作区</strong>
              <small>
                {native ? "桌面应用 · 0.1.0" : "浏览器预览 · 0.1.0"}
              </small>
            </div>
            <HardDrive size={16} />
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            工作空间
            <ChevronRight size={14} />
            <strong>
              {page === "settings"
                ? "设置"
                : pages.find((p) => p.id === page)?.label}
            </strong>
          </div>
          <div className="topbar-right">
            <span className="platform">
              <Monitor size={14} />
              {detectPlatform(environment)}
            </span>
            <span className="top-divider" />
            <button
              className="icon-button"
              aria-label="打开使用指南"
              onClick={() => setModal("help")}
            >
              <HelpCircle size={18} />
            </button>
          </div>
        </header>
        <main id="main-content">
          {storageIssue && (
            <div role="alert" className="notice warning">
              <TriangleAlert size={18} />
              <span>{storageIssue}</span>
              <button onClick={() => navigate("settings")}>
                打开设置
                <ArrowRight size={14} />
              </button>
            </div>
          )}
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                {page === "home"
                  ? "MAKE ROOM FOR YOUR NEXT WORLD"
                  : "FABRICAOT / LOCAL WORKSPACE"}
              </div>
              <h1>
                {page === "home"
                  ? "你的世界，由你构建。"
                  : page === "settings"
                    ? "工作台设置"
                    : pages.find((p) => p.id === page)?.label}
              </h1>
              <p>
                {page === "home"
                  ? "管理整合包，了解兼容性，开启下一次本地构建。"
                  : page === "instances"
                    ? "你的整合包和预检记录，都保存在本机。"
                    : page === "reports"
                      ? "从真实元数据出发，逐项了解整合包的适配要求。"
                      : page === "builds"
                        ? "准备构建配置，查看真实任务记录。"
                        : page === "environment"
                          ? "查看本机工具状态与平台支持范围。"
                          : "配置本地工具和项目路径。"}
              </p>
            </div>
            {page === "home" || page === "instances" ? (
              importButton
            ) : page === "reports" && selected ? (
              <button
                className="button secondary"
                onClick={() =>
                  void download(
                    "fabricaot-preflight.json",
                    JSON.stringify(selected.report, null, 2),
                  )
                }
              >
                <ArrowDownToLine size={16} />
                导出报告
              </button>
            ) : null}
          </div>

          {page === "home" && (
            <>
              <section className="hero">
                <img
                  src="/landscape.svg"
                  alt="原创方块山林插画"
                  className="hero-art"
                />
                <div className="hero-shade" />
                <div className="hero-content">
                  <span className="hero-label">
                    <span className="status-dot" />
                    BUILT LOCALLY. MADE FOR YOUR IPHONE.
                  </span>
                  <h2>
                    下一段冒险，
                    <br />
                    从这里构建<span>。</span>
                  </h2>
                  <p>
                    从熟悉的整合包开始，
                    <br />
                    探索 Fabric 世界的更多可能。
                  </p>
                  <button
                    className="button hero-button"
                    onClick={openImport}
                    disabled={busy}
                  >
                    <Import size={17} />
                    导入你的第一个整合包
                    <ArrowRight size={17} />
                  </button>
                  <div className="hero-tags">
                    <span>
                      <Box size={13} />
                      Minecraft 26.1.2
                    </span>
                    <span>
                      <Layers3 size={13} />
                      Fabric Only
                    </span>
                    <span>
                      <Smartphone size={13} />
                      iOS ARM64
                    </span>
                  </div>
                </div>
                <div className="hero-caption">
                  <span className="status-dot" />
                  THE OVERWORLD, REIMAGINED<span>01 / 01</span>
                </div>
              </section>
              <div className="home-grid">
                <div className="home-main">
                  <div className="section-heading library-heading">
                    <h2>
                      我的实例
                      <span className="count">
                        {instances.length.toString().padStart(2, "0")}
                      </span>
                    </h2>
                    <button
                      className="text-button"
                      onClick={() => navigate("instances")}
                    >
                      查看全部
                      <ArrowRight size={14} />
                    </button>
                  </div>
                  {instances.length ? (
                    <div className="instance-grid home-instances">
                      {instances.slice(0, 2).map(instanceCard)}
                    </div>
                  ) : (
                    <button
                      className="import-zone"
                      onClick={openImport}
                      disabled={busy}
                    >
                      <span className="import-zone-icon">
                        <Plus size={23} />
                      </span>
                      <strong>给下一个世界留个位置</strong>
                      <span>导入 .mrpack 或 Prism 实例，开始静态预检</span>
                      <small>也可以拖入预检 JSON 报告</small>
                    </button>
                  )}
                  <section className="workflow">
                    <div className="section-heading">
                      <h2>从整合包到本地构建</h2>
                      <span className="small muted">一步一步，清晰可见</span>
                    </div>
                    <div className="workflow-steps">
                      {[
                        {
                          icon: FolderOpen,
                          title: "导入实例",
                          subtitle: "读取本地整合包",
                          action: openImport,
                        },
                        {
                          icon: ShieldCheck,
                          title: "检查兼容性",
                          subtitle: "了解风险与阻断项",
                          action: () => navigate("reports"),
                        },
                        {
                          icon: Smartphone,
                          title: "准备构建",
                          subtitle: "在 Mac 上编译与签名",
                          action: () => navigate("builds"),
                        },
                      ].map((s, i) => (
                        <button key={s.title} onClick={s.action}>
                          <span className="step-icon">
                            <s.icon size={18} />
                            <small>0{i + 1}</small>
                          </span>
                          <strong>{s.title}</strong>
                          <span>{s.subtitle}</span>
                          {i < 2 && (
                            <ChevronRight className="step-arrow" size={14} />
                          )}
                        </button>
                      ))}
                    </div>
                  </section>
                </div>
                <div className="home-side">
                  {environmentPanel(true)}
                  <button
                    className="guide-card"
                    onClick={() => setModal("help")}
                  >
                    <div>
                      <span className="eyebrow">A LITTLE HELP</span>
                      <h3>第一次使用？</h3>
                      <p>从导入到构建，了解完整流程。</p>
                      <span className="guide-link">
                        查看入门指南
                        <ArrowUpRight size={14} />
                      </span>
                    </div>
                    <div className="guide-icon">
                      <FileCheck2 size={30} />
                    </div>
                  </button>
                </div>
              </div>
              <footer className="page-footer">
                <span>
                  <ShieldCheck size={13} />
                  文件与报告保存在本机
                </span>
                <span>独立非官方项目 · 静态预检不代表真机兼容性</span>
              </footer>
            </>
          )}

          {page === "instances" && (
            <>
              <div className="toolbar">
                <label className="search-field">
                  <Search size={16} />
                  <input
                    aria-label="搜索实例"
                    placeholder="搜索你的实例…"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                </label>
                <label className="filter-field">
                  <ListFilter size={15} />
                  <select
                    aria-label="筛选实例"
                    value={filter}
                    onChange={(e) => setFilter(e.target.value)}
                  >
                    <option value="all">全部实例</option>
                    <option value="clear">无静态阻断</option>
                    <option value="blocked">存在阻断</option>
                  </select>
                </label>
                <span className="small muted">
                  {filteredInstances.length} 个实例
                </span>
              </div>
              {filteredInstances.length ? (
                <div className="instance-grid">
                  {filteredInstances.map(instanceCard)}
                  <button className="add-instance" onClick={openImport}>
                    <Plus size={24} />
                    <span>导入更多整合包</span>
                  </button>
                </div>
              ) : (
                <section className="panel">
                  <Empty
                    title={
                      instances.length
                        ? "没有找到匹配的实例"
                        : "你的实例库还是空的"
                    }
                    action={
                      instances.length ? (
                        <button
                          className="button secondary"
                          onClick={() => {
                            setSearch("");
                            setFilter("all");
                          }}
                        >
                          清除筛选
                        </button>
                      ) : (
                        importButton
                      )
                    }
                  >
                    {instances.length
                      ? "试试其他关键词，或调整筛选条件。"
                      : "选择本地整合包，或导入一份已有的预检报告。"}
                  </Empty>
                </section>
              )}
            </>
          )}

          {page === "reports" &&
            (selected ? (
              <>
                <div className="report-selector">
                  <label>
                    当前实例
                    <select
                      aria-label="当前实例"
                      value={selected.id}
                      onChange={(e) => setSelectedId(e.target.value)}
                    >
                      {instances.map((i) => (
                        <option key={i.id} value={i.id}>
                          {i.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="report-actions">
                    {native && (
                      <button
                        className="button secondary"
                        onClick={() => void scanSource(selected.report.source)}
                        disabled={busy}
                      >
                        <RefreshCw size={15} className={busy ? "spin" : ""} />
                        重新预检
                      </button>
                    )}
                    <button
                      className="icon-button danger"
                      aria-label="移除实例记录"
                      onClick={() => setModal("delete")}
                    >
                      <Trash2 size={17} />
                    </button>
                  </div>
                </div>
                <div
                  className={
                    "notice " + (selected.report.fatal ? "error" : "info")
                  }
                >
                  <CircleAlert size={19} />
                  <div>
                    <strong>
                      {selected.report.fatal
                        ? "发现静态阻断项，请先处理后再构建。"
                        : "元数据预检结束，实际兼容性仍待验证。"}
                    </strong>
                    <p>
                      此报告仅静态读取元数据。Mod 的 iOS / AOT
                      行为尚未测试，不能标记为 VERIFIED。
                    </p>
                  </div>
                </div>
                <section className="report-summary">
                  <div>
                    <span>已扫描 Mod</span>
                    <strong>
                      {selected.report.mods.length}
                      <small>个</small>
                    </strong>
                  </div>
                  <div>
                    <span>阻断问题</span>
                    <strong
                      className={
                        selected.report.findings.some(
                          (f) => f.severity === "error",
                        )
                          ? "red-text"
                          : ""
                      }
                    >
                      {
                        selected.report.findings.filter(
                          (f) => f.severity === "error",
                        ).length
                      }
                      <small>项</small>
                    </strong>
                  </div>
                  <div>
                    <span>待关注事项</span>
                    <strong className="amber-text">
                      {
                        selected.report.findings.filter(
                          (f) => f.severity === "warning",
                        ).length
                      }
                      <small>项</small>
                    </strong>
                  </div>
                  <div>
                    <span>真机行为验证</span>
                    <strong className="unverified">未测试</strong>
                  </div>
                </section>
                <section className="panel findings-panel">
                  <div className="section-heading">
                    <h2>诊断事项</h2>
                    <Badge>
                      {selected.report.source_type === "mrpack"
                        ? "Modrinth"
                        : selected.report.source_type === "prism_or_folder"
                          ? "Prism / 本地目录"
                          : "未知来源"}
                    </Badge>
                  </div>
                  <div className="source-path">
                    <Folder size={14} />
                    <span title={selected.report.source}>
                      {selected.report.source}
                    </span>
                  </div>
                  <div className="filter-tabs" aria-label="诊断筛选">
                    {[
                      { key: "all", label: "全部" },
                      { key: "error", label: "阻断" },
                      { key: "warning", label: "待关注" },
                      { key: "info", label: "信息" },
                    ].map((f) => (
                      <button
                        key={f.key}
                        className={filter === f.key ? "active" : ""}
                        onClick={() => setFilter(f.key)}
                        aria-pressed={filter === f.key}
                      >
                        {f.label}
                        <span>
                          {
                            selected.report.findings.filter(
                              (item) =>
                                f.key === "all" || item.severity === f.key,
                            ).length
                          }
                        </span>
                      </button>
                    ))}
                  </div>
                  {selected.report.findings.filter(
                    (f) => filter === "all" || f.severity === filter,
                  ).length ? (
                    <div className="findings">
                      {selected.report.findings
                        .filter(
                          (f) => filter === "all" || f.severity === filter,
                        )
                        .map((f, i) => (
                          <div className={"finding " + f.severity} key={i}>
                            {f.severity === "error" ? (
                              <CircleAlert size={18} />
                            ) : f.severity === "warning" ? (
                              <TriangleAlert size={18} />
                            ) : (
                              <Circle size={16} />
                            )}
                            <div>
                              <strong>{findingLabels[f.code] ?? f.code}</strong>
                              <p>{f.message}</p>
                              <code>{f.code}</code>
                            </div>
                            <span className="small">
                              {f.severity === "error"
                                ? "阻断"
                                : f.severity === "warning"
                                  ? "待关注"
                                  : "信息"}
                            </span>
                          </div>
                        ))}
                    </div>
                  ) : (
                    <div className="quiet-empty">当前筛选下没有诊断事项。</div>
                  )}
                </section>
                <section className="panel mods-panel">
                  <div className="section-heading">
                    <h2>
                      Mod 元数据
                      <span className="count">
                        {selected.report.mods.length}
                      </span>
                    </h2>
                    <span className="small muted">
                      远程清单中的 JAR 可能尚未下载
                    </span>
                  </div>
                  {selected.report.mods.length ? (
                    <div className="table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Mod / 版本</th>
                            <th>构建期机制</th>
                            <th>环境</th>
                            <th>iOS / AOT 状态</th>
                          </tr>
                        </thead>
                        <tbody>
                          {selected.report.mods.map((m, i) => (
                            <tr key={m.id + i}>
                              <td>
                                <strong>{m.id}</strong>
                                <span className="table-sub">{m.version}</span>
                              </td>
                              <td>
                                <div className="mechanisms">
                                  {m.has_mixins && <span>Mixin</span>}
                                  {m.has_class_tweaker && (
                                    <span>Class Tweaker</span>
                                  )}
                                  {m.has_entrypoints && <span>Entrypoint</span>}
                                  {m.nested_jar_count > 0 && (
                                    <span>嵌套 JAR ×{m.nested_jar_count}</span>
                                  )}
                                  {m.has_language_adapters && (
                                    <span>Language Adapter</span>
                                  )}
                                  {m.bundled_native_count > 0 && (
                                    <span>
                                      原生库 ×{m.bundled_native_count}
                                    </span>
                                  )}
                                  {!m.has_mixins &&
                                    !m.has_entrypoints &&
                                    !m.has_class_tweaker &&
                                    !m.nested_jar_count &&
                                    !m.has_language_adapters &&
                                    !m.bundled_native_count &&
                                    "—"}
                                </div>
                              </td>
                              <td>
                                {m.environment === "*"
                                  ? "通用"
                                  : m.environment === "client"
                                    ? "客户端"
                                    : m.environment === "server"
                                      ? "服务端"
                                      : m.environment}
                              </td>
                              <td>
                                <Badge tone="amber">未测试</Badge>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="quiet-empty">
                      报告没有可读取的本地 Mod 元数据。
                    </div>
                  )}
                </section>
              </>
            ) : (
              <section className="panel">
                <Empty
                  title="还没有兼容性报告"
                  icon={<ShieldCheck size={28} />}
                  action={importButton}
                >
                  导入整合包或预检 JSON，查看具体的适配要求。
                </Empty>
              </section>
            ))}

          {page === "builds" && (
            <>
              <div className="notice info">
                <CircleAlert size={18} />
                <div>
                  <strong>
                    首版已接入静态预检；完整编译、签名和 IPA
                    导出按构建文档操作。
                  </strong>
                  <p>
                    下方可以生成构建准备命令。实际 iOS 构建由 macOS Apple
                    Silicon 完成。
                  </p>
                </div>
              </div>
              <div className="build-grid">
                <section className="panel build-config">
                  <div className="section-heading">
                    <h2>
                      <Settings2 size={17} />
                      构建准备
                    </h2>
                    <Badge>iOS ARM64</Badge>
                  </div>
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      setFormError("");
                      try {
                        setCommand(prepareCommand(settings, modsPath));
                      } catch (error) {
                        setFormError(String(error));
                      }
                    }}
                  >
                    <label className="field">
                      构建配置文件
                      <input
                        value={settings.config}
                        onChange={(e) => {
                          setSettings({ ...settings, config: e.target.value });
                          setCommand("");
                        }}
                        placeholder="mcfao.local.json"
                        required
                      />
                      <small>相对于项目目录；沿用现有构建配置。</small>
                    </label>
                    <label className="field">
                      已导入实例
                      <select
                        value={selected?.id ?? ""}
                        onChange={(e) => {
                          setSelectedId(e.target.value);
                          setModsPath("");
                          setCommand("");
                        }}
                      >
                        <option value="" disabled>
                          先导入整合包
                        </option>
                        {instances.map((i) => (
                          <option value={i.id} key={i.id}>
                            {i.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="field">
                      本地 Mod 目录
                      <input
                        aria-label="本地 Mod 目录"
                        value={modsPath}
                        onChange={(e) => {
                          setModsPath(e.target.value);
                          setCommand("");
                        }}
                        placeholder="/path/to/instance/.minecraft/mods"
                        required
                      />
                      <small>.mrpack 需先取得并验证实际 Mod 文件。</small>
                    </label>
                    <label className="field">
                      输出目录
                      <input
                        value={settings.output}
                        onChange={(e) => {
                          setSettings({ ...settings, output: e.target.value });
                          setCommand("");
                        }}
                        required
                      />
                      <small>建议为每轮构建设置独立目录。</small>
                    </label>
                    {formError && (
                      <p className="form-error" role="alert">
                        {formError}
                      </p>
                    )}
                    <button
                      className="button primary full"
                      type="submit"
                      disabled={!selected || selected.report.fatal}
                    >
                      <Terminal size={16} />
                      生成准备命令
                      <ArrowRight size={16} />
                    </button>
                    {!settings.workspace && (
                      <button
                        className="text-button setup-link"
                        type="button"
                        onClick={() => navigate("settings")}
                      >
                        先设置项目目录
                        <ArrowRight size={14} />
                      </button>
                    )}
                  </form>
                </section>
                <section className="panel command-panel">
                  <div className="section-heading">
                    <h2>
                      <Terminal size={17} />
                      执行预览
                    </h2>
                    <span className="small muted">macOS / zsh</span>
                  </div>
                  {command ? (
                    <>
                      <div className="command-label">
                        <span className="status-dot green" />
                        元数据准备 · --prepare-only
                      </div>
                      <pre className="command-text">{command}</pre>
                      <div className="command-actions">
                        <button
                          className="button secondary"
                          onClick={() => void copy(command)}
                        >
                          <Copy size={15} />
                          复制命令
                        </button>
                        <button
                          className="button secondary"
                          onClick={() =>
                            void download(
                              "fabricaot-build-preparation.txt",
                              buildInstructions(settings, command),
                            )
                          }
                        >
                          <ArrowDownToLine size={15} />
                          导出说明
                        </button>
                      </div>
                      <p className="small muted">
                        在终端进入项目目录后执行。此操作只准备元数据，不会执行未审计的
                        Mod。
                      </p>
                    </>
                  ) : (
                    <Empty title="准备好再出发" icon={<Terminal size={25} />}>
                      填写左侧配置，生成可检查、可复制的准备命令。
                    </Empty>
                  )}
                  <div className="build-stages">
                    <span>
                      <FileCheck2 size={16} />
                      静态预检<b>已接入</b>
                    </span>
                    <span>
                      <Cpu size={16} />
                      AOT 编译<b>使用命令行</b>
                    </span>
                    <span>
                      <Smartphone size={16} />
                      签名 / IPA<b>使用命令行</b>
                    </span>
                  </div>
                </section>
              </div>
              <section className="panel logs-panel">
                <div className="section-heading">
                  <h2>
                    <Terminal size={17} />
                    本次会话任务
                  </h2>
                  {selectedTask && (
                    <button
                      className="text-button"
                      onClick={() =>
                        void download(
                          "fabricaot-task-log.txt",
                          selectedTask.startedAt +
                            "\n" +
                            selectedTask.lines.join("\n"),
                        )
                      }
                    >
                      <ArrowDownToLine size={14} />
                      导出日志
                    </button>
                  )}
                </div>
                {tasks.length ? (
                  <div className="logs-layout">
                    <div className="task-list">
                      {tasks.map((task) => (
                        <button
                          className={
                            task.id === selectedTask?.id ? "active" : ""
                          }
                          key={task.id}
                          onClick={() => setActiveTask(task.id)}
                        >
                          {task.state === "running" ? (
                            <LoaderCircle size={16} className="spin" />
                          ) : task.state === "done" ? (
                            <CheckCircle2 size={16} className="green-text" />
                          ) : (
                            <TriangleAlert size={16} className="amber-text" />
                          )}
                          <div>
                            <strong>{task.name}</strong>
                            <span>{date(task.startedAt)}</span>
                          </div>
                          <small>
                            {task.state === "running"
                              ? "运行中"
                              : task.state === "done"
                                ? "已结束"
                                : task.state === "blocked"
                                  ? "有阻断"
                                  : "失败"}
                          </small>
                        </button>
                      ))}
                    </div>
                    <pre className="log-output" aria-label="任务日志">
                      {selectedTask?.lines.join("\n")}
                    </pre>
                  </div>
                ) : (
                  <div className="quiet-empty">
                    <Clock3 size={18} />
                    <span>
                      还没有运行任务。桌面应用中导入整合包后，预检日志会显示在这里。
                    </span>
                  </div>
                )}
              </section>
            </>
          )}

          {page === "environment" && (
            <div className="environment-grid">
              {environmentPanel()}
              <section className="panel platform-panel">
                <div className="section-heading">
                  <h2>
                    <Monitor size={17} />
                    平台能力
                  </h2>
                  <Badge tone="green">跨平台界面</Badge>
                </div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>功能</th>
                        <th>macOS</th>
                        <th>Windows</th>
                        <th>Linux</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td>实例 / 报告管理</td>
                        <td>支持</td>
                        <td>支持¹</td>
                        <td>支持¹</td>
                      </tr>
                      <tr>
                        <td>静态预检</td>
                        <td>Python 3</td>
                        <td>Python 3¹</td>
                        <td>Python 3¹</td>
                      </tr>
                      <tr>
                        <td>iOS AOT / 签名</td>
                        <td>Apple Silicon</td>
                        <td>需 Mac</td>
                        <td>需 Mac</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <p className="small muted">
                  ¹ 已提供平台适配代码；Windows / Linux
                  原生打包与运行仍需在对应系统验收。
                </p>
                <div className="platform-summary">
                  <div>
                    <Monitor size={20} />
                    <span>本机已就绪检查</span>
                    <strong>
                      {environment
                        ? readyChecks + " / " + environment.checks.length
                        : "待检测"}
                    </strong>
                  </div>
                  <div>
                    <Smartphone size={20} />
                    <span>远程 Mac 构建</span>
                    <strong>后续接入</strong>
                  </div>
                </div>
              </section>
            </div>
          )}

          {page === "settings" && (
            <div className="settings-layout">
              <section className="panel settings-panel">
                <div className="section-heading">
                  <h2>
                    <FolderOpen size={18} />
                    本地路径
                  </h2>
                  <span className="small muted">更改自动保存</span>
                </div>
                <label className="field">
                  FabricAOT 项目目录
                  <div className="input-with-button">
                    <input
                      value={settings.workspace}
                      onChange={(e) => {
                        setSettings({ ...settings, workspace: e.target.value });
                        setCommand("");
                      }}
                      placeholder="选择 MCFAO 仓库根目录"
                    />
                    {native && (
                      <button
                        className="icon-button"
                        aria-label="选择项目目录"
                        onClick={() =>
                          void pickWorkspace()
                            .then((path) => {
                              if (path) {
                                setSettings((s) => ({ ...s, workspace: path }));
                                setCommand("");
                              }
                            })
                            .catch((error) => notify(String(error), true))
                        }
                      >
                        <FolderOpen size={18} />
                      </button>
                    )}
                  </div>
                  <small>
                    用于生成构建命令。静态预检使用应用内附带的预检脚本。
                  </small>
                </label>
                <label className="field">
                  Python 可执行文件
                  <input
                    value={settings.python}
                    onChange={(e) => {
                      setSettings({ ...settings, python: e.target.value });
                      setCommand("");
                      setEnvironment(null);
                    }}
                    placeholder="留空使用系统 python3（Windows 为 python）"
                  />
                  <small>只填写程序名或完整路径，不附加命令行参数。</small>
                </label>
                <div className="inline-note">
                  <HardDrive size={17} />
                  <span>
                    实例、报告和设置保存在本机应用存储中。任务日志保留于本次会话，可单独导出。
                  </span>
                </div>
              </section>
              <section className="panel about-panel">
                <img src="/mark.svg" alt="" width="52" height="52" />
                <h2>FabricAOT</h2>
                <span className="version">Desktop 0.1.0 · Experimental</span>
                <p>你的世界，由你构建。</p>
                <div className="about-spec">
                  <span>
                    Minecraft<strong>26.1.2</strong>
                  </span>
                  <span>
                    运行时<strong>Java 25 · AOT</strong>
                  </span>
                  <span>
                    目标平台<strong>iOS ARM64</strong>
                  </span>
                </div>
                <p className="small muted">
                  独立非官方项目，与 Mojang / Microsoft
                  无关联。游戏资产由用户本地合法提供。
                </p>
              </section>
              {storageIssue && (
                <section className="panel recovery-panel">
                  <h2>本地记录恢复</h2>
                  <p>{storageIssue}</p>
                  <div className="command-actions">
                    <button
                      className="button secondary"
                      onClick={() => {
                        try {
                          void download(
                            "fabricaot-storage-backup.json",
                            localStorage.getItem(STORAGE_KEY) ?? "{}",
                          );
                        } catch (error) {
                          notify(String(error), true);
                        }
                      }}
                    >
                      导出原始记录
                    </button>
                    <button
                      className="button secondary"
                      onClick={() => setModal("reset")}
                    >
                      重置本地记录
                    </button>
                  </div>
                </section>
              )}
            </div>
          )}
        </main>
        <div className="statusbar">
          <span>
            <span className="status-dot green" />
            {busy ? "正在进行静态预检…" : "工作区就绪"}
            {busy && <LoaderCircle size={12} className="spin" />}
          </span>
          <span>
            Fabric Only<span className="dot-separator">·</span>26.1.2
            <span className="dot-separator">·</span>Experimental
          </span>
        </div>
      </div>
      <input
        type="file"
        ref={fileInput}
        hidden
        accept="application/json,.json"
        aria-label="导入预检 JSON 报告"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file)
            void importFile(file).catch((error) => {
              setImportError(String(error));
              notify(String(error), true);
            });
          e.target.value = "";
        }}
      />
      {modal === "import" && (
        <Modal title="导入你的整合包" onClose={() => setModal(null)}>
          <p className="modal-description">
            选择本地来源，创建实例并读取静态元数据。
          </p>
          <div className="import-options">
            <button
              onClick={() => void chooseSource(false)}
              disabled={busy || !native}
            >
              <span className="option-icon">
                <FileUp size={24} />
              </span>
              <div>
                <strong>Modrinth 整合包</strong>
                <span>选择 .mrpack 文件</span>
              </div>
              <ChevronRight size={18} />
            </button>
            <button
              onClick={() => void chooseSource(true)}
              disabled={busy || !native}
            >
              <span className="option-icon">
                <FolderOpen size={24} />
              </span>
              <div>
                <strong>Prism Launcher 实例</strong>
                <span>选择含 mmc-pack.json 的实例目录</span>
              </div>
              <ChevronRight size={18} />
            </button>
            <button onClick={() => fileInput.current?.click()} disabled={busy}>
              <span className="option-icon">
                <FileJson2 size={24} />
              </span>
              <div>
                <strong>已有预检报告</strong>
                <span>导入 tools/preflight.py 生成的 JSON</span>
              </div>
              <ChevronRight size={18} />
            </button>
          </div>
          {!native && (
            <div className="inline-note">
              <Monitor size={17} />
              <span>
                当前为浏览器预览，可导入 JSON
                报告。原始整合包和目录导入请启动桌面应用。
              </span>
            </div>
          )}
          {busy && (
            <p className="import-progress" role="status">
              <LoaderCircle className="spin" size={18} />
              正在扫描元数据，结果将自动保存…
            </p>
          )}
          {importError && (
            <p className="form-error" role="alert">
              {importError}
            </p>
          )}
          <div className="modal-footnote">
            <ShieldCheck size={15} />
            仅读取元数据，不执行 Mod 或构建脚本。
          </div>
        </Modal>
      )}
      {modal === "help" && (
        <Modal title="从这里开始" onClose={() => setModal(null)} wide>
          <p className="modal-description">
            把复杂的构建过程，拆成清晰的每一步。
          </p>
          <ol className="help-steps">
            <li>
              <span>01</span>
              <div>
                <h3>导入与预检</h3>
                <p>
                  在桌面应用中选择 .mrpack 或 Prism
                  实例。也可先运行预检脚本，再导入 JSON 报告。
                </p>
                <code>
                  python3 tools/preflight.py /path/to/pack.mrpack &gt;
                  report.json
                </code>
              </div>
            </li>
            <li>
              <span>02</span>
              <div>
                <h3>读懂兼容性报告</h3>
                <p>
                  先处理版本、加载器和路径等阻断项，再评估
                  Mixin、嵌套依赖与原生库。静态扫描不会授予 VERIFIED 状态。
                </p>
              </div>
            </li>
            <li>
              <span>03</span>
              <div>
                <h3>在 Mac 上准备构建</h3>
                <p>
                  在设置中指定项目目录，再到“构建与日志”填写配置和 Mod
                  目录。生成的命令只进行元数据准备。
                </p>
              </div>
            </li>
            <li>
              <span>04</span>
              <div>
                <h3>编译、签名与设备验收</h3>
                <p>
                  完整流程见仓库 docs/BUILDING.md。设备可玩性与 Mod 行为按
                  docs/ACCEPTANCE.md 单独验收。
                </p>
              </div>
            </li>
          </ol>
          <button
            className="button primary full"
            onClick={() => {
              setModal(null);
              openImport();
            }}
          >
            开始导入
            <ArrowRight size={17} />
          </button>
        </Modal>
      )}
      {modal === "delete" && (
        <Modal title="移除实例记录" onClose={() => setModal(null)}>
          <p className="modal-description">
            移除“{selected?.name}”在工作台中的记录。源整合包和本地存档会保留。
          </p>
          <div className="modal-buttons">
            <button className="button secondary" onClick={() => setModal(null)}>
              取消
            </button>
            <button
              className="button destructive"
              onClick={() => {
                setInstances((i) =>
                  i.filter((item) => item.id !== selected?.id),
                );
                setSelectedId("");
                setModal(null);
                notify("实例记录已移除。");
              }}
            >
              移除记录
            </button>
          </div>
        </Modal>
      )}
      {modal === "reset" && (
        <Modal title="重置本地记录" onClose={() => setModal(null)}>
          <p className="modal-description">
            此操作将替换工作台保存的实例和设置。请先导出原始记录；源整合包和存档会保留。
          </p>
          <div className="modal-buttons">
            <button className="button secondary" onClick={() => setModal(null)}>
              取消
            </button>
            <button
              className="button destructive"
              onClick={() => {
                try {
                  localStorage.removeItem(STORAGE_KEY);
                  setInstances([]);
                  setSettings(DEFAULT_SETTINGS);
                  setSelectedId("");
                  setCommand("");
                  setStorageIssue("");
                  setModal(null);
                  notify("本地记录已重置。");
                } catch (error) {
                  notify(String(error), true);
                }
              }}
            >
              确认重置
            </button>
          </div>
        </Modal>
      )}
      {toast && (
        <div
          className={"toast " + (toast.error ? "error" : "")}
          role={toast.error ? "alert" : "status"}
        >
          {toast.error ? <CircleAlert size={18} /> : <Check size={18} />}
          <span>{toast.message}</span>
          <button
            className="icon-button"
            aria-label="关闭提示"
            onClick={() => setToast(null)}
          >
            <X size={15} />
          </button>
        </div>
      )}
    </div>
  );
}
