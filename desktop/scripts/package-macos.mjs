import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";
import fs from "node:fs";

const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(desktopRoot, "..");
if (process.platform !== "darwin") throw new Error("此打包命令需要 macOS。");
if (process.arch !== "arm64") throw new Error("此打包命令需要 Apple Silicon macOS。");
const armCargoBin = path.join(process.env.HOME || "", ".cargo", "bin");
process.env.PATH = armCargoBin + path.delimiter + (process.env.PATH || "");

function run(command, args, cwd = desktopRoot) {
  const r = spawnSync(command, args, { cwd, stdio: "inherit" });
  if (r.error) throw r.error;
  if (r.status !== 0) process.exit(r.status ?? 1);
}

function capture(command, args, cwd = repoRoot) {
  const r = spawnSync(command, args, { cwd, encoding: "utf8" });
  if (r.error) throw r.error;
  if (r.status !== 0) process.exit(r.status ?? 1);
  return r.stdout;
}

function requireExternalDisk() {
  const status = JSON.parse(
    capture("python3", ["-B", "tools/external_storage.py", "--json"]),
  );
  if (!status.available) {
    console.error("外接盘挂载检查未通过，已暂停打包。");
    process.exit(3);
  }
  console.log("外接盘检查通过：" + status.data);
}

function compileBuilderIcon() {
  const source = path.join(repoRoot, "NCB.icon");
  if (!fs.existsSync(path.join(source, "icon.json"))) {
    throw new Error("找不到 Builder 图标源：" + source);
  }
  const out = path.join(desktopRoot, "src-tauri", "icon-build");
  fs.rmSync(out, { recursive: true, force: true });
  fs.mkdirSync(out, { recursive: true });
  run("xcrun", [
    "actool",
    "--compile", out,
    "--platform", "macosx",
    "--minimum-deployment-target", "11.0",
    "--app-icon", "NCB",
    "--standalone-icon-behavior", "all",
    "--output-partial-info-plist", path.join(out, "partial.plist"),
    "--warnings",
    "--errors",
    source,
  ]);
  for (const name of ["Assets.car", "NCB.icns", "partial.plist"]) {
    if (!fs.existsSync(path.join(out, name))) {
      throw new Error("actool 未生成 " + name);
    }
  }
  const partial = capture("/usr/bin/plutil", ["-p", path.join(out, "partial.plist")], desktopRoot);
  if (!partial.includes('"CFBundleIconName" => "NCB"') ||
      !partial.includes('"CFBundleIconFile" => "NCB"')) {
    throw new Error("actool 输出的图标名不是 NCB");
  }
  console.log("已用 Xcode actool 编译 NCB.icon（浅色 / 深色 / 透明）。");
}

function assertIconIdentity(app) {
  const infoPlist = path.join(app, "Contents", "Info.plist");
  for (const key of ["CFBundleIconFile", "CFBundleIconName"]) {
    const value = capture("/usr/bin/plutil", ["-extract", key, "raw", "-o", "-", infoPlist], desktopRoot).trim();
    if (value !== "NCB") {
      throw new Error(key + " 应为 NCB，实际为 " + value);
    }
  }
  const resources = path.join(app, "Contents", "Resources");
  for (const name of ["Assets.car", "NCB.icns"]) {
    if (!fs.existsSync(path.join(resources, name))) {
      throw new Error("应用包缺少 " + name);
    }
  }
}

requireExternalDisk();
compileBuilderIcon();
run("npm", ["run", "tauri", "--", "build", "--debug", "--bundles", "app"]);

const bundleDir = process.env.CARGO_TARGET_DIR
  ? path.join(process.env.CARGO_TARGET_DIR, "debug/bundle/macos")
  : path.join(desktopRoot, "src-tauri/target/debug/bundle/macos");
const builtApp = path.join(bundleDir, "NCL Builder.app");
if (!fs.existsSync(builtApp)) throw new Error("Tauri 未生成 " + builtApp);

const builtInfoPlist = path.join(builtApp, "Contents", "Info.plist");
for (const key of ["CFBundleIconFile", "CFBundleIconName"]) {
  run("/usr/bin/plutil", ["-replace", key, "-string", "NCB", builtInfoPlist]);
}
assertIconIdentity(builtApp);

const deliverDir = path.join(repoRoot, "artifacts/desktop/ncl-builder-ncb-icon");
fs.mkdirSync(deliverDir, { recursive: true });
const app = path.join(deliverDir, "NCL Builder.app");
fs.rmSync(app, { recursive: true, force: true });
run("/usr/bin/rsync", [
  "-a",
  "--exclude", "._*",
  "--exclude", ".DS_Store",
  builtApp + "/",
  app + "/",
]);
assertIconIdentity(app);

run("/usr/bin/codesign", [
  "--force",
  "--deep",
  "--sign", "-",
  "--identifier", "org.fabricaot.desktop",
  app,
]);
run("/usr/bin/codesign", ["--verify", "--deep", "--strict", app]);

const zip = path.join(deliverDir, "NCL Builder.app.zip");
fs.rmSync(zip, { force: true });
run("/usr/bin/ditto", ["-c", "-k", "--norsrc", "--noextattr", "--noacl", "--keepParent", app, zip]);

console.log("本地工作台已打包并完成临时签名：" + app);
console.log("压缩交付包：" + zip);

