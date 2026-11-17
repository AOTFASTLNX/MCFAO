import { useEffect, useRef, useState } from "react";
import { formatBytes, storageRoles } from "./storageManagement";

export type StoragePolicy = "keep" | "migrate" | "delete";
export interface StorageChangePlan {
  paths: { cache: string; builds: string; jobs: string; rust: string };
  token: string;
  rows: {
    role: string;
    source: string;
    destination: string;
    bytes: number;
    count: number;
  }[];
}
export function StorageChangeDialog({
  plan,
  busy,
  error,
  onCancel,
  onApply,
}: {
  plan: StorageChangePlan;
  busy: string;
  error: string;
  onCancel: () => void;
  onApply: (policy: StoragePolicy) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [choice, setChoice] = useState<StoragePolicy | "">("");
  const [deleting, setDeleting] = useState(false);
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  return (
    <dialog
      ref={dialog}
      className="confirm-dialog"
      aria-labelledby="storage-change-title"
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onCancel();
      }}
    >
      <h2 id="storage-change-title">
        {deleting ? "删除已有文件？" : "如何处理已有文件？"}
      </h2>
      <p>
        {deleting
          ? "将永久删除下列原目录内的全部文件，包括构建产物、IPA、缓存和任务记录。此操作无法撤销。"
          : "新目录已选好，请选择如何处理原储存目录中的文件。尚未更改设置。"}
      </p>
      <details open>
        <summary>
          涉及 {plan.rows.reduce((sum, row) => sum + row.count, 0)} 个文件 ·{" "}
          {formatBytes(plan.rows.reduce((sum, row) => sum + row.bytes, 0))}
        </summary>
        <ul className="storage-list">
          {plan.rows.map((row) => (
            <li key={row.role}>
              <strong>{storageRoles[row.role]}</strong> ·{" "}
              {formatBytes(row.bytes)}
              <p className="sm-path">
                原目录：{row.source}
                <br />
                新目录：{row.destination}
              </p>
            </li>
          ))}
        </ul>
      </details>
      {!deleting && (
        <fieldset disabled={!!busy} style={{ border: 0, padding: 0 }}>
          <legend>处理方式</legend>
          {(
            [
              [
                "migrate",
                "迁移已有文件",
                "复制到新目录并逐文件校验，成功后移除原文件。目标子目录须不存在；迁移后旧构建可能需要重新检测或编译。",
              ],
              [
                "delete",
                "删除已有文件",
                "删除原目录内的全部文件，后续任务从新目录开始。需再次确认。",
              ],
              ["keep", "保留原位", "保留已有文件，只将后续文件保存到新目录。"],
            ] as const
          ).map(([policy, title, detail]) => (
            <label className="setting-row" key={policy}>
              <input
                type="radio"
                name="storage-policy"
                checked={choice === policy}
                onChange={() => setChoice(policy)}
              />
              <span className="setting-label">
                <strong>{title}</strong>
                <small>{detail}</small>
              </span>
            </label>
          ))}
        </fieldset>
      )}
      {error && <p role="alert">{error}</p>}
      {busy && (
        <p role="status">{busy}… 大目录可能耗时较长，请保持应用打开。</p>
      )}
      <div className="button-line">
        <button
          className="secondary"
          autoFocus
          disabled={!!busy}
          onClick={onCancel}
        >
          取消
        </button>
        <button
          className={deleting ? "danger" : "primary"}
          disabled={!!busy || !choice}
          onClick={() => {
            if (choice === "delete" && !deleting) setDeleting(true);
            else if (choice) onApply(choice);
          }}
        >
          {deleting ? "删除原文件并切换目录" : "应用所选方式"}
        </button>
      </div>
    </dialog>
  );
}
