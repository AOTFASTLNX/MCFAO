import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
if (process.platform !== "darwin") throw new Error("此打包命令需要 macOS。");
function run(command, args) {
  const r = spawnSync(command, args, { cwd: root, stdio: "inherit" });
  if (r.error) throw r.error;
  if (r.status !== 0) process.exit(r.status ?? 1);
}
run("npm", ["run", "tauri", "--", "build", "--debug", "--bundles", "app"]);
const app = path.resolve(
  root,
  process.env.CARGO_TARGET_DIR
    ? path.join(
        process.env.CARGO_TARGET_DIR,
        "debug/bundle/macos/NCL Builder.app",
      )
    : "src-tauri/target/debug/bundle/macos/NCL Builder.app",
);
run("/usr/bin/codesign", [
  "--force",
  "--deep",
  "--sign",
  "-",
  "--identifier",
  "org.fabricaot.desktop",
  app,
]);
run("/usr/bin/codesign", ["--verify", "--deep", "--strict", app]);
console.log("本地工作台已打包并完成临时签名：" + app);
