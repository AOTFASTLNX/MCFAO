#!/usr/bin/env python3
"""Mine a simulator smoke log for per-Mod initialisation evidence.

`docs/MOD_COMPATIBILITY_MATRIX.md` refuses to upgrade a Mod past `BUILD_PASS` on build
success alone: `LOAD_PASS` needs a line in `game.log` proving the Mod's own code ran and
initialised. Hunting those 100+ lines by hand every pack is the slow part of the loop, so this
tool turns it into a repeatable pass:

    python3 -B tools/scan_mod_evidence.py --build artifacts/mcfao/fabric-pack-87

For each Mod in the fabric stage report it builds search tokens (Mod id, display name, the
package and class names of every declared entrypoint), then keeps only log lines that look like
an initialisation / registration event. Stack frames, `WARN`/`ERROR` lines and lines that only
mention a resource path are rejected - a Mod that logged a warning has not proven it is healthy.

`--emit-evidence` additionally writes the strong matches into the manual evidence table as
`LOAD_PASS` candidates. Existing keys are never overwritten: `FUNCTION_PASS` and
`DEVICE_PASS` need human observation and must not be downgraded by a scanner.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDS = ROOT / "artifacts" / "mcfao"
EVIDENCE = ROOT / "docs" / "MOD_MATRIX_EVIDENCE.json"

#: A line proves the Mod ran only if it announces one of these verbs.
INIT_KEYWORDS = (
    "initializ", "initialis", "registered", "registering", "loading", "loaded",
    "starting", "started", "setup", "enabled", "hooked", "injected", "constructed",
)

#: Lines that are about vanilla assets mention Mod names by accident (`assets/<mod>/...`).
ASSET_NOISE = ("assets/", "data/", "#", "jar:", ".png", ".json", ".ogg", ".class")

#: Single-token names shorter than this match too much prose to be evidence.
MIN_TOKEN = 4


def read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def stage_report(build: Path, stage: str):
    matches = sorted(build.glob(f"{stage}/*/product/result.json"))
    return read_json(matches[0]) if matches else None


def clean_text(value: str) -> str:
    """Minecraft log lines carry `§` colour codes and are wrapped in `[...]` prefixes."""
    return re.sub(r"§.", "", value)


def tokens_for(mod: dict, entrypoints: list[dict]) -> list[tuple[str, str]]:
    """`(token, kind)` pairs, longest first so the strongest match wins the tie-break.

    `kind` records how identifying the token is: a class or package name can only appear because
    the Mod's own code logged it, a display name is nearly as good, while a bare Mod id is weak
    (`shader registered` is vanilla prose, not proof that a Mod named `shader` ran).
    """
    tokens: list[tuple[str, str]] = []
    name = (mod.get("name") or "").strip()
    if len(name) >= MIN_TOKEN:
        tokens.append((name, "name"))
    mod_id = (mod.get("id") or "").strip()
    if len(mod_id) >= MIN_TOKEN:
        tokens.append((mod_id, "id"))
    for entry in entrypoints:
        definition = entry.get("definition") or ""
        if definition:
            tokens.append((definition.rsplit(".", 1)[-1], "class"))
            package = definition.rsplit(".", 1)[0]
            if package:
                tokens.append((package, "class"))
    seen, unique = set(), []
    for token, kind in tokens:
        key = token.lower()
        if len(token) >= MIN_TOKEN and key not in seen:
            seen.add(key)
            unique.append((token, kind))
    return sorted(unique, key=lambda item: len(item[0]), reverse=True)


def entrypoints_by_mod(report: dict) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for entry in (report.get("transform") or {}).get("entrypoints", []) or []:
        grouped.setdefault(entry.get("mod", ""), []).append(entry)
    return grouped


#: Minecraft wraps every record as `[12:32:48] [Render thread/INFO]: ...`. Requiring the level
#: tag rejects stack-trace continuations such as a bare `java.lang.RuntimeException: ...` header,
#: which mention a Mod's class without saying anything about its health.
LEVEL_TAG = re.compile(r"/(INFO|STDOUT|DEBUG|WARN|ERROR)\]")


def level_of(line: str) -> str | None:
    match = LEVEL_TAG.search(line)
    return match.group(1) if match else None


def is_candidate(line: str) -> bool:
    stripped = line.strip()
    if stripped.startswith("at ") or stripped.startswith("...") or stripped.startswith("Caused by"):
        return False
    if level_of(stripped) is None:
        return False
    lower = stripped.lower()
    if "[stdout]" in lower and "initializ" not in lower:
        return False
    if not any(keyword in lower for keyword in INIT_KEYWORDS):
        return False
    if any(noise in lower for noise in ASSET_NOISE):
        return False
    return True


def is_brand(token: str) -> bool:
    """A token distinctive enough that a case-insensitive prose hit is still about the Mod.

    `TerraBlender` / `ImmediatelyFast` / `terrablender` survive case folding because of the inner
    capital or the length; `Shader` does not - `Builtin shader registered` is vanilla prose.
    """
    return any(character.isupper() for character in token[1:]) or len(token) >= 10


def strength_of(line: str, mod_id: str, tokens: list[tuple[str, str]]) -> tuple[str, str] | None:
    """`(token, strength)` for the strongest identifying mention on this line."""
    lowered = line.lower()
    # Exact casing: class names and display names keep it, prose does not.
    for token, kind in tokens:
        if kind != "id" and token in line:
            return token, kind
    # A Mod id is convincing when it is used as a namespace: `backpacked:slot`,
    # `snownee.jade.addon`, `[Indigo]`.
    if f"{mod_id}:" in lowered or f"{mod_id}." in lowered or f"[{mod_id}]" in lowered:
        return mod_id, "namespace"
    for token, _ in tokens:
        if is_brand(token) and token.lower() in lowered:
            return token, "brand"
    for token, kind in tokens:
        if kind == "id" and token.lower() in lowered:
            return token, "id"
    return None


#: The exporter prints one of these after each entrypoint callback returns successfully, so the
#: line is direct proof that the Mod's own initialiser ran instead of merely being linked.
DISPATCH_MARKER = "[MCFAO_ENTRYPOINT] mod="
DISPATCH_RE = re.compile(r"\[MCFAO_ENTRYPOINT\] mod=(?P<mod>\S+) stage=(?P<stage>\S+) class=(?P<cls>\S+)")


def dispatch_lines(lines: list[tuple[int, str]]) -> dict[str, dict]:
    """`mod id -> {line, stage, cls}` from the exporter's own dispatch trace."""
    found: dict[str, dict] = {}
    for number, text in lines:
        match = DISPATCH_RE.search(text)
        if match:
            found.setdefault(match.group("mod"), {
                "line": number, "stage": match.group("stage"), "cls": match.group("cls"),
            })
    return found


def scan(log: Path, mods: list[dict], grouped: dict[str, list[dict]]) -> dict:
    lines = log.read_text(errors="replace").splitlines()
    prepared = [(number, clean_text(line)) for number, line in enumerate(lines, 1)]
    dispatched = dispatch_lines(prepared)
    results: dict[str, dict] = {}
    for mod in mods:
        mod_id = mod.get("id") or ""
        tokens = tokens_for(mod, grouped.get(mod_id, []))
        hits = []
        for number, text in prepared:
            if DISPATCH_MARKER in text:
                continue
            if not is_candidate(text):
                continue
            match = strength_of(text, mod_id, tokens)
            if match is None:
                continue
            token, strength = match
            hits.append({"line": number, "token": token, "strength": strength,
                         "severity": level_of(text), "text": text.strip()[:220]})
        trace = dispatched.get(mod_id)
        clean = [hit for hit in hits
                 if hit["severity"] in {"INFO", "STDOUT", "DEBUG"} and hit["strength"] != "id"]
        results[mod_id] = {
            "mod": mod_id,
            "name": mod.get("name") or mod_id,
            "tokens": [token for token, _ in tokens[:5]],
            "hits": hits[:6],
            # Only a healthy line that names the Mod unambiguously counts as proof: a warning
            # proves the code ran, not that it works, and a bare id match proves nothing.
            "clean": clean,
            "dispatched": trace,
        }
    return results


def summarise(results: dict) -> str:
    rows = sorted(results.values(), key=lambda row: (row["dispatched"] is None,
                                                     -len(row["clean"]), row["mod"]))
    dispatched = [row for row in rows if row["dispatched"]]
    proven = [row for row in rows if row["clean"] and not row["dispatched"]]
    warned = [row for row in rows if not row["clean"] and row["hits"] and not row["dispatched"]]
    missing = [row for row in rows if not row["hits"] and not row["dispatched"]]
    out = [
        f"{len(rows)} mods: {len(dispatched)} entrypoint dispatch, "
        f"{len(proven)} own init line, {len(warned)} only warnings, {len(missing)} silent",
        "",
        f"{'mod':28} {'line':>6}  evidence",
    ]
    for row in dispatched:
        hit = row["dispatched"]
        out.append(f"{row['mod']:28} {hit['line']:>6}  [MCFAO_ENTRYPOINT] stage={hit['stage']} {hit['cls']}")
    for row in proven:
        hit = row["clean"][0]
        out.append(f"{row['mod']:28} {hit['line']:>6}  {hit['text'][:120]}")
    if warned:
        out += ["", "only WARN/ERROR (not proof of healthy init):"]
        for row in warned:
            hit = row["hits"][0]
            out.append(f"{row['mod']:28} {hit['line']:>6}  {hit['text'][:120]}")
    if missing:
        out += ["", "silent (no entrypoint trace and no self-named init line): "
                + ", ".join(row["mod"] for row in missing)]
    return "\n".join(out)


def emit_evidence(results: dict, build: Path, path: Path) -> list[str]:
    """Add LOAD_PASS candidates without touching existing verdicts."""
    table = read_json(path) or {}
    added = []
    for mod_id, row in sorted(results.items()):
        if mod_id in table:
            continue
        if row["dispatched"]:
            hit = row["dispatched"]
            table[mod_id] = {
                "status": "LOAD_PASS",
                "note": f"{row['name']} 的 {hit['stage']} 入口点 {hit['cls']} 派发返回，未抛异常",
                "evidence": f"{build.name}-simulator/game.log#L{hit['line']}",
                "tests": "tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py",
            }
        elif row["clean"]:
            hit = row["clean"][0]
            table[mod_id] = {
                "status": "LOAD_PASS",
                "note": f"{row['name']} 在运行期打出初始化标记（token `{hit['token']}`），入口点未抛异常",
                "evidence": f"{build.name}-simulator/game.log#L{hit['line']}",
                "tests": "tools/scan_mod_evidence.py + tests/test_scan_mod_evidence.py",
            }
        else:
            continue
        added.append(mod_id)
    if added:
        ordered = {key: table[key] for key in table if key.startswith("_")}
        ordered.update({key: table[key] for key in sorted(table) if not key.startswith("_")})
        path.write_text(json.dumps(ordered, ensure_ascii=False, indent=2) + "\n")
    return added


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=Path, help="fabric-pack-NN 目录")
    parser.add_argument("--json", type=Path, help="把逐 Mod 命中写到这个文件")
    parser.add_argument("--emit-evidence", action="store_true",
                        help="把 INFO 级命中写进 docs/MOD_MATRIX_EVIDENCE.json 作为 LOAD_PASS")
    args = parser.parse_args()

    build = args.build if args.build.is_absolute() else ROOT / args.build
    log = build.with_name(build.name + "-simulator") / "game.log"
    if not log.is_file():
        raise SystemExit(f"no smoke log at {log}")
    report = stage_report(build, "fabric")
    if not report:
        raise SystemExit(f"no fabric stage report in {build}")

    mods = [row for row in report.get("mods", []) if isinstance(row, dict) and row.get("id")]
    results = scan(log, mods, entrypoints_by_mod(report))
    print(summarise(results))
    if args.json:
        args.json.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
        print(f"\nwrote {args.json}")
    if args.emit_evidence:
        added = emit_evidence(results, build, EVIDENCE)
        print(f"\nemitted {len(added)} LOAD_PASS candidates -> {EVIDENCE.relative_to(ROOT)}")
        for mod_id in added:
            print(f"  + {mod_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
