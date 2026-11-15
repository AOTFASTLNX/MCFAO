import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { native } from "./bridge";
import type { Settings } from "./model";
interface ImportedInstance {
  root: string;
  mods: string;
  files: Record<string, unknown>;
  validation: string;
  importedMods: {
    id: string;
    version: string;
    declared_depends: Record<string, unknown>;
    has_mixins: boolean;
    bundled_native_count: number;
  }[];
  modFindings: unknown[];
}

export interface BuildSnapshot {
  id: string;
  state: "running" | "done" | "failed" | "cancelled";
  stage: string;
  output: string;
  logPath: string;
  lines: string[];
  error: string | null;
  artifact: {
    ipa: string;
    bytes: number;
    sha256: string;
    sourceCommit: string;
    renderer: string;
    loader: string;
    signature: string;
    aotCommand: string;
    loaderReport: string | null;
  } | null;
}
export function BuildPanel({
  settings,
  setSettings,
  modsPath,
  setModsPath,
  source,
}: {
  settings: Settings;
  setSettings: (value: Settings) => void;
  modsPath: string;
  setModsPath: (value: string) => void;
  source?: string;
}) {
  const [renderer, setRenderer] = useState("");
  const [loader, setLoader] = useState("vanilla");
  const [unsigned, setUnsigned] = useState(true);
  const [audited, setAudited] = useState(false);
  const [heap, setHeap] = useState(7);
  const [parallelism, setParallelism] = useState(3);
  const [bundle, setBundle] = useState(
    "org.fabricaot.integration.gl41.20261115",
  );
  const [snapshot, setSnapshot] = useState<BuildSnapshot | null>(null);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);
  const [adaptation, setAdaptation] = useState<Record<string, unknown> | null>(
    null,
  );
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<ImportedInstance | null>(
    null,
  );
  const busy = importing || starting || snapshot?.state === "running";
  useEffect(() => {
    if (!native) return;
    let active = true;
    const poll = async () => {
      try {
        const value = await invoke<BuildSnapshot | null>("build_status");
        if (active) setSnapshot(value);
      } catch (e) {
        if (active) setError(String(e));
      }
    };
    void poll();
    const timer = setInterval(() => void poll(), 750);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);
  async function start() {
    setError("");
    setStarting(true);
    try {
      const value = await invoke<BuildSnapshot>("start_build", {
        request: {
          ...settings,
          renderer,
          loader,
          mods: modsPath,
          auditedMods: audited,
          instanceData: importResult?.root || "",
          unsigned,
          bundleId: bundle,
          heapGib: heap,
          parallelism,
        },
      });
      setSnapshot(value);
    } catch (e) {
      setError(String(e));
    } finally {
      setStarting(false);
    }
  }
  async function cancel() {
    try {
      await invoke("cancel_build");
    } catch (e) {
      setError(String(e));
    }
  }
  async function stageInstance() {
    setImporting(true);
    setError("");
    try {
      const result = await invoke<ImportedInstance>("stage_instance", {
        workspace: settings.workspace,
        source,
        python: settings.python,
      });
      setModsPath(result.mods);
      setLoader("fabric");
      setImportResult(result);
    } catch (e) {
      setError(String(e));
    } finally {
      setImporting(false);
    }
  }
  const artifact = snapshot?.artifact;
  return (
    <section
      className="panel"
      aria-label="完整本地 AOT 构建"
      style={{ padding: 24, marginBottom: 20 }}
    >
      <div className="section-heading">
        <h2>完整本地 AOT → IPA</h2>
        <span className="badge">Apple Silicon macOS</span>
      </div>
      <p className="small muted">
        使用所选 MCFAO 源码与已核验的本地游戏资源。GL41
        是主要研发路线；真机验证前请显式选择渲染器。构建进度来自真实阶段与日志。
      </p>
      <div className="build-grid">
        <div>
          {source && (
            <div>
              <p className="small">当前预检实例：{source}</p>
              <button
                className="button secondary"
                disabled={!native || busy || importing || !settings.workspace}
                onClick={() => void stageInstance()}
              >
                {importing
                  ? "正在校验并导入实例文件…"
                  : "导入此实例的本地构建文件"}
              </button>
            </div>
          )}
          {importResult && (
            <p role="status">
              已导入 {Object.keys(importResult.files).length} 个文件。Mod 目录：
              {importResult.mods}。{importResult.validation}
            </p>
          )}
          {importResult && (
            <details>
              <summary>已获取的 Mod 元数据与静态风险</summary>
              <div style={{ overflowX: "auto" }}>
                <table>
                  <thead>
                    <tr>
                      <th>Mod / 版本</th>
                      <th>声明依赖</th>
                      <th>Mixin / JNI</th>
                      <th>实际验证</th>
                    </tr>
                  </thead>
                  <tbody>
                    {importResult.importedMods.map((mod, index) => (
                      <tr key={`${mod.id}-${index}`}>
                        <td>
                          {mod.id} · {mod.version}
                        </td>
                        <td>{JSON.stringify(mod.declared_depends)}</td>
                        <td>
                          {mod.has_mixins ? "Mixin 待转换" : "无声明 Mixin"} /{" "}
                          {mod.bundled_native_count} 个原生库待审计
                        </td>
                        <td>NOT TESTED</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <pre style={{ whiteSpace: "pre-wrap" }}>
                {JSON.stringify(importResult.modFindings, null, 2)}
              </pre>
            </details>
          )}
          <label className="field">
            运行模式
            <select
              aria-label="完整构建运行模式"
              value={loader}
              disabled={busy}
              onChange={(e) => setLoader(e.target.value)}
            >
              <option value="vanilla">Minecraft 26.1.2 Vanilla</option>
              <option value="fabric">Fabric 26.1.2 / MDAF</option>
            </select>
          </label>
          <label className="field">
            渲染器
            <select
              aria-label="完整构建渲染器"
              value={renderer}
              disabled={busy}
              onChange={(e) => setRenderer(e.target.value)}
            >
              <option value="" disabled>
                请选择渲染器
              </option>
              <option value="gl41">GL41 / Zink / MoltenVK（主要研发）</option>
              <option value="metal">原生 Metal（实验 / 维护）</option>
            </select>
          </label>
          <label className="field">
            本地工具链配置
            <input
              aria-label="完整构建配置"
              value={settings.config}
              disabled={busy}
              onChange={(e) =>
                setSettings({ ...settings, config: e.target.value })
              }
            />
          </label>
          <label className="field">
            IPA 构建目录
            <input
              aria-label="完整构建输出目录"
              value={settings.output}
              disabled={busy}
              onChange={(e) =>
                setSettings({ ...settings, output: e.target.value })
              }
            />
          </label>
          <label className="field">
            独立测试 Bundle ID
            <input
              aria-label="测试 Bundle ID"
              value={bundle}
              disabled={busy}
              onChange={(e) => setBundle(e.target.value)}
            />
          </label>
          <label className="field">
            AOT 堆预算（GiB）
            <select
              value={heap}
              disabled={busy}
              onChange={(e) => setHeap(Number(e.target.value))}
            >
              {[6, 7, 8, 9].map((n) => (
                <option key={n}>{n}</option>
              ))}
            </select>
          </label>
          <label className="field">
            编译并发
            <select
              value={parallelism}
              disabled={busy}
              onChange={(e) => setParallelism(Number(e.target.value))}
            >
              {[1, 2, 3, 4, 5, 6, 7, 8].map((n) => (
                <option key={n}>{n}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>
              <input
                type="checkbox"
                checked={unsigned}
                disabled={busy}
                onChange={(e) => setUnsigned(e.target.checked)}
              />{" "}
              导出未签名 IPA
            </span>
            <small>
              未签名 IPA 不能直接安装；签名模式仅使用现有开发证书与匹配的
              profile。
            </small>
          </label>
          {loader === "fabric" && (
            <label className="field">
              <span>
                <input
                  type="checkbox"
                  checked={audited}
                  disabled={busy}
                  onChange={(e) => setAudited(e.target.checked)}
                />{" "}
                已审计本地 Mod，允许在隔离沙盒执行构建期转换
              </span>
              <small>
                沿用下方本地 Mod 目录。未支持机制将记录为 BLOCKED /
                UNSUPPORTED；静态报告不能证明 FUNCTION_PASS。
              </small>
            </label>
          )}
          <div className="command-actions">
            <button
              className="button primary"
              disabled={
                !native ||
                busy ||
                !renderer ||
                !settings.workspace ||
                (loader === "fabric" && (!modsPath || !audited))
              }
              onClick={() => void start()}
            >
              {snapshot?.state === "failed" || snapshot?.state === "cancelled"
                ? "重试完整构建"
                : "开始完整构建"}
            </button>
            <button
              className="button secondary"
              disabled={!busy}
              onClick={() => void cancel()}
            >
              取消构建
            </button>
          </div>
          {!native && (
            <p className="small muted">
              浏览器用于工作流预览；完整构建请启动 macOS 应用。
            </p>
          )}
          {error && (
            <p role="alert" className="form-error">
              {error}
            </p>
          )}
        </div>
        <div>
          <p role="status">
            {snapshot
              ? `${snapshot.state} · ${snapshot.stage}`
              : "等待开始完整构建"}
          </p>
          {snapshot?.error && (
            <p role="alert" className="form-error">
              {snapshot.error}
            </p>
          )}
          <pre
            aria-label="完整构建实时日志"
            className="build-live-log"
            style={{
              maxHeight: 460,
              overflow: "auto",
              whiteSpace: "pre-wrap",
              overflowWrap: "anywhere",
            }}
          >
            {snapshot?.lines.join("\n") ||
              "阶段日志将在此显示。不会虚构百分比或预计剩余时间。"}
          </pre>
          {snapshot && (
            <>
              <p className="small muted">完整日志：{snapshot.logPath}</p>
              <div className="command-actions">
                <button
                  className="button secondary"
                  onClick={() =>
                    void invoke("open_build_output").catch((e) =>
                      setError(String(e)),
                    )
                  }
                >
                  打开输出目录
                </button>
                <button
                  className="button secondary"
                  onClick={() =>
                    void invoke("export_build_log").catch((e) =>
                      setError(String(e)),
                    )
                  }
                >
                  导出完整日志
                </button>
              </div>
            </>
          )}
          {artifact && (
            <div aria-label="IPA 产物清单">
              <h3>IPA 完整性校验通过</h3>
              <p className="small">真机游玩和 Mod 功能需要独立验收。</p>
              <dl style={{ overflowWrap: "anywhere" }}>
                {Object.entries({
                  IPA: artifact.ipa,
                  大小: `${artifact.bytes} bytes`,
                  "SHA-256": artifact.sha256,
                  "源码 SHA": artifact.sourceCommit,
                  渲染器: artifact.renderer,
                  运行模式: artifact.loader,
                  签名: artifact.signature,
                  "AOT 记录": artifact.aotCommand,
                  "Mod 转换报告": artifact.loaderReport || "Vanilla",
                }).map(([key, value]) => (
                  <div key={key}>
                    <dt>{key}</dt>
                    <dd>{value}</dd>
                  </div>
                ))}
              </dl>
              {artifact.signature === "UNSIGNED" && (
                <p className="form-error">
                  未签名：不能直接作为已签名应用安装。
                </p>
              )}
            </div>
          )}
          {snapshot && (
            <button
              className="button secondary"
              onClick={() =>
                void invoke<Record<string, unknown> | null>(
                  "build_adaptation_report",
                )
                  .then(setAdaptation)
                  .catch((e) => setError(String(e)))
              }
            >
              读取 Fabric / MDAF 实际报告
            </button>
          )}
          {adaptation && (
            <details open>
              <summary>Mod 依赖、转换、反射 / 资源、动态类与平台风险</summary>
              <p className="small">
                下列数据来自实际转换报告；运行状态 NOT RUN，不能据此判定
                FUNCTION_PASS。
              </p>
              <pre
                style={{
                  maxHeight: 500,
                  overflow: "auto",
                  whiteSpace: "pre-wrap",
                  overflowWrap: "anywhere",
                }}
              >
                {JSON.stringify(adaptation, null, 2)}
              </pre>
            </details>
          )}
        </div>
      </div>
    </section>
  );
}
