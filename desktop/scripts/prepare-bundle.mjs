import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../..",
);
const output = path.join(root, "desktop/src-tauri/bundle-source");
const temporary = output + "-" + process.pid;
const done = spawnSync(
  "python3",
  ["-B", path.join(root, "tools/bundle_source.py"), "--output", temporary],
  { stdio: "inherit" },
);
if (done.status !== 0) process.exit(done.status || 1);
// Only this generated source staging directory is replaced; source data and builds are untouched.
if (fs.existsSync(output))
  fs.renameSync(output, output + "-previous-" + Date.now());
fs.renameSync(temporary, output);
