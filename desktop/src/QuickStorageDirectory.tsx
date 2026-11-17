import { useEffect, useRef, useState } from "react";
import { FolderOpen } from "lucide-react";

export function QuickStorageDirectory({
  disabled,
  busy,
  status,
  onChoose,
  onReset,
}: {
  disabled: boolean;
  busy: string;
  status: string;
  onChoose: () => void;
  onReset: () => void;
}) {
  const [confirm, setConfirm] = useState<"choose" | "reset" | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (confirm) dialog.current?.showModal();
  }, [confirm]);
  return (
    <div className="settings-group">
      <h2>储存目录</h2>
      <div className="setting-row">
        <div className="setting-label">
          <strong>快速选择储存目录</strong>
          <small>
            选择一个总目录，统一保存后续的缓存、构建产物与任务记录。
          </small>
        </div>
        <div className="setting-control">
          <button
            className="secondary"
            disabled={disabled}
            onClick={() => setConfirm("choose")}
          >
            <FolderOpen size={16} aria-hidden="true" />
            快速选择储存目录
          </button>
        </div>
      </div>
      <div className="setting-row">
        <div className="setting-label">
          <strong>重置目录设置</strong>
          <small>恢复默认储存路径，已有文件保留原位。</small>
        </div>
        <div className="setting-control">
          <button
            className="secondary"
            disabled={disabled}
            onClick={() => setConfirm("reset")}
          >
            重置目录设置
          </button>
        </div>
      </div>
      {busy && <p role="status">{busy}…</p>}
      {!busy && status && <p role="status">{status}</p>}
      {confirm && (
        <dialog
          ref={dialog}
          className="confirm-dialog"
          aria-labelledby="quick-storage-title"
          onCancel={() => setConfirm(null)}
        >
          <h2 id="quick-storage-title">
            {confirm === "reset" ? "重置目录设置？" : "覆盖当前储存设置？"}
          </h2>
          {confirm === "reset" ? (
            <p>
              将恢复默认的编译缓存、构建产物、任务记录及 Rust
              缓存目录。已有文件保留原位，不会迁移或删除；后续任务使用默认目录。是否继续？
            </p>
          ) : (
            <>
              <p>此操作会覆盖当前已有的储存设置，是否继续？</p>
              <p>
                继续后请选择一个目录，缓存、构建产物、任务记录和 Rust
                缓存将分别保存到其中的 cache、builds、jobs、rust
                子目录。选定后可选择迁移、删除或保留已有文件。
              </p>
            </>
          )}
          <div className="button-line">
            <button
              className="secondary"
              autoFocus
              onClick={() => setConfirm(null)}
            >
              取消
            </button>
            <button
              className="primary"
              disabled={disabled}
              onClick={() => {
                const action = confirm;
                setConfirm(null);
                if (action === "reset") onReset();
                else onChoose();
              }}
            >
              {confirm === "reset" ? "恢复默认目录" : "继续选择目录"}
            </button>
          </div>
        </dialog>
      )}
    </div>
  );
}
