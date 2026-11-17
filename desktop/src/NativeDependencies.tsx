import { RefreshCw, Square } from "lucide-react";
import {
  isActive,
  jobStateName,
  stageName,
  type BuildJob,
  type DependencyInventory,
} from "./workflow";
import { LogView } from "./LogView";
import "./native-dependencies.css";

const states = {
  current: "一致",
  stale: "已过期",
  missing: "缺失",
  invalid: "校验失败",
};

export function DependencyTask({
  job,
  disabled,
  onCancel,
}: {
  job: BuildJob;
  disabled: boolean;
  onCancel: () => void;
}) {
  return (
    <section className="dependency-task" aria-label="依赖库重建任务">
      <div className="check-toolbar">
        <strong>
          {jobStateName(job)} · {stageName(job.stage)}
        </strong>
        {isActive(job) && (
          <button
            className="danger"
            disabled={disabled || job.state === "cancelling"}
            onClick={onCancel}
          >
            <Square size={14} />
            {job.state === "cancelling" ? "正在停止…" : "取消重建"}
          </button>
        )}
      </div>
      {job.dependencyProgress && (
        <p role="status">
          已完成 {job.dependencyProgress.completed} /{" "}
          {job.dependencyProgress.total}
        </p>
      )}
      <code className="dependency-path">{job.build}</code>
      {job.error && (
        <p role="alert" className="dependency-error">
          {job.error}
        </p>
      )}
      {job.state === "succeeded" && <p>构建配置已切换到新目录。</p>}
      <div className="dependency-log" tabIndex={0} aria-label="依赖库构建日志">
        <LogView text={job.log ?? "等待构建日志…"} label="依赖库日志内容" />
      </div>
    </section>
  );
}

export function NativeDependencies({
  report,
  error,
  disabled,
  checking,
  onRefresh,
  onRebuild,
}: {
  report: DependencyInventory | null;
  error: string;
  disabled: boolean;
  checking: boolean;
  onRefresh: () => void;
  onRebuild: (keys: string[]) => void;
}) {
  return (
    <section
      className="panel flat dependency-manager"
      aria-label="原生依赖库管理"
    >
      <div className="check-toolbar">
        <h2>原生依赖库</h2>
        <button
          className="secondary"
          disabled={disabled || checking}
          onClick={onRefresh}
        >
          <RefreshCw size={16} />
          {checking ? "正在比对…" : "刷新依赖状态"}
        </button>
      </div>
      <p className="section-description">
        按依赖顺序构建 iPhoneOS arm64 产物，成功后切换配置。新产物保存在
        artifacts/graphics 下的独立时间戳目录。
      </p>
      <div className="button-line">
        <button
          className="primary"
          disabled={disabled || !report}
          onClick={() =>
            report && onRebuild(report.libraries.map((r) => r.key))
          }
        >
          按顺序整体重建
        </button>
        <button
          className="secondary"
          disabled={
            disabled ||
            !report?.libraries.some((r) => r.required && r.state !== "current")
          }
          onClick={() =>
            report &&
            onRebuild(
              report.libraries
                .filter((r) => r.required && r.state !== "current")
                .map((r) => r.key),
            )
          }
        >
          一键重建所需依赖
        </button>
      </div>
      {error && (
        <p role="alert" className="dependency-error">
          {error}
        </p>
      )}
      {!report ? (
        <p role="status">
          {checking
            ? "正在比对源码、产物和依赖哈希…"
            : "选择构建配置后可检查全部依赖库。"}
        </p>
      ) : (
        <ol className="dependency-list">
          {report.libraries.map((row) => (
            <li key={row.key} data-testid={`dependency-${row.key}`}>
              <div className="dependency-heading">
                <h3>{row.name}</h3>
                <span className={`dependency-state ${row.state}`}>
                  {states[row.state]}
                </span>
                {!row.required && <small>可选 Metal 路线</small>}
                <button
                  className="secondary"
                  disabled={disabled}
                  aria-label={`重建 ${row.name}`}
                  onClick={() => onRebuild([row.key])}
                >
                  单独重建
                </button>
              </div>
              <dl>
                <dt>当前路径</dt>
                <dd>
                  <code className="dependency-path">
                    {row.path || "未配置"}
                  </code>
                </dd>
                <dt>
                  {row.timeBasis === "report-mtime"
                    ? "构建记录时间"
                    : "构建时间"}
                </dt>
                <dd>
                  {row.builtAt
                    ? new Date(row.builtAt).toLocaleString()
                    : "未知"}
                </dd>
                <dt>目标架构</dt>
                <dd>{row.target}</dd>
              </dl>
              {row.mode === "fetch" && (
                <p>固定版本预编译库：重建时重新获取并校验哈希。</p>
              )}
              {!!row.reasons.length && <p>{row.reasons.join("；")}</p>}
              {!!row.changedFiles.length && (
                <details open>
                  <summary>变更的源文件（{row.changedFiles.length}）</summary>
                  <ul>
                    {row.changedFiles.map((file) => (
                      <li key={file}>
                        <code>{file}</code>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
