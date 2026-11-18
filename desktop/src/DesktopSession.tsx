import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronLeft,
  Files,
  FolderOpen,
  HardDrive,
  LoaderCircle,
  PackageCheck,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import {
  AccountPanel,
  AccountProvider,
  accountIsVerified,
  useAccount,
} from "./Account";
import { choosePath, defaultWorkspace, native, workbench } from "./bridge";
import { StepBody } from "./MotionPrimitives";
import { useStepContent } from "./motion";
import {
  ONBOARDING_KEY,
  emptyOnboarding,
  onboardingStep,
  readOnboarding,
  storageFormPatch,
  type OnboardingState,
} from "./onboarding";
import {
  FORM_KEY,
  LEGACY_FORM_KEY,
  migrateLegacyKeys,
  readWithLegacy,
} from "./storage";
import { storageRoles, unifiedStoragePaths } from "./storageManagement";
import {
  StorageChangeDialog,
  type StorageChangePlan,
  type StoragePolicy,
} from "./StorageChangeDialog";
import { defaultForm, restoreForm, type BuildForm } from "./workflow";
import {
  applyAccent,
  applyTheme,
  getSystemAccent,
  readAccentPreference,
  readThemePreference,
  resolveTheme,
  syncWindowTheme,
  systemPrefersDark,
} from "./theme";
import "./onboarding.css";

function initialState() {
  try {
    return readOnboarding(localStorage.getItem(ONBOARDING_KEY));
  } catch {
    return { ...emptyOnboarding };
  }
}
function initialForm(): { form: BuildForm; issue: string } {
  try {
    migrateLegacyKeys(localStorage);
    return {
      form: restoreForm(
        readWithLegacy(localStorage, FORM_KEY, LEGACY_FORM_KEY),
      ),
      issue: "",
    };
  } catch {
    return {
      form: { ...defaultForm },
      issue: "现有构建设置无法读取。请先备份或修复本地记录，再配置储存目录。",
    };
  }
}

export function DesktopSession({ children }: { children: ReactNode }) {
  const [initial] = useState(initialState);
  return (
    <AccountProvider revalidate={initial.completed}>
      <SessionGate initial={initial}>{children}</SessionGate>
    </AccountProvider>
  );
}
function SessionGate({
  initial,
  children,
}: {
  initial: OnboardingState;
  children: ReactNode;
}) {
  const [state, setState] = useState(initial);
  const { account, loading } = useAccount();
  const preview =
    !native && new URLSearchParams(location.search).has("onboarding");
  const gated = native || preview;
  const deferred = !!state.verificationDeferred && !account.configured;
  const ready =
    !gated || (state.completed && !loading && (accountIsVerified(account) || deferred));
  useEffect(() => {
    if (ready) return;
    const theme = resolveTheme(readThemePreference(), systemPrefersDark());
    applyTheme(theme);
    void syncWindowTheme(theme);
    let stopped = false;
    void getSystemAccent().then((accent) => {
      if (!stopped) applyAccent(readAccentPreference(), accent, theme);
    });
    return () => {
      stopped = true;
    };
  }, [ready]);
  function save(next: OnboardingState) {
    // Saving must succeed before leaving the guide. No identity or tokens here.
    localStorage.setItem(ONBOARDING_KEY, JSON.stringify(next));
    setState(next);
  }
  if (ready) return children;
  if (loading)
    return (
      <div className="onboarding-shell">
        <div className="onboarding-titlebar" data-tauri-drag-region />
        <main className="onboarding-loading" role="status">
          <LoaderCircle className="spin" size={25} aria-hidden="true" />
          <p>正在检查登录状态…</p>
        </main>
      </div>
    );
  if (state.completed)
    return (
      <div className="onboarding-shell">
        <div className="onboarding-titlebar" data-tauri-drag-region />
        <main className="onboarding-card account-recovery">
          <span className="eyebrow">NCL BUILDER</span>
          <h1>验证账号后继续</h1>
          <p className="onboarding-description">
            重新登录或验证 Minecraft Java 版资格，即可继续使用工作台。
          </p>
          <AccountPanel />
          {!account.configured && (
            <button
              className="secondary"
              onClick={() => save({ ...state, verificationDeferred: true })}
            >
              暂时跳过正版验证
            </button>
          )}
        </main>
      </div>
    );
  return <Onboarding state={state} onSave={save} />;
}
function Onboarding({
  state,
  onSave,
}: {
  state: OnboardingState;
  onSave: (state: OnboardingState) => void;
}) {
  const { account, code } = useAccount();
  const verified = accountIsVerified(account);
  const deferred = !!state.verificationDeferred && !account.configured;
  const accountReady = verified || deferred;
  const [step, setStep] = useState(() => onboardingStep(state, accountReady));
  const transition = useStepContent(step);
  const visibleStep = transition.phase === "idle" ? step : transition.step;
  const [savedForm] = useState(initialForm);
  const [form, setForm] = useState(savedForm.form);
  const formRef = useRef(form);
  formRef.current = form;
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [warning, setWarning] = useState("");
  const [plan, setPlan] = useState<StorageChangePlan | null>(null);
  const [selectedDirectory, setSelectedDirectory] = useState("");
  const [workspaceReady, setWorkspaceReady] = useState(!native);
  const locked = useRef(false);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (!native) return;
    let stopped = false;
    defaultWorkspace()
      .then((path) => {
        if (!stopped) {
          setForm((old) => ({ ...old, workspace: path || old.workspace }));
          setWorkspaceReady(true);
        }
      })
      .catch(() => {
        if (!stopped) setError("无法读取项目目录，请重新打开完整的桌面应用。");
      });
    return () => {
      stopped = true;
    };
  }, []);
  useEffect(() => {
    if (transition.phase === "idle")
      heading.current?.focus({ preventScroll: true });
  }, [visibleStep, transition.phase]);
  useEffect(() => {
    if (step > 1 && !accountReady) setStep(1);
  }, [accountReady, step]);
  async function attempt(label: string, action: () => Promise<void>) {
    if (locked.current) return;
    locked.current = true;
    setBusy(label);
    setError("");
    try {
      await action();
    } catch (e) {
      setError(String(e).replace(/^Error: /, ""));
    } finally {
      locked.current = false;
      setBusy("");
    }
  }
  async function applyPlan(
    next: StorageChangePlan,
    root: string,
    policy: StoragePolicy,
  ) {
    const result = await workbench<{
      ready: boolean;
      warnings?: string[];
      pathMappings?: Record<string, string>;
    }>(formRef.current, "storage-change-apply", undefined, {
      paths: next.paths,
      token: next.token,
      policy,
    });
    const updated = {
      ...formRef.current,
      ...storageFormPatch(
        formRef.current,
        next.paths.builds,
        result.pathMappings,
      ),
    };
    // Persist the same form consumed by the workbench, without resetting other inputs.
    localStorage.setItem(FORM_KEY, JSON.stringify(updated));
    setForm(updated);
    onSave({ ...state, storageRoot: root });
    setPlan(null);
    setWarning(
      [
        !result.ready
          ? "当前可用空间不足，开始构建前请在存储管理中检查空间。"
          : "",
        ...(result.warnings || []),
      ]
        .filter(Boolean)
        .join(" "),
    );
  }
  async function chooseDirectory() {
    await attempt("正在选择储存目录", async () => {
      if (savedForm.issue) throw new Error(savedForm.issue);
      const directory = await choosePath("选择统一储存目录", true);
      if (!directory) return;
      setBusy("正在检查已有文件");
      const next = await workbench<StorageChangePlan>(
        formRef.current,
        "storage-change-plan",
        undefined,
        { paths: unifiedStoragePaths(directory) },
      );
      setSelectedDirectory(directory);
      if (next.rows.some((row) => row.count > 0)) setPlan(next);
      else await applyPlan(next, directory, "keep");
    });
  }
  function next() {
    if (busy || transition.phase !== "idle") return;
    try {
      if (step === 0) {
        onSave({ ...state, accepted: true });
        setStep(1);
      } else if (step === 1 && accountReady && !code) setStep(2);
      else if (step === 2 && state.storageRoot && accountReady) setStep(3);
      else if (
        step === 3 &&
        state.accepted &&
        accountReady &&
        state.storageRoot
      )
        onSave({ ...state, completed: true });
    } catch {
      setError("无法保存初始配置，请检查本机存储权限后重试。");
    }
  }
  const names = ["使用须知", "正版登录", "储存目录", "完成配置"];
  const titles = [
    "欢迎使用 NCL Builder",
    "登录你的正版账号",
    "为构建留出空间",
    "初步配置已完成",
  ];
  const icons = [ShieldCheck, UserRound, HardDrive, CheckCircle2];
  const Icon = icons[visibleStep];
  const canContinue =
    step === 0 ||
    (step === 1 ? accountReady && !code : !!state.storageRoot && accountReady);
  return (
    <div
      className="onboarding-shell"
      data-window-chrome={
        native && /Mac/.test(navigator.platform) ? "overlay" : undefined
      }
    >
      <div
        className="onboarding-titlebar"
        data-tauri-drag-region
        aria-hidden="true"
      />
      <main className="onboarding-layout">
        <div
          className="onboarding-progress"
          role="progressbar"
          aria-label="初始配置进度"
          aria-valuemin={0}
          aria-valuemax={4}
          aria-valuenow={step + 1}
          aria-valuetext={`第 ${step + 1} 步，共 4 步：${names[step]}`}
        >
          <span style={{ transform: `scaleX(${(step + 1) / 4})` }} />
        </div>
        <ol className="onboarding-steps" aria-label="引导步骤">
          {names.map((name, index) => (
            <li
              key={name}
              aria-current={index === step ? "step" : undefined}
              data-complete={index < step}
            >
              <span aria-hidden="true">
                {index < step ? <Check size={12} /> : index + 1}
              </span>
              {name}
            </li>
          ))}
        </ol>
        <section className="onboarding-card" aria-labelledby="onboarding-title">
          <StepBody
            step={visibleStep}
            phase={transition.phase}
            direction={transition.direction}
            className="onboarding-body"
          >
            <div
              className="onboarding-glyph"
              data-complete={visibleStep === 3}
              aria-hidden="true"
            >
              <Icon size={32} strokeWidth={1.5} />
            </div>
            <span className="eyebrow">
              NCL BUILDER · {String(visibleStep + 1).padStart(2, "0")} / 04
            </span>
            <h1 id="onboarding-title" ref={heading} tabIndex={-1}>
              {titles[visibleStep]}
            </h1>
            <p className="onboarding-description">
              {
                [
                  "开始之前，先了解本软件的使用与分发边界。",
                  "登录拥有 Minecraft Java Edition 的账号，验证正版资格。",
                  "选择一个总目录，后续的构建产物与缓存就都有了归处。",
                  deferred
                    ? "储存目录已就绪，正版验证暂缓，可以开始准备构建。"
                    : "账号和储存目录已就绪，可以开始导入内容、准备构建了。",
                ][visibleStep]
              }
            </p>
            {visibleStep === 0 && (
              <div className="onboarding-notices">
                <article>
                  <ShieldCheck size={21} aria-hidden="true" />
                  <div>
                    <h2>独立的第三方软件</h2>
                    <p>
                      NCL Builder 与 Minecraft、Mojang Studios 和 Microsoft
                      没有关联，亦未获得其认可或赞助。
                    </p>
                  </div>
                </article>
                <article>
                  <Files size={21} aria-hidden="true" />
                  <div>
                    <h2>游戏文件由你在本地获取</h2>
                    <p>
                      本软件不以任何形式直接分发修改后的游戏文件。构建所需游戏内容应由你通过合法渠道取得。
                    </p>
                  </div>
                </article>
                <article>
                  <PackageCheck size={21} aria-hidden="true" />
                  <div>
                    <h2>构建产物供个人使用</h2>
                    <p>
                      构建的 IPA
                      可能包含游戏代码与资源，不建议向他人分发。请遵守相关法律及游戏许可条款。
                    </p>
                  </div>
                </article>
              </div>
            )}
            {visibleStep === 1 && (
              <>
                <AccountPanel />
                {!account.configured && (
                  <button
                    className="secondary"
                    disabled={!!busy || !!code || transition.phase !== "idle"}
                    onClick={() => {
                      try {
                        onSave({ ...state, verificationDeferred: true });
                        setStep(2);
                      } catch {
                        setError("无法保存配置，请检查本地存储权限。");
                      }
                    }}
                  >
                    暂时跳过正版验证
                  </button>
                )}
                <p className="onboarding-ownership">
                  依据相关法律与游戏许可要求，本软件不提供免费游玩 Minecraft
                  的功能。请仅使用你合法拥有的游戏文件。
                </p>
              </>
            )}
            {visibleStep === 2 && (
              <div className="onboarding-storage">
                <div className="onboarding-storage-choice">
                  <FolderOpen size={22} aria-hidden="true" />
                  <div>
                    <strong>
                      {state.storageRoot
                        ? "已选择储存目录"
                        : "快速选择储存目录"}
                    </strong>
                    <p>
                      {state.storageRoot || "只需选择一次，自动设置四类目录。"}
                    </p>
                  </div>
                  <button
                    className="secondary"
                    disabled={!native || !workspaceReady || !!busy}
                    onClick={() => void chooseDirectory()}
                  >
                    {state.storageRoot ? "更换目录" : "选择目录"}
                  </button>
                </div>
                <dl className="onboarding-storage-paths">
                  {Object.entries(
                    unifiedStoragePaths(state.storageRoot || "所选目录"),
                  ).map(([role, path]) => (
                    <div key={role}>
                      <dt>{storageRoles[role]}</dt>
                      <dd>{path}</dd>
                    </div>
                  ))}
                </dl>
                <div className="onboarding-space-note">
                  <HardDrive size={18} aria-hidden="true" />
                  <p>
                    编译缓存和中间产物可能占用大量空间，建议选择空间充足的磁盘。之后可在设置中更改，或在存储管理中检查占用。
                  </p>
                </div>
              </div>
            )}
            {visibleStep === 3 && (
              <div className="onboarding-summary">
                <div>
                  <CheckCircle2 size={20} aria-hidden="true" />
                  <div>
                    <strong>
                      {verified ? account.profile?.name : "正版验证已暂时跳过"}
                    </strong>
                    <p>
                      {verified
                        ? "Minecraft Java Edition · 正版资格已验证"
                        : "账号尚未验证，可在设置中稍后登录。"}
                    </p>
                  </div>
                </div>
                <div>
                  <FolderOpen size={20} aria-hidden="true" />
                  <div>
                    <strong>储存目录已配置</strong>
                    <p>{state.storageRoot}</p>
                  </div>
                </div>
                <p className="onboarding-summary-hint">
                  账号可在设置首行管理；储存位置可随时调整。
                </p>
              </div>
            )}
          </StepBody>
          {error && (
            <p className="account-error" role="alert">
              {error}
            </p>
          )}
          {warning && (
            <p className="onboarding-warning" role="status">
              {warning}
            </p>
          )}
          {busy && (
            <p className="account-waiting" role="status">
              <LoaderCircle size={15} className="spin" aria-hidden="true" />
              {busy}…
            </p>
          )}
          <footer className="onboarding-footer">
            <span className="onboarding-step-count">
              第 {step + 1} 步，共 4 步
            </span>
            <div className="button-line">
              {step > 0 && (
                <button
                  className="text-button"
                  disabled={!!busy || !!code || transition.phase !== "idle"}
                  onClick={() => {
                    setError("");
                    setStep(step - 1);
                  }}
                >
                  <ChevronLeft size={16} aria-hidden="true" />
                  上一步
                </button>
              )}
              <button
                className="primary"
                disabled={!canContinue || !!busy || transition.phase !== "idle"}
                onClick={next}
              >
                {step === 3 ? "开始使用" : step === 0 ? "了解并继续" : "下一步"}
                <ArrowRight size={16} aria-hidden="true" />
              </button>
            </div>
          </footer>
        </section>
        <p className="onboarding-caption">本地构建 · 个人使用</p>
      </main>
      {plan && (
        <StorageChangeDialog
          plan={plan}
          busy={busy}
          error={error}
          onCancel={() => {
            setPlan(null);
            setError("");
          }}
          onApply={(policy) =>
            void attempt(
              policy === "migrate"
                ? "正在迁移并校验文件"
                : policy === "delete"
                  ? "正在处理已有文件"
                  : "正在保存储存设置",
              () => applyPlan(plan, selectedDirectory, policy),
            )
          }
        />
      )}
    </div>
  );
}
