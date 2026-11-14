import os, re, subprocess, sys, time, statistics
from pathlib import Path
root = Path(__file__).parent
py = root / "python"
env = dict(os.environ)
env["PYTHONPATH"] = os.pathsep.join([str(py), str(py/"win32"), str(py/"win32/lib")])
env["PATH"] = str(py/"pywin32_system32") + os.pathsep + env["PATH"]
bundle = "app.perseus4004.sunset349"

def run(args, timeout=180):
    return subprocess.run([sys.executable, "-m", "pymobiledevice3", *args], env=env,
                          capture_output=True, text=True, timeout=timeout)

def launch(extra):
    args = ["developer", "dvt", "launch", "--userspace"]
    for item in extra:
        args += ["--env", item]
    args.append(bundle)
    res = run(args, 90)
    print("launch:", res.stdout.strip() or res.stderr.strip()[-300:])

def pull(label, attempt):
    target = root / f"bench-{label}-{attempt}"
    res = run(["apps", "pull", "--documents", bundle, "/Documents/c0-logs", str(target)])
    logs = sorted(target.rglob("run-*.log"), key=lambda p: p.stat().st_mtime)
    return logs[-1] if logs else None

def stats(text):
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if "level_load_ready" in l and "ready=true" in l), 0)
    disp = [tuple(map(float, m.groups())) for l in lines[start:]
            if (m := re.search(r"display fps=([\d.]+) p95=(\d+)ms long34=(\d+) drops=(\d+)", l))]
    perf = [tuple(map(float, m.groups())) for l in lines[start:]
            if (m := re.search(r"perf fps=([\d.]+) finish=([\d.]+)ms present=([\d.]+)ms finishP95=(\d+)ms outsideSwapP95=(\d+)ms", l))]
    if not disp:
        return None
    fps = [d[0] for d in disp]
    return {"n": len(fps), "min": min(fps), "median": statistics.median(fps), "max": max(fps),
            "long34": sum(d[2] for d in disp), "drops": sum(d[3] for d in disp),
            "finishP95": statistics.median(p[3] for p in perf) if perf else None,
            "outsideP95": statistics.median(p[4] for p in perf) if perf else None}

label = sys.argv[1]
extra = sys.argv[2:]
settle = int(os.environ.get("BENCH_SETTLE", "35"))
launch(extra)
log = None
ready_text = None
for attempt in range(1, 13):
    time.sleep(8)
    log = pull(label, attempt)
    if log is None:
        continue
    body = log.read_text(errors="replace")
    if "ready=true" in body and "display fps=" in body:
        ready_text = body
        print("ready after", attempt * 8, "s:", log.name)
        break
if ready_text is None:
    print("no world-ready sample")
    raise SystemExit(2)
time.sleep(settle)
log = pull(label, 99)
result = stats(log.read_text(errors="replace"))
print(label, extra, result)

