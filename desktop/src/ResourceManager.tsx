import { useState, type CSSProperties } from "react";
import { Search } from "lucide-react";
import type { Report, ResourceEntry } from "./model";
import type { ResourceSelection } from "./workflow";
import {
  clientRequirement,
  resourceTier,
  requirementLabels,
  requirementExplanation,
  type ResourceTier,
} from "./resourceClassification";
import { AnimatedNumber } from "./MotionPrimitives";
export const resourceCategories = {
  mods: "Mod",
  resourcepacks: "材质包",
  shaderpacks: "光影包",
  config: "配置与脚本",
  other: "其他资源",
};
const origins = {
  manifest: "清单下载",
  overrides: "包内文件",
  "client-overrides": "客户端覆盖",
  local: "本地实例",
};
const states = {
  available: "可保留",
  server_only: "仅服务端",
  disabled: "来源已禁用",
  unsafe: "不安全路径",
  unsupported: "暂不支持导入",
};
export default function ResourceManager({
  report,
  selection,
  onChange,
}: {
  report: Report | null;
  selection: ResourceSelection | null;
  onChange: (s: ResourceSelection) => void;
}) {
  const [category, setCategory] = useState("all");
  const [tier, setTier] = useState<ResourceTier | "all">("all");
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState(50);
  if (!report?.resources || !report.resources_fingerprint)
    return (
      <div className="resource-empty">
        请返回“游戏内容”重新选择整合包，以读取完整资源清单。
      </div>
    );
  const rows = report.resources;
  const valid =
    selection?.source === report.source &&
    selection.fingerprint === report.resources_fingerprint;
  const kept = new Set(
    valid
      ? selection.included
      : rows.filter((r) => r.default_selected).map((r) => r.id),
  );
  const categoryRows = rows.filter(
    (r) => category === "all" || r.category === category,
  );
  const excludedRequired = rows.filter(
    (r) =>
      r.selectable && clientRequirement(r) === "required" && !kept.has(r.id),
  );
  const filtered = categoryRows.filter(
    (r) =>
      (tier === "all" || resourceTier(r) === tier) &&
      r.path.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()),
  );
  function commit(included: Set<string>) {
    onChange({
      source: report!.source,
      fingerprint: report!.resources_fingerprint!,
      included: rows
        .filter((r) => r.selectable && included.has(r.id))
        .map((r) => r.id),
    });
  }
  function batch(keep: boolean) {
    const next = new Set(kept);
    filtered
      .filter((r) => r.selectable)
      .forEach((r) => (keep ? next.add(r.id) : next.delete(r.id)));
    commit(next);
  }
  function modFor(row: ResourceEntry) {
    return report!.mod_inventory?.find(
      (m) =>
        m.path === row.path ||
        m.path ===
          (row.origin === "overrides"
            ? "overrides/"
            : row.origin === "client-overrides"
              ? "client-overrides/"
              : "") +
            row.path ||
        (row.origin === "local" && row.path === "mods/" + m.path),
    );
  }
  return (
    <section className="resource-manager" aria-label="整合包资源管理">
      <div className="resource-summary">
        <strong>
          已保留 <AnimatedNumber value={kept.size} /> /{" "}
          <AnimatedNumber value={rows.length} /> 项
        </strong>
        <span>取消勾选仅影响本次构建，原整合包文件保持完整。</span>
      </div>
      <p className="mod-list-hint">
        材质包和光影包按所选文件保留；保留光影包不代表当前渲染器支持启用光影。可选
        Mod 由你选择，下载后的依赖与重复版本仍需检查。
      </p>
      <div className="resource-categories" aria-label="资源分类">
        {[["all", "全部"], ...Object.entries(resourceCategories)].map(
          ([key, label]) => (
            <button
              key={key}
              aria-pressed={category === key}
              onClick={() => {
                setCategory(key);
                setLimit(50);
              }}
            >
              {label}
              <span>
                {key === "all"
                  ? rows.length
                  : rows.filter((r) => r.category === key).length}
              </span>
            </button>
          ),
        )}
      </div>
      <div className="resource-grading">
        <span className="resource-filter-label">客户端分级</span>
        <div
          className="resource-categories resource-tiers"
          aria-label="客户端分级"
        >
          {(
            [
              "all",
              "required",
              "optional",
              "unknown",
              "unsupported",
              "unavailable",
            ] as const
          ).map((key) => (
            <button
              key={key}
              aria-pressed={tier === key}
              onClick={() => {
                setTier(key);
                setLimit(50);
              }}
            >
              {key === "all" ? "全部级别" : requirementLabels[key]}
              <span>
                {key === "all"
                  ? categoryRows.length
                  : categoryRows.filter((r) => resourceTier(r) === key).length}
              </span>
            </button>
          ))}
        </div>
        <p className="mod-list-hint">
          必需 /
          可选依据整合包清单的客户端声明；包内和本地资源未声明时列为待确认。
          分级不代表 iOS 兼容性，必需项仍可手动排除。
        </p>
      </div>
      {excludedRequired.length > 0 && (
        <div className="resource-required-warning" role="status">
          <p>
            已排除 {excludedRequired.length}{" "}
            项客户端必需资源，可能导致依赖缺失或启动失败。
          </p>
          <button
            className="text-button"
            onClick={() =>
              commit(new Set([...kept, ...excludedRequired.map((r) => r.id)]))
            }
          >
            恢复必需资源
          </button>
        </div>
      )}
      <div className="mod-list-tools">
        <label className="mod-search">
          <Search size={16} aria-hidden="true" />
          <input
            aria-label="搜索资源"
            placeholder="搜索资源文件名或路径"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setLimit(50);
            }}
          />
        </label>
      </div>
      <div className="resource-actions">
        <button className="text-button" onClick={() => batch(true)}>
          保留当前列表
        </button>
        <button className="text-button" onClick={() => batch(false)}>
          排除当前列表
        </button>
        <button
          className="text-button"
          onClick={() =>
            commit(
              new Set(rows.filter((r) => r.default_selected).map((r) => r.id)),
            )
          }
        >
          恢复默认选择
        </button>
      </div>
      <p role="status" className="mod-result-count">
        当前列表 <AnimatedNumber value={filtered.length} /> 项 · 已保留{" "}
        <AnimatedNumber value={filtered.filter((r) => kept.has(r.id)).length} />{" "}
        项
      </p>
      {!valid && (
        <button className="secondary" onClick={() => commit(kept)}>
          确认资源选择
        </button>
      )}
      {filtered.length === 0 && (
        <p className="resource-empty">没有匹配资源，请切换分类或搜索关键词。</p>
      )}
      <ul className="resource-list">
        {filtered.slice(0, limit).map((row, index) => {
          const metadata = row.category === "mods" ? modFor(row) : undefined;
          return (
            <li
              key={row.id}
              style={{ "--row-index": Math.min(index, 12) } as CSSProperties}
            >
              <div className="resource-row">
                <input
                  type="checkbox"
                  aria-label={
                    "保留 " + row.path + "（" + origins[row.origin] + "）"
                  }
                  checked={kept.has(row.id)}
                  disabled={!row.selectable}
                  onChange={(e) => {
                    const next = new Set(kept);
                    if (e.target.checked) next.add(row.id);
                    else next.delete(row.id);
                    commit(next);
                  }}
                />
                <div className="resource-name">
                  <strong>
                    {metadata?.mod?.name || row.path.split("/").pop()}
                  </strong>
                  <small>{row.path}</small>
                </div>
                <div className="resource-badges">
                  <span
                    className={"mod-status resource-tier " + resourceTier(row)}
                  >
                    {requirementLabels[resourceTier(row)]}
                  </span>
                  <span
                    className={
                      "mod-status " + (!row.selectable ? "attention" : "")
                    }
                  >
                    {!row.selectable
                      ? states[row.status]
                      : kept.has(row.id)
                        ? "将保留"
                        : "已排除"}
                  </span>
                </div>
              </div>
              <details className="resource-detail">
                <summary>查看资源详情</summary>
                <dl>
                  <dt>分类</dt>
                  <dd>{resourceCategories[row.category]}</dd>
                  <dt>来源</dt>
                  <dd>{origins[row.origin]}</dd>
                  <dt>文件数量</dt>
                  <dd>{row.file_count}</dd>
                  <dt>大小</dt>
                  <dd>{(row.bytes / 1024 / 1024).toFixed(2)} MB</dd>
                  <dt>客户端分级</dt>
                  <dd>{requirementLabels[clientRequirement(row)]}</dd>
                  <dt>判定依据</dt>
                  <dd>{requirementExplanation(row)}</dd>
                  {metadata?.mod && (
                    <>
                      <dt>Mod ID / 版本</dt>
                      <dd>
                        {metadata.mod.id} · {metadata.mod.version}
                      </dd>
                    </>
                  )}
                  {row.category === "mods" && (
                    <>
                      <dt>iOS / AOT</dt>
                      <dd>
                        未测试
                        {row.origin === "manifest"
                          ? " · 元数据待下载后读取"
                          : ""}
                      </dd>
                    </>
                  )}
                </dl>
                {metadata?.findings.map((f, i) => (
                  <p key={i}>
                    {f.code} · {f.message}
                  </p>
                ))}
                {row.category === "shaderpacks" && (
                  <p>仅保留光影资源，当前不保证可启用。</p>
                )}
              </details>
            </li>
          );
        })}
      </ul>
      {filtered.length > limit && (
        <button className="text-button" onClick={() => setLimit(limit + 50)}>
          显示更多资源（剩余 {filtered.length - limit} 项）
        </button>
      )}
    </section>
  );
}
