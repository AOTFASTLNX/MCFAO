import os, re, subprocess, sys, time, statistics
from pathlib import Path

root = Path(__file__).parent
py = root / "python"
env = dict(os.environ)
env["PYTHONPATH"] = os.pathsep.join([str(py), str(py / "win32"), str(py / "win32/lib")])
env["PATH"] = str(py / "pywin32_system32") + os.pathsep + env["PATH"]
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
    target = root / f"steady-{label}-{attempt}"
    run(["apps", "pull", "--documents", bundle, "/Documents/c0-logs", str(target)])
    logs = sorted(target.rglob("run-*.log"), key=lambda p: p.stat().st_mtime)
    return logs[-1] if logs else None


def samples(text):
    disp = [tuple(map(float, m.groups())) for l in text.splitlines()
            if (m := re.search(r"display fps=([\d.]+) p95=(\d+)ms long34=(\d+) drops=(\d+)", l))]
    perf = [tuple(map(float, m.groups())) for l in text.splitlines()
            if (m := re.search(r"perf fps=([\d.]+) finish=([\d.]+)ms present=([\d.]+)ms finishP95=(\d+)ms outsideSwapP95=(\d+)ms", l))]
    return disp, perf


label = sys.argv[1]
extra = sys.argv[2:]
settle = int(os.environ.get("BENCH_SETTLE", "90"))
window = int(os.environ.get("BENCH_WINDOW", "90"))
launch(extra)
for attempt in range(1, 13):
    time.sleep(8)
    log = pull(label, attempt)
    if log and "ready=true" in log.read_text(errors="replace"):
        break
else:
    print("no world ready")
    raise SystemExit(2)
time.sleep(settle)
log = pull(label, 70)
disp, perf = samples(log.read_text(errors="replace"))
offset = len(disp)
print("settled samples before window:", offset)
time.sleep(window)
log = pull(label, 99)
disp, perf = samples(log.read_text(errors="replace"))
disp, perf = disp[offset:], perf[offset:]
if not disp:
    print("no window samples")
    raise SystemExit(3)
fps = [d[0] for d in disp]
print(f"{label} {extra} window={len(fps)} min={min(fps):.1f} median={statistics.median(fps):.1f} "
      f"max={max(fps):.1f} below50={sum(f < 50 for f in fps)} below40={sum(f < 40 for f in fps)} "
      f"long34={sum(d[2] for d in disp):.0f} drops={sum(d[3] for d in disp):.0f} "
      f"finishP95={statistics.median(p[3] for p in perf) if perf else None} "
      f"outsideP95={statistics.median(p[4] for p in perf) if perf else None}")
