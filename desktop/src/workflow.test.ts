import { describe, it, expect } from "vitest";
import {
  buildProblems,
  defaultForm,
  isActive,
  mergeJob,
  restoreForm,
  type BuildJob,
} from "./workflow";
import { parseReport } from "./model";
const report = parseReport({
  source: "/fixture",
  target_minecraft: "26.1.2",
  source_type: "prism_or_folder",
  status: "STATIC_PREFLIGHT_ONLY",
  fabric_loader_version: "0.19.3",
  fatal: false,
  findings: [],
  mods: [],
});
const form = {
  ...defaultForm,
  workspace: "/repo",
  config: "/config",
  exportOptions: "/export",
  output: "/out",
  source: "/fixture",
  audited: true,
};
describe("executable workflow", () => {
  it("requires selection for resource-aware reports and retains user choices on reopen", () => {
    const resourceReport = {
      ...report,
      resources_fingerprint: "a".repeat(64),
      resources: [
        {
          id: "local:mods/one.jar",
          path: "mods/one.jar",
          origin: "local" as const,
          category: "mods" as const,
          status: "available" as const,
          optional: false,
          selectable: true,
          default_selected: true,
          bytes: 10,
          file_count: 1,
        },
      ],
    };
    expect(buildProblems(form, resourceReport, true).join()).toContain(
      "资源管理",
    );
    const resourceSelection = {
      source: form.source,
      fingerprint: "a".repeat(64),
      included: ["local:mods/one.jar"],
    };
    expect(
      buildProblems({ ...form, resourceSelection }, resourceReport, true),
    ).toEqual([]);
    expect(
      restoreForm(JSON.stringify({ ...form, resourceSelection }))
        .resourceSelection,
    ).toEqual(resourceSelection);
    expect(
      buildProblems(
        { ...form, resourceSelection: { ...resourceSelection, included: [] } },
        resourceReport,
        true,
      ).join(),
    ).toContain("至少保留");
    expect(() =>
      restoreForm(
        JSON.stringify({
          ...form,
          resourceSelection: { ...resourceSelection, included: [5] },
        }),
      ),
    ).toThrow();
  });
  it("allows complete checked Fabric input", () =>
    expect(buildProblems(form, report, true)).toEqual([]));
  it("requires a desktop host", () =>
    expect(buildProblems(form, report, false).join()).toContain("桌面"));
  it("rejects an imported report for a different path", () =>
    expect(
      buildProblems({ ...form, source: "/other" }, report, true).join(),
    ).toContain("当前来源"));
  it("blocks a report with errors", () =>
    expect(
      buildProblems(form, { ...report, fatal: true }, true).join(),
    ).toContain("阻断"));
  it("requires explicit audit for each session", () => {
    expect(
      buildProblems({ ...form, audited: false }, report, true).join(),
    ).toContain("审计");
    expect(restoreForm(JSON.stringify(form)).audited).toBe(false);
  });
  it("warns about mismatched Loader versions without blocking", () =>
    expect(
      buildProblems(
        form,
        { ...report, fabric_loader_version: "0.1" },
        true,
      ),
    ).toEqual([]));
  it("requires valid team identifiers", () =>
    expect(
      buildProblems({ ...form, team: "invalid" }, report, true).join(),
    ).toContain("Team ID"));
  it("allows an explicit Loader override", () => {
    expect(
      buildProblems(
        { ...form, forceCompile: true },
        { ...report, fabric_loader_version: "0.19.2" },
        true,
      ),
    ).toEqual([]);
  });
  it("keeps invalid sources and audit requirements when forcing compilation", () => {
    const forced = { ...form, forceCompile: true, audited: false };
    expect(
      buildProblems(forced, { ...report, fatal: true }, true).join(),
    ).toContain("阻断");
    expect(buildProblems(forced, report, true).join()).toContain("审计");
    expect(buildProblems(forced, null, true).join()).toContain("检查当前来源");
  });
  it("requires force mode to be selected again after reopening", () => {
    expect(
      restoreForm(JSON.stringify({ ...form, forceCompile: true })).forceCompile,
    ).toBe(false);
  });
  it("supports vanilla without mod source or audit", () =>
    expect(
      buildProblems(
        { ...form, loader: "vanilla", source: "", audited: false },
        null,
        true,
      ),
    ).toEqual([]));
  it("validates stored settings before use", () => {
    expect(() => restoreForm("[]")).toThrow();
    expect(() => restoreForm('{"workspace":9}')).toThrow();
  });
  it("deduplicates jobs and preserves chronological order", () => {
    const a = {
      id: "a",
      startedAt: "2026-11-01",
      state: "running",
    } as BuildJob;
    const b = { id: "b", startedAt: "2026-11-02", state: "failed" } as BuildJob;
    const result = mergeJob([a, b], { ...a, state: "succeeded" });
    expect(result.map((j) => j.id)).toEqual(["b", "a"]);
    expect(result[1].state).toBe("succeeded");
  });
  it("treats cancellation as active until the worker stops", () => {
    expect(isActive({ state: "cancelling" } as BuildJob)).toBe(true);
    expect(isActive({ state: "cancelled" } as BuildJob)).toBe(false);
  });
});
