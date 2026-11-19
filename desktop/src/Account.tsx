import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { invoke } from "@tauri-apps/api/core";
import {
  Check,
  ExternalLink,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import { native } from "./bridge";

export interface AccountSnapshot {
  loginRequired?: boolean;
  configured: boolean;
  verified: boolean;
  profile: { id: string; name: string } | null;
  verifiedAt?: number;
  verifiedUntil?: number;
}
interface LoginCode {
  userCode: string;
  verificationUrl: string;
  expiresAt: number;
  interval: number;
}
const empty: AccountSnapshot = {
  configured: false,
  verified: false,
  profile: null,
};
const action = <T,>(name: string) =>
  invoke<T>("account_action", { action: name });
const message = (error: unknown) => String(error).replace(/^Error: /, "");
export function accountIsVerified(
  account: AccountSnapshot,
  now = Date.now() / 1000,
) {
  return !!(
    account.verified &&
    account.profile &&
    account.verifiedUntil &&
    account.verifiedUntil > now
  );
}

function useAccountState(revalidate: boolean) {
  const [account, setAccount] = useState<AccountSnapshot>(empty);
  const [loading, setLoading] = useState(native);
  const [busy, setBusy] = useState(false);
  const [code, setCode] = useState<LoginCode | null>(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const generation = useRef(0);
  const operation = useRef(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    let stopped = false;
    if (!native)
      return () => {
        mounted.current = false;
      };
    action<AccountSnapshot>("status")
      .then((value) => {
        if (!stopped)
          setAccount({
            ...value,
            verified: revalidate ? false : value.verified,
          });
        return revalidate && value.loginRequired !== false && value.configured
          ? action<AccountSnapshot>("refresh")
          : value;
      })
      .then((value) => {
        if (!stopped) setAccount(value);
      })
      .catch((e) => {
        if (!stopped) {
          setAccount((old) => ({ ...old, verified: false }));
          setError(message(e));
        }
      })
      .finally(() => {
        if (!stopped) setLoading(false);
      });
    return () => {
      stopped = true;
      mounted.current = false;
    };
  }, [revalidate]);

  async function begin() {
    if (operation.current || !native) return;
    operation.current = true;
    setBusy(true);
    setError("");
    setCopied(false);
    const request = ++generation.current;
    try {
      const next = await action<LoginCode>("begin");
      if (generation.current !== request || !mounted.current) return;
      setCode(next);
      try {
        await invoke("open_account_login");
      } catch (e) {
        if (mounted.current) setError(message(e));
      }
    } catch (e) {
      if (mounted.current) setError(message(e));
    } finally {
      operation.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  async function cancel() {
    if (operation.current) return;
    operation.current = true;
    ++generation.current;
    setCode(null);
    setBusy(true);
    setError("");
    try {
      setAccount(await action<AccountSnapshot>("cancel"));
    } catch (e) {
      setError(message(e));
    } finally {
      operation.current = false;
      setBusy(false);
    }
  }
  async function refresh() {
    if (operation.current || code || !native) return;
    operation.current = true;
    setBusy(true);
    setError("");
    try {
      setAccount(await action<AccountSnapshot>("refresh"));
    } catch (e) {
      setAccount((old) => ({ ...old, verified: false }));
      setError(message(e));
    } finally {
      operation.current = false;
      setBusy(false);
    }
  }

  useEffect(() => {
    if (!code) return;
    let stopped = false;
    let interval = code.interval;
    let timer: ReturnType<typeof setTimeout>;
    const request = generation.current;
    async function poll() {
      try {
        if (Date.now() / 1000 >= code!.expiresAt)
          throw new Error("验证码已过期，请重新登录。");
        const result = await action<
          AccountSnapshot & {
            pending?: boolean;
            ready?: boolean;
            interval?: number;
          }
        >("poll");
        if (stopped || generation.current !== request) return;
        if (result.pending) {
          interval = result.interval || interval;
          timer = setTimeout(poll, interval * 1000);
        } else if (result.ready) {
          operation.current = true;
          setBusy(true);
          try {
            const committed = await action<AccountSnapshot>("commit");
            if (!stopped && generation.current === request) {
              setAccount(committed);
              setCode(null);
              setError("");
            }
          } finally {
            operation.current = false;
            if (!stopped) setBusy(false);
          }
        } else {
          throw new Error("登录状态无效，请重新登录。");
        }
      } catch (e) {
        if (!stopped && generation.current === request) {
          setCode(null);
          setError(message(e));
        }
      }
    }
    timer = setTimeout(poll, interval * 1000);
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [code]);
  useEffect(() => {
    if (!account.verifiedUntil || !account.verified || code) return;
    const timer = setTimeout(
      () => void refresh(),
      Math.max(1000, account.verifiedUntil * 1000 - Date.now() - 30000),
    );
    return () => clearTimeout(timer);
  }, [account.verifiedUntil, account.verified, code]);
  return {
    account,
    loading,
    busy,
    code,
    error,
    copied,
    begin,
    cancel,
    refresh,
    async copy() {
      if (!code) return;
      try {
        await navigator.clipboard.writeText(code.userCode);
        setCopied(true);
      } catch {
        setError("复制失败，请手动选中验证码复制。");
      }
    },
    async openLogin() {
      try {
        await invoke("open_account_login");
      } catch (e) {
        setError(message(e));
      }
    },
  };
}
type AccountState = ReturnType<typeof useAccountState>;
const AccountContext = createContext<AccountState | null>(null);
export function AccountProvider({
  children,
  revalidate,
}: {
  children: ReactNode;
  revalidate: boolean;
}) {
  const state = useAccountState(revalidate);
  return (
    <AccountContext.Provider value={state}>{children}</AccountContext.Provider>
  );
}
export function useAccount() {
  const state = useContext(AccountContext);
  if (!state) throw new Error("AccountProvider is missing");
  return state;
}
export function AccountPanel({ disabled = false }: { disabled?: boolean }) {
  const session = useAccount();
  const { account, loading, busy, code, error } = session;
  const verified = accountIsVerified(account);
  return (
    <div className="account-panel" aria-busy={loading || busy}>
      <div className="account-identity">
        <span className="account-avatar" aria-hidden="true">
          <UserRound size={24} strokeWidth={1.6} />
        </span>
        <div className="account-identity-text">
          <strong>{account.profile?.name || "登录 Microsoft 账号"}</strong>
          <small>
            {loading
              ? "正在检查登录状态…"
              : verified
                ? "Minecraft Java Edition · 正版资格已验证"
                : account.profile
                  ? "需要重新验证正版资格"
                  : "使用拥有 Minecraft Java Edition 的账号"}
          </small>
        </div>
        {verified && (
          <span className="account-verified">
            <ShieldCheck size={15} aria-hidden="true" />
            已验证
          </span>
        )}
      </div>
      {account.profile && (
        <dl className="account-details">
          <div>
            <dt>游戏档案 ID</dt>
            <dd>{account.profile.id}</dd>
          </div>
          {account.verifiedAt && (
            <div>
              <dt>最近验证</dt>
              <dd>
                {new Date(account.verifiedAt * 1000).toLocaleString("zh-CN")}
              </dd>
            </div>
          )}
        </dl>
      )}
      {!loading && !account.configured && (
        <p className="account-message" role="status">
          登录服务待配置，请联系应用维护者完成配置后再登录。
        </p>
      )}
      {code ? (
        <div className="login-code-panel">
          <p>
            在 Microsoft 官方页面输入下方验证码，完成登录后会自动验证正版资格。
          </p>
          <div className="login-code-row">
            <code aria-label="登录验证码">{code.userCode}</code>
            <button className="secondary" onClick={() => void session.copy()}>
              {session.copied && <Check size={15} aria-hidden="true" />}
              {session.copied ? "已复制" : "复制验证码"}
            </button>
          </div>
          <p className="login-address">
            microsoft.com/link · 验证码有效至{" "}
            {new Date(code.expiresAt * 1000).toLocaleTimeString("zh-CN")}
          </p>
          <div className="button-line">
            <button
              className="secondary"
              onClick={() => void session.openLogin()}
            >
              <ExternalLink size={15} aria-hidden="true" />
              打开登录页面
            </button>
            <button
              className="text-button"
              disabled={busy}
              onClick={() => void session.cancel()}
            >
              取消登录
            </button>
          </div>
          <p className="account-waiting" role="status">
            <LoaderCircle size={15} className="spin" aria-hidden="true" />
            等待授权与正版验证…
          </p>
        </div>
      ) : (
        <div className="button-line account-actions">
          <button
            className={verified ? "secondary" : "primary"}
            disabled={
              !native || loading || busy || disabled || !account.configured
            }
            onClick={() => void session.begin()}
          >
            {busy ? (
              <LoaderCircle size={16} className="spin" aria-hidden="true" />
            ) : (
              <UserRound size={16} aria-hidden="true" />
            )}
            {busy
              ? "正在处理…"
              : verified
                ? "切换账号"
                : "使用 Microsoft 账号登录"}
          </button>
          {(account.profile || error) && (
            <button
              className="text-button"
              disabled={!native || loading || busy || disabled}
              onClick={() => void session.refresh()}
            >
              <RefreshCw size={15} aria-hidden="true" />
              重新验证
            </button>
          )}
        </div>
      )}
      {disabled && (
        <p className="account-message">
          构建正在进行，完成或取消后可切换账号。
        </p>
      )}
      {error && (
        <p className="account-error" role="alert">
          {error}
        </p>
      )}
      <p className="account-privacy">
        登录在 Microsoft 官方页面完成，凭证仅保存在本机钥匙串。
      </p>
    </div>
  );
}
