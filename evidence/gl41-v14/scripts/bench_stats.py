import re, sys, statistics
from pathlib import Path
root = Path(sys.argv[1])
logs = sorted(root.rglob("run-*.log"), key=lambda p: p.stat().st_mtime)
text = logs[-1].read_text(errors="replace")
lines = text.splitlines()
start = next((i for i,l in enumerate(lines) if "level_load_ready" in l and "ready=true" in l), 0)
disp = [tuple(map(float, m.groups())) for l in lines[start:] if (m := re.search(r"display fps=([\d.]+) p95=(\d+)ms long34=(\d+) drops=(\d+)", l))]
perf = [tuple(map(float, m.groups())) for l in lines[start:] if (m := re.search(r"perf fps=([\d.]+) finish=([\d.]+)ms present=([\d.]+)ms finishP95=(\d+)ms outsideSwapP95=(\d+)ms", l))]
fps = [d[0] for d in disp]
print(f"label={sys.argv[2]} log={logs[-1].name} samples={len(fps)}")
if fps:
    q = statistics.quantiles(fps, n=20) if len(fps) > 4 else []
    print(f"fps min={min(fps):.1f} median={statistics.median(fps):.1f} max={max(fps):.1f} p05={q[0]:.1f} p95={q[-1]:.1f} long34={sum(d[2] for d in disp):.0f} drops={sum(d[3] for d in disp):.0f}")
if perf:
    print(f"finish avg={statistics.mean(p[1] for p in perf):.2f}ms p95={statistics.median(p[3] for p in perf):.0f}ms outside p95={statistics.median(p[4] for p in perf):.0f}ms")
