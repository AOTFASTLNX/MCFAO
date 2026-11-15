import { useMemo, useState } from "react";
import { ChevronRight, Package, Search } from "lucide-react";
import { findingLabels, type ModInventoryEntry, type Report } from "./model";
import { SelectMenu } from "./SelectMenu";

export function inventoryRows(report: Report): ModInventoryEntry[] {
  return (
    report.mod_inventory ??
    report.mods.map((mod) => ({
      path: mod.path,
      origin: report.source_type === "mrpack" ? "embedded" : "local",
      status: mod.environment === "server" ? "server_only" : "metadata_read",
      mod,
      // Older reports have no structured JAR association. Match the exact path
      // followed by the scanner's delimiter, never an arbitrary ID substring.
      findings: report.findings.filter(
        (f) => f.message === mod.path || f.message.startsWith(mod.path + ":"),
      ),
    }))
  );
}

export function modState(row: ModInventoryEntry) {
  if (row.findings.some((f) => f.severity === "error")) return "unreadable";
  if (
    row.status === "metadata_read" &&
    row.findings.some((f) => f.severity === "warning")
  )
    return "attention";
  return row.status;
}
const labels = {
  metadata_read: "已读取",
  attention: "需关注",
  pending_download: "待下载",
  server_only: "仅服务端",
  skipped_optional: "可选 · 可勾选",
  disabled: "已禁用",
  unreadable: "读取失败",
};
const explanations = {
  metadata_read: "已读取 Fabric 元数据；iOS / AOT 兼容性未测试。",
  attention: "已读取元数据，下列机制需要进一步适配或核验。",
  pending_download:
    "整合包清单引用的文件，构建导入时下载并校验；Mod ID、版本和兼容性尚未知。",
  server_only:
    "标记为仅服务端，不用于客户端运行；清单中的服务端文件会在导入时跳过。",
  skipped_optional: "客户端可选文件，可在下一步“资源管理”中勾选保留。",
  disabled: "来源中已禁用，不作为启用的 Mod 参与编译。",
  unreadable: "未能完成静态读取，请查看下方原因。",
};
const origins = {
  manifest: "整合包清单",
  embedded: "包内文件",
  local: "本地实例",
};
const filename = (path: string) => path.split("/").pop() || path;
const PAGE_SIZE = 50;

export default function ModList({ report }: { report: Report }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [limit, setLimit] = useState(PAGE_SIZE);
  const rows = useMemo(() => inventoryRows(report), [report]);
  const counts = useMemo(
    () =>
      rows.reduce<Record<string, number>>((result, row) => {
        const state = modState(row);
        result[state] = (result[state] || 0) + 1;
        return result;
      }, {}),
    [rows],
  );
  const filtered = useMemo(
    () =>
      rows.filter((row) => {
        const text = [row.path, row.mod?.name, row.mod?.id, row.mod?.version]
          .join(" ")
          .toLocaleLowerCase();
        return (
          (filter === "all" || modState(row) === filter) &&
          text.includes(query.trim().toLocaleLowerCase())
        );
      }),
    [rows, query, filter],
  );

  return (
    <section className="mod-browser" aria-label="包内 Mod">
      <button
        className="mod-list-toggle"
        aria-expanded={open}
        aria-controls="mod-list-content"
        onClick={() => setOpen(!open)}
      >
        <Package size={18} aria-hidden="true" />
        <span>
          {open ? "收起 Mod 列表" : "查看 Mod 列表"}
          <small>{rows.length} 个文件 · 名称、版本与状态</small>
        </span>
        <ChevronRight
          size={18}
          className={open ? "expanded" : ""}
          aria-hidden="true"
        />
      </button>
      {open && (
        <div id="mod-list-content" className="mod-list-content">
          <p className="mod-list-hint">
            状态来自本次静态检查；已读取不代表已通过 iOS / AOT
            验证。嵌套依赖数量显示在所属 Mod 详情中。
          </p>
          {!report.mod_inventory && (
            <p className="mod-list-hint">
              旧报告仅包含已读取的 Mod。重新“检查来源”可补全清单中的待下载文件。
            </p>
          )}
          <div className="mod-list-tools">
            <label className="mod-search">
              <Search size={16} aria-hidden="true" />
              <input
                aria-label="搜索 Mod"
                placeholder="搜索名称、ID 或文件名"
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setLimit(PAGE_SIZE);
                }}
              />
            </label>
            <div className="mod-filter">
              状态
              <SelectMenu
                className="mod-filter-select"
                label="筛选 Mod 状态"
                value={filter}
                onChange={(next) => {
                  setFilter(next);
                  setLimit(PAGE_SIZE);
                }}
                options={[
                  { value: "all", label: `全部（${rows.length}）` },
                  ...Object.entries(labels)
                    .filter(([state]) => counts[state])
                    .map(([state, label]) => ({
                      value: state,
                      label: `${label}（${counts[state]}）`,
                    })),
                ]}
              />
            </div>
          </div>
          <p className="mod-result-count" role="status">
            显示 {Math.min(filtered.length, limit)} / {filtered.length} 个文件 ·
            共 {rows.length} 个
          </p>
          {filtered.length === 0 && (
            <p className="mod-empty">
              {rows.length
                ? "没有匹配的 Mod，请尝试其他关键词或选择全部状态。"
                : "当前来源未发现 Mod 文件。"}
            </p>
          )}
          <ul className="mod-list">
            {filtered.slice(0, limit).map((row, index) => {
              const state = modState(row);
              return (
                <li key={row.origin + row.path + index}>
                  <details className="mod-item">
                    <summary>
                      <ChevronRight size={15} aria-hidden="true" />
                      <span className="mod-title">
                        <strong>
                          {row.mod?.name || row.mod?.id || filename(row.path)}
                        </strong>
                        <small>
                          {row.mod
                            ? row.mod.id + " · " + row.mod.version
                            : "ID / 版本待读取"}
                        </small>
                      </span>
                      <span className={"mod-status " + state}>
                        {labels[state]}
                      </span>
                    </summary>
                    <div className="mod-item-detail">
                      <p>{explanations[state]}</p>
                      <dl>
                        <dt>文件</dt>
                        <dd>{row.path}</dd>
                        <dt>来源</dt>
                        <dd>{origins[row.origin]}</dd>
                        <dt>iOS / AOT</dt>
                        <dd>未测试</dd>
                        {row.mod && (
                          <>
                            <dt>运行侧</dt>
                            <dd>
                              {row.mod.environment === "client"
                                ? "客户端"
                                : row.mod.environment === "server"
                                  ? "服务端"
                                  : "通用"}
                            </dd>
                            <dt>构建机制</dt>
                            <dd>
                              {[
                                row.mod.has_mixins && "Mixin",
                                row.mod.has_entrypoints && "入口点",
                                row.mod.has_class_tweaker && "访问修改",
                                row.mod.has_language_adapters && "语言适配器",
                                row.mod.nested_jar_count > 0 &&
                                  row.mod.nested_jar_count + " 个嵌套依赖",
                                row.mod.bundled_native_count > 0 &&
                                  row.mod.bundled_native_count + " 个原生库",
                              ]
                                .filter(Boolean)
                                .join(" · ") || "未发现特殊机制"}
                            </dd>
                          </>
                        )}
                      </dl>
                      {row.findings.length > 0 && (
                        <ul className="mod-issues">
                          {row.findings.map((f, i) => (
                            <li key={i}>
                              <strong>
                                {f.severity === "error"
                                  ? "阻断"
                                  : f.severity === "warning"
                                    ? "注意"
                                    : "信息"}{" "}
                                · {findingLabels[f.code] || f.code}
                              </strong>
                              <span>{f.message}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  </details>
                </li>
              );
            })}
          </ul>
          {filtered.length > limit && (
            <button
              className="text-button"
              onClick={() => setLimit(limit + PAGE_SIZE)}
            >
              显示更多（剩余 {filtered.length - limit} 个）
            </button>
          )}
        </div>
      )}
    </section>
  );
}
