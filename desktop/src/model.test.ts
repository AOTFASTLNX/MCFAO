import { describe, expect, it } from "vitest";
import { execFileSync } from "node:child_process";
import {
  DEFAULT_SETTINGS,
  makeInstance,
  parseReport,
  parseSavedState,
  prepareCommand,
  quoteArgument,
  sourceName,
  upsertInstance,
} from "./model";
const report = {
  source: "/pack/My World.mrpack",
  target_minecraft: "26.1.2",
  status: "STATIC_PREFLIGHT_ONLY",
  source_type: "mrpack",
  fatal: false,
  findings: [],
  mods: [],
};

describe("preflight report boundary", () => {
  it("accepts the actual metadata-only schema", () => {
    expect(parseReport(report).source).toBe(report.source);
  });
  it("does not trust claimed iOS verification in imported reports", () => {
    const value = parseReport({
      ...report,
      aot_ios_verified: true,
      mods: [
        {
          id: "fixture",
          version: "1",
          path: "fixture.jar",
          aot_compatibility: "VERIFIED",
        },
      ],
    });
    expect(value.aot_ios_verified).toBe(false);
    expect(value.mods[0].aot_compatibility).toBe("NOT_TESTED");
  });
  it("treats error findings as fatal even if the flag is false", () => {
    expect(
      parseReport({
        ...report,
        findings: [
          {
            severity: "error",
            code: "WRONG_MC_VERSION",
            message: "Wrong version",
          },
        ],
      }).fatal,
    ).toBe(true);
  });
  it.each([
    {},
    null,
    { ...report, status: "VERIFIED" },
    { ...report, mods: [{}] },
    { ...report, findings: [{ severity: "whatever" }] },
    { ...report, manifest_files: -1 },
  ])("rejects invalid report %j", (value) => {
    expect(() => parseReport(value)).toThrow();
  });
  it("uses the last path component on either desktop OS", () => {
    expect(sourceName(parseReport(report))).toBe("My World");
    expect(
      sourceName(
        parseReport({ ...report, source: "C:\\Prism\\instances\\My World\\" }),
      ),
    ).toBe("My World");
  });
  it("deduplicates imports by source without merging unrelated instances", () => {
    const first = makeInstance(parseReport(report));
    const next = makeInstance(parseReport(report));
    expect(upsertInstance([first], next)).toEqual([next]);
  });
  it("round-trips stored state and rejects corruption", () => {
    const value = {
      instances: [makeInstance(parseReport(report))],
      settings: DEFAULT_SETTINGS,
    };
    expect(parseSavedState(JSON.stringify(value))).toEqual(value);
    expect(() => parseSavedState("{broken")).toThrow();
  });
});
describe("reviewable build command", () => {
  const settings = {
    ...DEFAULT_SETTINGS,
    workspace: "/tmp/My Project",
    config: "/tmp/config.json",
    output: "/tmp/build-output",
  };
  it("uses prepare-only without granting an audit bypass", () => {
    const command = prepareCommand(settings, "/tmp/mods");
    expect(command).toContain("'--prepare-only'");
    expect(command).not.toContain("--audited-mods");
    expect(command).toContain("'26.1.2'");
  });
  it("preserves hostile-looking arguments literally through a POSIX shell", () => {
    const value = "a'b $(echo BAD); 中文 folder";
    const result = execFileSync(
      "/bin/sh",
      ["-c", "printf '%s' " + quoteArgument(value)],
      { encoding: "utf8" },
    );
    expect(result).toBe(value);
  });
  it("quotes Windows PowerShell apostrophes", () => {
    expect(quoteArgument("C:\\It's mine", true)).toBe("'C:\\It''s mine'");
  });
  it.each(["a\nb", "a\rb", "a\0b"])("rejects control characters", (value) => {
    expect(() => quoteArgument(value)).toThrow();
  });
  it("requires all file paths", () => {
    expect(() => prepareCommand(DEFAULT_SETTINGS, "")).toThrow();
  });
});
