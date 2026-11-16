import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(desktopRoot, "..");

describe("NCL Builder app icon", () => {
  it("keeps the Icon Composer source in the repository", () => {
    const icon = path.join(repoRoot, "NCB.icon", "icon.json");
    expect(fs.existsSync(icon)).toBe(true);
    const document = JSON.parse(fs.readFileSync(icon, "utf8"));
    expect(document["supported-platforms"]["squares"]).toBe("shared");
    expect(document.fill).toBe("system-light");
    expect(document.groups.length).toBeGreaterThan(0);
  });

  it("bundles the compiled assets and points Info.plist at NCB", () => {
    const config = JSON.parse(
      fs.readFileSync(path.join(desktopRoot, "src-tauri", "tauri.conf.json"), "utf8"),
    );
    expect(config.bundle.resources["icon-build/Assets.car"]).toBe("Assets.car");
    expect(config.bundle.resources["icon-build/NCB.icns"]).toBe("NCB.icns");
    const info = fs.readFileSync(path.join(desktopRoot, "src-tauri", "Info.plist"), "utf8");
    expect(info).toContain("CFBundleIconFile");
    expect(info).toContain("CFBundleIconName");
    expect(info).toContain("<string>NCB</string>");
  });
});
