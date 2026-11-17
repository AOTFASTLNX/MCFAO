import { describe, expect, it } from "vitest";
import {
  formatBytes,
  percent,
  selectedBytes,
  unifiedStoragePaths,
  type StoragePlan,
} from "./storageManagement";

describe("storage chart quantities", () => {
  it("creates separate subdirectories under the selected root", () => {
    expect(unifiedStoragePaths("/Volumes/Build/My Files///")).toEqual({
      cache: "/Volumes/Build/My Files/cache",
      builds: "/Volumes/Build/My Files/builds",
      jobs: "/Volumes/Build/My Files/jobs",
      rust: "/Volumes/Build/My Files/rust",
    });
  });
  it("handles empty and unavailable sizes without NaN or overflowing bars", () => {
    expect(percent(1, 0)).toBe(0);
    expect(percent(200, 100)).toBe(100);
    expect(percent(-1, 100)).toBe(0);
    expect(formatBytes(NaN)).toBe("0 B");
    expect(formatBytes(1024 ** 3)).toBe("1.0 GiB");
  });
  it("totals only selected known cleanup categories once", () => {
    const plan = {
      groups: [
        { id: "cache", bytes: 1024 },
        { id: "builds", bytes: 2048 },
      ],
    } as StoragePlan;
    expect(selectedBytes(plan, ["cache", "cache", "unknown"])).toBe(1024);
    expect(selectedBytes(plan, [])).toBe(0);
  });
});
