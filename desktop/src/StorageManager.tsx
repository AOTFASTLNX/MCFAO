import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  ChevronRight,
  FolderOpen,
  HardDrive,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  Square,
  Trash2,
} from "lucide-react";
import {
  formatBytes as size,
  percent,
  selectedBytes,
  storageRoles,
  type StoragePlan,
} from "./storageManagement";
import { AnimatedNumber } from "./MotionPrimitives";
import "./storage-management.css";

const name = (path: string) => path.split("/").filter(Boolean).pop() || path;

/** Say plainly whether these numbers are live or came from the cache. */
function describeAge(plan: StoragePlan): string {
  if (!plan.scannedAt) return "磁盘容量按卷统计";
  const seconds = plan.ageSeconds;
  const clock = new Date(plan.scannedAt).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  });
  if (plan.cached) {
    const ago =
      typeof seconds === "number"
        ? seconds < 60
          ? "刚刚"
          : seconds < 3600
            ? `${Math.round(seconds / 60)} 分钟前`
            : `${Math.round(seconds / 3600)} 小时前`
        : "上次";
    return `缓存统计 · ${ago}（${clock}）`;
  }
  if (plan.scanState === "incremental") return `增量更新于 ${clock}`;
  return `扫描于 ${clock}`;
}

export interface ScanProgressView {
  state: string;
  phase?: string;
  files: number;
  dirs: number;
  bytes: number;
  current: string;
  error?: string;
  completedRoles?: string[];
  totalRoles?: number;
}

export function StorageManager({
  plan,
  busy,
  available,
  active,
  done,
  scan,
  scanError,
  scanMessage,
  locations,
  onScan,
  onCancelScan,
  onClean,
  onReveal,
}: {
  plan: StoragePlan | null;
  busy: string;
  available: boolean;
  active: boolean;
  done: string;
  scan: ScanProgressView | null;
  scanError: string;
  scanMessage: string;
  locations: ReactNode;
  onScan: () => void;
  onCancelScan: () => void;
  onClean: (groups: string[]) => void;
  onReveal: (path: string) => void;
}) {
  const [volume, setVolume] = useState("");
  const [role, setRole] = useState("");
  const [choices, setChoices] = useState<string[]>([]);
  const [confirm, setConfirm] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    setChoices([]);
    setConfirm(false);
    setVolume((current) =>
      plan?.volumes?.some((v) => v.id === current) ? current : "",
    );
    setRole((current) =>
      plan?.usage?.some((row) => row.role === current) ? current : "",
    );
  }, [plan]);
  useEffect(() => {
    if (confirm) dialog.current?.showModal();
  }, [confirm]);
  const usage = plan?.usage || [];
  const volumes = plan?.volumes || [];
  const filtered = usage.filter((row) => !volume || row.volumeId === volume);
  const current = filtered.find((row) => row.role === role) || filtered[0];
  const total = filtered.reduce((sum, row) => sum + row.bytes, 0);
  const selected = plan ? selectedBytes(plan, choices) : 0;
  const scanning = !!scan;
  const disabled = !available || !!busy;

  return (
    <section className="storage-page" aria-label="存储管理">
      <div className="sm-heading">
        <div>
          <h1>存储管理</h1>
          <p>查看空间分布，管理构建文件与缓存。</p>
        </div>
        <div className="sm-heading-actions">
          {scanning && (
            <button className="secondary" onClick={onCancelScan}>
              <Square size={14} aria-hidden="true" />
              取消扫描
            </button>
          )}
          <button className="secondary" disabled={disabled} onClick={onScan}>
            {scanning ? (
              <LoaderCircle size={16} className="spin" aria-hidden="true" />
            ) : (
              <RefreshCw size={16} aria-hidden="true" />
            )}
            {scanning ? "正在扫描…" : plan ? "重新扫描" : "扫描存储空间"}
          </button>
        </div>
      </div>
      {busy && (
        <p className="sm-feedback" role="status">
          {busy}…
        </p>
      )}
      {scan && (
        <div className="sm-progress" role="status" aria-live="polite">
          <div className="sm-progress-title">
            <LoaderCircle size={15} className="spin" aria-hidden="true" />
            <strong>{scan.phase === "queued" ? "等待扫描进程" : "正在扫描"}</strong>
            <span>
              已读取 {scan.files.toLocaleString("zh-CN")} 个文件 ·{" "}
              {scan.dirs.toLocaleString("zh-CN")} 个目录
            </span>
          </div>
          {scan.current && (
            <p className="sm-path" title={scan.current}>
              {scan.current}
            </p>
          )}
          <p className="sm-help">
            可切换到其他页面，扫描会在后台继续；已显示的数字来自上次完成的扫描。
          </p>
        </div>
      )}
      {scanError && (
        <p className="sm-feedback" role="alert">
          {scanError}
        </p>
      )}
      {scanMessage && (
        <p className="sm-feedback" role="status">
          {scanMessage}
        </p>
      )}
      {done && (
        <p className="sm-feedback" role="status">
          {done}
        </p>
      )}
      {!available && (
        <p className="sm-feedback">请在桌面应用中扫描和管理本机存储。</p>
      )}

      {plan ? (
        <>
          <div className="sm-stats">
            <div>
              <span>Builder 文件占用</span>
              <strong>
                {size(
                  plan.managedBytes ??
                    usage.reduce((sum, r) => sum + r.bytes, 0),
                )}
              </strong>
              <small>已扫描的存储目录</small>
            </div>
            <div>
              <span>可清理空间</span>
              <strong>{size(plan.reclaimBytes)}</strong>
              <small>
                {plan.blocked ? "当前自动清理不可用" : "按清理规则保留交付产物"}
              </small>
            </div>
            <div>
              <span>所在磁盘</span>
              <strong>
                <AnimatedNumber value={volumes.length} />
                <em> 个</em>
              </strong>
              <small>{describeAge(plan)}</small>
            </div>
          </div>
          {!!plan.warnings?.length && (
            <div className="sm-feedback" role="status">
              <strong>部分目录统计不完整</strong>
              <details>
                <summary>查看 {plan.warnings.length} 条提示</summary>
                {plan.warnings.map((warning, i) => (
                  <p key={i}>{warning}</p>
                ))}
              </details>
            </div>
          )}
          <section className="sm-panel" aria-labelledby="sm-volumes">
            <div className="sm-section-heading">
              <h2 id="sm-volumes">磁盘概览</h2>
              <button
                className="secondary"
                disabled={!volume}
                onClick={() => setVolume("")}
              >
                显示全部磁盘
              </button>
            </div>
            <div className="sm-volumes">
              {volumes.map((v) => (
                <button
                  key={v.id}
                  className={
                    "sm-volume " + (volume === v.id ? "is-selected" : "")
                  }
                  aria-pressed={volume === v.id}
                  onClick={() => setVolume(volume === v.id ? "" : v.id)}
                >
                  <div className="sm-volume-title">
                    <HardDrive size={20} aria-hidden="true" />
                    <strong>
                      {v.path === "/" ? "系统磁盘" : name(v.path)}
                    </strong>
                    <span>{size(v.freeBytes)} 可用</span>
                  </div>
                  <div
                    className="sm-meter"
                    role="img"
                    aria-label={`${v.path}：总容量 ${size(v.totalBytes)}，Builder ${size(v.managedBytes)}，其他已用 ${size(v.otherBytes)}，可用 ${size(v.freeBytes)}`}
                  >
                    <span
                      className="sm-managed"
                      style={{
                        width: percent(v.managedBytes, v.totalBytes) + "%",
                      }}
                    />
                    <span
                      className="sm-other"
                      style={{
                        width: percent(v.otherBytes, v.totalBytes) + "%",
                      }}
                    />
                  </div>
                  <div className="sm-volume-caption">
                    <span>{v.path}</span>
                    <span>
                      共 {size(v.totalBytes)}{" "}
                      <ChevronRight size={13} aria-hidden="true" />
                    </span>
                  </div>
                </button>
              ))}
            </div>
            <div className="sm-legend">
              <span>
                <i className="sm-managed" />
                Builder 文件
              </span>
              <span>
                <i className="sm-other" />
                其他已用空间
              </span>
              <span>
                <i className="sm-free" />
                可用空间
              </span>
            </div>
          </section>

          <section className="sm-panel" aria-labelledby="sm-distribution">
            <div className="sm-section-heading">
              <div>
                <h2 id="sm-distribution">存储分布</h2>
                <p>
                  {volume ? "所选磁盘" : "全部磁盘"} · {size(total)}
                  ，点击类别查看较大的目录
                </p>
              </div>
            </div>
            <div
              className="sm-distribution"
              role="img"
              aria-label={
                filtered
                  .map(
                    (row) =>
                      `${storageRoles[row.role] || row.role} ${size(row.bytes)}`,
                  )
                  .join("，") || "尚无可统计的目录"
              }
            >
              {filtered
                .filter((row) => row.bytes > 0)
                .map((row) => (
                  <span
                    key={row.role}
                    data-role={row.role}
                    style={{ width: percent(row.bytes, total) + "%" }}
                  />
                ))}
            </div>
            <div className="sm-categories">
              {filtered.map((row) => (
                <button
                  key={row.role}
                  className={
                    "sm-category " +
                    (current?.role === row.role ? "is-selected" : "")
                  }
                  aria-pressed={current?.role === row.role}
                  onClick={() => setRole(row.role)}
                >
                  <span>
                    <i data-role={row.role} />
                    {storageRoles[row.role] || row.role}
                  </span>
                  <strong>
                    {row.available === false ? "不可用" : size(row.bytes)}
                  </strong>
                  <small>
                    {row.error
                      ? "统计需检查"
                      : `${percent(row.bytes, total).toFixed(1)}%`}
                  </small>
                </button>
              ))}
            </div>
            {current && (
              <div
                className="sm-directory"
                role="region"
                aria-label={`${storageRoles[current.role]}目录明细`}
              >
                <div className="sm-section-heading">
                  <div>
                    <h3>{storageRoles[current.role]}</h3>
                    <p className="sm-path">{current.path}</p>
                  </div>
                  <button
                    className="secondary"
                    disabled={disabled || current.available === false}
                    onClick={() => onReveal(current.path)}
                  >
                    <FolderOpen size={15} aria-hidden="true" />在 Finder 中打开
                  </button>
                </div>
                {current.error && (
                  <p className="sm-feedback">{current.error}</p>
                )}
                {current.items?.length ? (
                  <>
                    <ul className="sm-files">
                      {current.items.map((item) => (
                        <li key={item.path}>
                          <div>
                            <strong title={item.path}>{name(item.path)}</strong>
                            <span>{size(item.bytes)}</span>
                            <button
                              className="icon-button"
                              disabled={disabled}
                              aria-label={"在 Finder 中显示 " + name(item.path)}
                              onClick={() => onReveal(item.path)}
                            >
                              <FolderOpen size={15} aria-hidden="true" />
                            </button>
                          </div>
                          <div className="sm-file-meter" aria-hidden="true">
                            <span
                              data-role={current.role}
                              style={{
                                width: percent(item.bytes, current.bytes) + "%",
                              }}
                            />
                          </div>
                        </li>
                      ))}
                    </ul>
                    {(current.itemCount || 0) > 12 && (
                      <p className="sm-help">
                        显示最大的 12 项，共 {current.itemCount} 项。可在 Finder
                        中查看全部内容。
                      </p>
                    )}
                  </>
                ) : (
                  <p className="sm-help">
                    {current.available === false
                      ? "连接磁盘后重新扫描。"
                      : "此目录暂无可统计的文件。"}
                  </p>
                )}
              </div>
            )}
            <p className="sm-help">
              按文件已分配空间统计；目录内部的符号链接不展开。APFS
              共享块、快照及扫描期间的文件变化可能使占用与磁盘已用空间存在差异。
            </p>
          </section>

          <section className="sm-panel" aria-labelledby="sm-cleanup">
            <div className="sm-section-heading">
              <div>
                <h2 id="sm-cleanup">空间清理</h2>
                <p>选择要清理的内容，确认后执行。</p>
              </div>
              <ShieldCheck size={21} aria-hidden="true" />
            </div>
            {(plan.blocked || active) && (
              <p className="sm-feedback">
                {active
                  ? "有任务正在运行，完成或取消后才能清理。"
                  : plan.reason || "有构建任务正在运行，完成或取消后才能清理。"}
              </p>
            )}
            {plan.groups.map((group) => (
              <div className="sm-cleanup-group" key={group.id}>
                <label>
                  <input
                    type="checkbox"
                    disabled={disabled || plan.blocked || active}
                    checked={choices.includes(group.id)}
                    onChange={(e) =>
                      setChoices((old) =>
                        e.target.checked
                          ? [...old, group.id]
                          : old.filter((id) => id !== group.id),
                      )
                    }
                  />
                  <span>
                    <strong>{group.label}</strong>
                    <small>{group.detail}</small>
                  </span>
                  <b>{size(group.bytes)}</b>
                </label>
                <details>
                  <summary>查看 {group.count} 项清理明细</summary>
                  <ul className="sm-cleanup-items">
                    {group.items.map((item) => (
                      <li key={item.path}>
                        <span className="sm-path">
                          {item.path}
                          <small>{item.reason}</small>
                        </span>
                        <span>{size(item.bytes)}</span>
                      </li>
                    ))}
                  </ul>
                </details>
              </div>
            ))}
            {!plan.groups.length && !plan.blocked && (
              <p className="sm-help">没有符合规则的可清理内容。</p>
            )}
            <div className="sm-cleanup-footer">
              <span>
                已选 {choices.length} 类 · 预计释放{" "}
                <strong>{size(selected)}</strong>
              </span>
              <button
                className="danger"
                disabled={disabled || active || plan.blocked || !choices.length}
                onClick={() => setConfirm(true)}
              >
                <Trash2 size={15} aria-hidden="true" />
                清理所选
              </button>
            </div>
          </section>
        </>
      ) : (
        <div className="sm-empty">
          <HardDrive size={40} aria-hidden="true" />
          <h2>{scanning ? "正在读取存储目录" : "从一次存储扫描开始"}</h2>
          <p>查看各磁盘容量、缓存与构建产物分布，以及可清理内容。</p>
          <p className="sm-help">扫描仅读取文件信息，不会修改文件。</p>
        </div>
      )}

      <section className="sm-panel" aria-labelledby="sm-locations">
        <h2 id="sm-locations">存储位置</h2>
        <p className="sm-help">
          分别选择四类目录。保存后用于后续任务，现有文件保留在原位置，旧任务仍可查看。
        </p>
        <div className="sm-locations">{locations}</div>
      </section>

      {confirm && plan && (
        <dialog
          ref={dialog}
          className="confirm-dialog sm-confirm"
          aria-labelledby="sm-confirm-title"
          onCancel={() => setConfirm(false)}
        >
          <h2 id="sm-confirm-title">清理磁盘空间？</h2>
          <p>
            预计释放 {size(selected)}
            。将删除所选缓存或构建阶段；IPA、构建记录与证据目录保留。
          </p>
          <ul>
            {plan.groups
              .filter((g) => choices.includes(g.id))
              .map((g) => (
                <li key={g.id}>
                  {g.label} · {size(g.bytes)}（{g.count} 项）
                </li>
              ))}
          </ul>
          <p>删除后无法撤销，下次构建可能需要重新下载或编译。</p>
          <div className="button-line">
            <button
              className="secondary"
              autoFocus
              onClick={() => setConfirm(false)}
            >
              取消
            </button>
            <button
              className="danger"
              disabled={disabled || active || plan.blocked}
              onClick={() => {
                setConfirm(false);
                onClean(choices);
              }}
            >
              删除并释放空间
            </button>
          </div>
        </dialog>
      )}
    </section>
  );
}
