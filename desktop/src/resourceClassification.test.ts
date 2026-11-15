import { describe, it, expect } from "vitest";
import {
  clientRequirement,
  resourceTier,
  requirementExplanation,
} from "./resourceClassification";
import { parseReport, type ResourceEntry } from "./model";
const row: ResourceEntry = {
  id: "local:mods/a.jar",
  path: "mods/a.jar",
  origin: "local",
  category: "mods",
  status: "available",
  optional: false,
  selectable: true,
  default_selected: true,
  bytes: 1,
  file_count: 1,
};
describe("resource client grading", () => {
  it("uses manifest requirements independently from inclusion state", () => {
    expect(
      clientRequirement({
        ...row,
        origin: "manifest",
        default_selected: false,
      }),
    ).toBe("required");
    expect(
      clientRequirement({
        ...row,
        origin: "manifest",
        optional: true,
        default_selected: true,
      }),
    ).toBe("optional");
    expect(clientRequirement(row)).toBe("unknown");
    expect(clientRequirement({ ...row, origin: "client-overrides" })).toBe(
      "unknown",
    );
    expect(requirementExplanation(row)).toContain("未声明");
  });
  it("separates server-only and unavailable entries", () => {
    expect(
      resourceTier({ ...row, status: "server_only", selectable: false }),
    ).toBe("unsupported");
    for (const status of ["disabled", "unsafe", "unsupported"] as const)
      expect(resourceTier({ ...row, status, selectable: false })).toBe(
        "unavailable",
      );
  });
  it("normalizes untrusted and older report grading from actual import evidence", () => {
    const report = {
      source: "/tmp/a.mrpack",
      status: "STATIC_PREFLIGHT_ONLY",
      source_type: "mrpack",
      target_minecraft: "26.1.2",
      mods: [],
      findings: [],
      fatal: false,
      resources_fingerprint: "a".repeat(64),
      resources: [{ ...row, client_requirement: "required" }],
    };
    expect(parseReport(report).resources![0].client_requirement).toBe(
      "unknown",
    );
    expect(() =>
      parseReport({
        ...report,
        resources: [{ ...row, client_requirement: "invalid" }],
      }),
    ).toThrow();
    const remote = {
      ...row,
      origin: "manifest",
      id: "manifest:mods/a.jar",
      optional: true,
    };
    expect(
      parseReport({ ...report, resources: [remote] }).resources![0]
        .client_requirement,
    ).toBe("optional");
  });
});
