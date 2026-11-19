import { useEffect, type RefObject } from "react";
import { Download, LoaderCircle } from "lucide-react";
import { AccountPanel, accountIsVerified, useAccount } from "./Account";
import { native, workbench } from "./bridge";
import type { BuildForm, SetupState } from "./workflow";

export function setupIsRunning(setup: SetupState | null) {
  return setup?.state === "queued" || setup?.state === "running";
}

export function useSetupProgress(
  form: RefObject<BuildForm>,
  setup: SetupState | null,
  setSetup: (value: SetupState) => void,
) {
  const running = setupIsRunning(setup);
  useEffect(() => {
    if (!native || !running) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const next = await workbench<SetupState>(form.current, "setup-status");
        if (cancelled) return;
        setSetup(next);
        if (!setupIsRunning(next)) return;
      } catch {
        if (cancelled) return;
      }
      timer = setTimeout(poll, 1500);
    }
    timer = setTimeout(poll, 750);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [running, form, setSetup]);
}

export function BuildSetup({
  setup,
  configured = false,
  disabled,
  onStart,
}: {
  setup: SetupState | null;
  configured?: boolean;
  disabled: boolean;
  onStart: () => void;
}) {
  const { account } = useAccount();
  const canPrepare = account.loginRequired === false || accountIsVerified(account);
  const running = setupIsRunning(setup);
  const generated = setup?.state === "ready" && !!setup.config;
  const ready = generated || configured;
  const retry = setup?.state === "failed";
  return (
    <section className="dependency-preflight" aria-label="自动准备构建环境">
      <div className="environment-row">
        <div>
          <h3>自动准备构建环境</h3>
          <p>
            {ready && !running && !retry
              ? generated
                ? "构建配置已自动生成并保存，可以开始构建。"
                : "已找到构建配置。应用会在构建前再次校验。"
              : "下载游戏资源和所需工具，准备 iOS 依赖后自动生成并保存构建配置。"}
          </p>
        </div>
        {!running && native && canPrepare && (
          <button
            type="button"
            className={ready && !retry ? "secondary" : "primary"}
            disabled={disabled}
            onClick={onStart}
          >
            <Download size={16} aria-hidden="true" />
            {retry ? "重试准备" : ready ? "重新检查并准备" : "一键下载并准备"}
          </button>
        )}
      </div>
      {running && (
        <p role="status">
          <LoaderCircle size={15} className="spin" aria-hidden="true" />
          {" "}{setup?.message || "正在准备…"}
        </p>
      )}
      {setup?.stage === "toolchain" && setup.totalBytes && (
        <progress
          aria-label="工具链下载进度"
          value={setup.completedBytes || 0}
          max={setup.totalBytes}
        />
      )}
      {retry && (
        <p role="alert">{setup.error || setup.message || "准备中断，请重试。"}</p>
      )}
      {!running && native && !canPrepare && (
        <div className="build-setup-account">
          <AccountPanel disabled={disabled} />
        </div>
      )}
      {!native && <p>请在桌面应用中登录并准备构建环境。</p>}
    </section>
  );
}
