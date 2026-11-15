import { describe, expect, it } from "vitest";
import { inventoryRows, modState } from "./ModList";
import { parseReport } from "./model";

const base = {
  source: "/fixture",
  target_minecraft: "26.1.2",
  status: "STATIC_PREFLIGHT_ONLY",
  source_type: "prism_or_folder",
  fatal: false,
  findings: [],
  mods: [
    { id: "example", name: "示例 Mod", version: "1.0", path: "example.jar" },
  ],
};
describe("Mod inventory", () => {
  it("preserves structured states and never accepts imported verification", () => {
    const report = parseReport({
      ...base,
      mod_inventory: [
        {
          path: "example.jar",
          origin: "local",
          status: "metadata_read",
          findings: [],
          mod: { aot_compatibility: "VERIFIED" },
        },
        {
          path: "mods/remote.jar",
          origin: "manifest",
          status: "pending_download",
          findings: [],
        },
      ],
    });
    expect(inventoryRows(report)[0].mod?.name).toBe("示例 Mod");
    expect(inventoryRows(report)[0].mod?.aot_compatibility).toBe("NOT_TESTED");
    expect(modState(inventoryRows(report)[1])).toBe("pending_download");
  });
  it("keeps old reports usable and scopes findings to the exact JAR", () => {
    const report = parseReport({
      ...base,
      findings: [
        {
          severity: "warning",
          code: "MIXIN_REQUIRES_AOT_WORK",
          message: "example.jar",
        },
        {
          severity: "error",
          code: "INVALID_MOD_JAR",
          message: "other-example.jar: broken",
        },
      ],
    });
    const row = inventoryRows(report)[0];
    expect(modState(row)).toBe("attention");
    expect(row.findings).toHaveLength(1);
    expect(
      modState({
        ...row,
        findings: [
          { severity: "error", code: "INVALID_MOD_JAR", message: "broken" },
        ],
      }),
    ).toBe("unreadable");
  });
  it("rejects invalid inventory and metadata claims", () => {
    for (const row of [
      { path: "x", origin: "local", status: "VERIFIED", findings: [] },
      { path: "x", origin: "local", status: "metadata_read", findings: [] },
      {
        path: "x",
        origin: "local",
        status: "pending_download",
        findings: [{}],
      },
    ])
      expect(() => parseReport({ ...base, mod_inventory: [row] })).toThrow();
  });
});
