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


def launch():
    res = run(["developer", "dvt", "launch", "--userspace", bundle], 90)
    print("launch:", res.stdout.strip() or res.stderr.strip()[-300:])


def pull(label):
    target = root / f"cache-{label}"
    run(["apps", "pull", "--documents", bundle, "/Documents/c0-logs", str(target)])
    logs = sorted(target.rglob("run-*.log"), key=lambda p: p.stat().st_mtime)
    return logs[-1] if logs else None


def cycle(label, window):
    launch()
    deadline = time.time() + 120
    log = None
    while time.time() < deadline:
        time.sleep(8)
        log = pull(label)
        if log and "ready=true" in log.read_text(errors="replace"):
            break
    time.sleep(window)
    log = pull(label)
    text = log.read_text(errors="replace")
    lines = text.splitlines()
    ready_at = next((int(m.group(1)) for l in lines
                     if (m := re.search(r"event=level_load_ready.*upMs=(\d+).*ready=true", l))), None)
    disp = [tuple(map(float, m.groups())) for l in lines
            if (m := re.search(r"display fps=([\d.]+) p95=(\d+)ms long34=(\d+) drops=(\d+)", l))]
    ready_line = next((i for i, l in enumerate(lines) if "ready=true" in l), 0)
    after = disp[max(0, len(disp) - 6):]
    print(f"{label}: readyMs={ready_at} cache={'ready' if 'shader cache ready' in text else 'no'} "
          f"samples={len(disp)} earlyMin={min(d[0] for d in disp[ready_line:] or disp) if disp else None} "
          f"tail={[round(d[0],1) for d in after]}")


if __name__ == "__main__":
    cycle(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 45)
