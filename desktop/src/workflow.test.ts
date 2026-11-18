import { describe, it, expect } from "vitest";
import {
  buildProblems,
  defaultForm,
  explainError,
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
};
describe("executable workflow", () => {
  it("unsigned mode skips signing fields while retaining build requirements", () => {
    const unsigned = {
      ...form,
      unsigned: true,
      exportOptions: "",
      team: "BAD",
    };
    expect(buildProblems(unsigned, report, true)).toEqual([]);
    expect(
      buildProblems({ ...unsigned, config: "" }, report, true).join(),
    ).toContain("构建配置");
    const restored = restoreForm(JSON.stringify(unsigned));
    expect(restored.unsigned).toBe(true);
    expect(() => restoreForm(JSON.stringify({ unsigned: "yes" }))).toThrow();
  });
  it("keeps a custom icon with its layout options across restarts", () => {
    const custom = {
      ...form,
      icon: "/art/Brand.icon",
      iconFit: "fill" as const,
      iconBackground: "#FFFFFF",
      iconPadding: 12,
    };
    const restored = restoreForm(JSON.stringify(custom));
    expect(restored.icon).toBe("/art/Brand.icon");
    expect(restored.iconFit).toBe("fill");
    expect(restored.iconBackground).toBe("#FFFFFF");
    expect(restored.iconPadding).toBe(12);
    expect(restoreForm(null).icon).toBe("");
    expect(restoreForm(null).iconFit).toBe("fit");
  });
  it("rejects malformed icon settings", () => {
    expect(() =>
      restoreForm(JSON.stringify({ ...form, iconFit: "stretch" })),
    ).toThrow("缩放");
    expect(() =>
      restoreForm(JSON.stringify({ ...form, iconBackground: "red" })),
    ).toThrow("背景");
    expect(() =>
      restoreForm(JSON.stringify({ ...form, iconPadding: 31 })),
    ).toThrow("留白");
    expect(() =>
      restoreForm(JSON.stringify({ ...form, iconPadding: 1.5 })),
    ).toThrow("留白");
  });
  it("flags unsupported icon files before a build starts", () => {
    expect(
      buildProblems({ ...form, icon: "/art/notes.txt" }, report, true).join(),
    ).toContain("图标");
    expect(
      buildProblems({ ...form, icon: "/art/Brand.icon" }, report, true),
    ).toEqual([]);
    expect(
      buildProblems({ ...form, icon: "/art/Brand.SVG" }, report, true),
    ).toEqual([]);
  });
  it("requires selection for resource-aware reports within the session", () => {
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
      buildProblems(
        { ...form, resourceSelection: { ...resourceSelection, included: [] } },
        resourceReport,
        true,
      ).join(),
    ).toContain("至少保留");
  });
  it("allows complete checked Fabric input", () =>
    expect(buildProblems(form, report, true)).toEqual([]));
  it("requires a desktop host", () =>
    expect(buildProblems(form, report, false).join()).toContain("桌面"));
  it("rejects an imported report for a different path", () =>
    expect(
      buildProblems({ ...form, source: "/other" }, report, true).join(),
    ).toContain("重新选择整合包"));
  it("blocks a report with errors", () =>
    expect(
      buildProblems(form, { ...report, fatal: true }, true).join(),
    ).toContain("阻断"));
  it("warns about mismatched Loader versions without blocking", () =>
    expect(
      buildProblems(form, { ...report, fabric_loader_version: "0.1" }, true),
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
  it("keeps invalid source requirements when forcing compilation", () => {
    const forced = { ...form, forceCompile: true };
    expect(
      buildProblems(forced, { ...report, fatal: true }, true).join(),
    ).toContain("阻断");
    expect(buildProblems(forced, null, true).join()).toContain(
      "重新选择整合包",
    );
  });
  it("never restores a stored pack or its resource selection", () => {
    const restored = restoreForm(
      JSON.stringify({
        ...form,
        resourceSelection: {
          source: form.source,
          fingerprint: "a".repeat(64),
          included: ["local:mods/one.jar"],
        },
      }),
    );
    expect(restored.source).toBe("");
    expect(restored.resourceSelection).toBeNull();
  });
  it("requires force mode to be selected again after reopening", () => {
    expect(
      restoreForm(JSON.stringify({ ...form, forceCompile: true })).forceCompile,
    ).toBe(false);
  });
  it("supports vanilla without a mod source", () =>
    expect(
      buildProblems({ ...form, loader: "vanilla", source: "" }, null, true),
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

  it("explains an AOT heap exhaustion instead of echoing the raw error", () => {
    const error = [
      "aot 失败（退出码 2）",
      "Terminating due to java.lang.OutOfMemoryError: Java heap space",
      " - 6.68GB of memory (34.6% of system memory, set via '-Xmx7g')",
    ].join("\n");
    const explained = explainError(error, "aot");
    expect(explained?.title).toBe("Java 25 原生编译内存不足");
    expect(explained?.cause).toContain("7 GiB");
    expect(explained?.next.length).toBeGreaterThan(1);
    expect(explained?.retryHelps).toBe(false);
  });

  it("explains the native-image failure the compiler now reports", () => {
    const error = [
      "aot 失败（退出码 2）",
      "Native Image stopped before producing an image (exit 2). Logs: /x/analysis",
      "com.oracle.svm.driver.NativeImage$NativeImageError",
      "Terminating due to java.lang.OutOfMemoryError: Java heap space",
      "The Native Image build process ran out of memory.",
    ].join("\n");
    expect(explainError(error, "aot")?.title).toBe("Java 25 原生编译内存不足");
  });

  it("marks input fingerprint conflicts as retryable", () => {
    const explained = explainError(
      "build 失败（退出码 2）\nmcfao build: Build inputs changed. Use a new output.",
      "fabric",
    );
    expect(explained?.title).toBe("构建输入与旧目录不一致");
    expect(explained?.retryHelps).toBe(true);
  });

  it("recognises a truncated download as a network problem", () => {
    const explained = explainError(
      "<urlopen error [SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol (_ssl.c:1016)>",
      "source",
    );
    expect(explained?.title).toContain("网络中断");
    expect(explained?.retryHelps).toBe(true);
  });

  it("leaves unrecognised failures to the raw output", () => {
    expect(explainError("something unexpected", "aot")).toBeNull();
    expect(explainError("   ", "aot")).toBeNull();
  });

  it("explains an ambiguous export directory", () => {
    const explained = explainError(
      "export 失败（退出码 2）\nmcfao export: Expected one exported IPA: /x/export",
      "archive",
    );
    expect(explained?.title).toBe("导出目录里不止一个 IPA");
    expect(explained?.retryHelps).toBe(true);
  });

  it("explains a legacy exclusion check that recorded no cause", () => {
    const explained = explainError(
      "失败原因不是可确认的静态 AOT 排除项",
      "fabric",
    );
    expect(explained?.title).toBe("构建在 Fabric 检查阶段停止");
    expect(explained?.retryHelps).toBe(true);
  });
});
