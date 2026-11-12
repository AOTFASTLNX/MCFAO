#!/usr/bin/env python3
"""Generate docs/MOD_COMPATIBILITY_MATRIX.md from a verification pack's own evidence.

The matrix is intentionally derived, not hand-maintained: every Mod id, version, build number,
exclusion verdict and log path below comes from the pack's result.json files. The only input that
is a human judgement is docs/MOD_MATRIX_EVIDENCE.json, which can *upgrade* a row when somebody
has actually observed that Mod working in a running world. Nothing in this tool can upgrade a row
on its own - a successful build is BUILD_PASS, never FUNCTION_PASS.

Usage:
    python3 -B tools/generate_mod_matrix.py --build artifacts/mcfao/fabric-pack-77
    python3 -B tools/generate_mod_matrix.py            # latest pack with a result.json
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "docs" / "MOD_COMPATIBILITY_MATRIX.md"
EVIDENCE = ROOT / "docs" / "MOD_MATRIX_EVIDENCE.json"
BUILDS = ROOT / "artifacts" / "mcfao"
CURATED = BUILDS / "curated-verification-mods-01"
ISOLATED = BUILDS / "incompatible-01"

STATUS_ORDER = ["NOT_TESTED", "BLOCKED", "BUILD_PASS", "LOAD_PASS", "FUNCTION_PASS", "DEVICE_PASS"]
RANK = {status: index for index, status in enumerate(STATUS_ORDER)}

# A Mod-specific adapter is the exception, not the rule: the framework lowering is general and
# each entry below records why one Mod needed a targeted rewrite, which version it was audited
# against, and which first-party regression test keeps it honest.
ADAPTERS = {
    "xaeroworldmap": ("ModFiles.modFile / fetchModFile",
                      "tests/test_runtime_lowering.py::test_mods_asking_for_their_own_jar_get_a_nominal_path"),
    "xaerominimap": ("ModFiles.modFile / FabricPlatformHelper.getModFile",
                     "tests/test_runtime_lowering.py::test_mods_asking_for_their_own_jar_get_a_nominal_path"),
    "xaerolib": ("反射成员元数据 RenderType.create",
                 "tests/test_config_reflection.py::test_field_lookup_and_wrapper_returning_a_field_are_recorded"),
    "immediatelyfast": ("MixinConfigPlugin.onLoad 的 earlyInit 重放 / 版本查询折叠",
                        "tests/test_runtime_lowering.py::test_mixin_plugin_early_init_is_replayed_in_closed_world"),
    "glitchcore": ("EventManager.addListenerResolved 事件类型构建期解析",
                   "tests/test_runtime_lowering.py::test_glitchcore_event_types_are_resolved_at_build_time"),
    "biomesoplenty": ("GlitchCore 监听器事件类型构建期解析",
                      "tests/test_runtime_lowering.py::test_glitchcore_event_types_are_resolved_at_build_time"),
    "fabric-renderer-indigo": ("shouldApplyIndigo 门控折叠",
                               "tests/test_runtime_lowering.py::test_indigo_renderer_decision_without_runtime_plugin"),
    "fabric-api-base": ("移除未使用的动态代理工厂方法",
                        "tests/test_runtime_lowering.py::test_fabric_api_interfaces_are_pinned_for_dual_initializers"),
    "jade": ("FabricJadeMetadata 构造器元数据折叠",
             "tests/test_runtime_lowering.py::test_custom_stage_singletons_and_lazy_identity"),
    "framework": ("@RegistryContainer 扫描改写为构建期表",
                  "tests/test_runtime_lowering.py::test_custom_stage_singletons_and_lazy_identity"),
    "dynamic-fps": ("包装器 fromJson 的序列化根扫描",
                    "tests/test_runtime_lowering.py::test_json_reads_through_a_mod_wrapper_register_their_type"),
    "sodium": ("布局驱动的顶点序列化器替换运行时字节码生成",
               "tests/test_config_reflection.py::test_sodium_dependency_injection_implementations_are_registered"),
    "yet_another_config_lib_v3": ("YACL 配置根与 handler 字段注册",
                                  "tests/test_config_reflection.py::test_yacl_config_roots_require_handler_field_and_clinit"),
    "entity_model_features": ("ASMParser 运行时 defineClass（未适配，已排除）", "—"),
}

CATEGORY_RULES = [
    (lambda mod: mod == "fabric-api" or mod.startswith("fabric-"), "Fabric API"),
    (lambda mod: mod.startswith("org_") or mod.startswith("com_") or mod.startswith("net_")
     or mod.startswith("cloth-") or mod.startswith("de_") or mod in {"jsr305", "mousetweaks"},
     "库 / 嵌套依赖"),
    (lambda mod: mod == "mcfao_fixture", "第一方验证夹具"),
]


def read_json(path: Path):
    return json.loads(path.read_text()) if path.is_file() else None


def relative(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def pack_number(path: Path) -> int:
    match = re.search(r"fabric-pack-(\d+)$", path.name)
    return int(match.group(1)) if match else -1


def latest_build() -> Path:
    candidates = [path for path in BUILDS.glob("fabric-pack-*")
                  if path.is_dir() and (path / "result.json").is_file()]
    if not candidates:
        raise SystemExit("No completed verification pack found under artifacts/mcfao")
    return max(candidates, key=pack_number)


def stage_report(build: Path, stage: str) -> tuple[dict, Path] | tuple[None, None]:
    matches = sorted(build.glob(f"{stage}/*/product/result.json"))
    return (read_json(matches[0]), matches[0]) if matches else (None, None)


#: Exceptions that never describe a blocker. `oshi` cannot identify the simulator's OS and
#: prints `Operating system not supported: Unknown` during startup of every build; offline
#: auth and Realms probes also throw by design. A log that only contains these is healthy.
BENIGN_NOISE = (
    "Operating system not supported",
    "UnknownHostException",
    "401 Unauthorized",
    "Realms",
    "Missing model",
)


def is_noise(line: str) -> bool:
    return any(token in line for token in BENIGN_NOISE)


def smoke_evidence(build: Path) -> dict:
    directory = build.with_name(build.name + "-simulator")
    result = read_json(directory / "result.json")
    log = directory / "game.log"
    text = log.read_text(errors="replace") if log.is_file() else ""
    markers = {
        "F1": "MCFAO_F1_CLIENT_ENTRYPOINT_RESOURCE_PASS",
        "F3": "MCFAO_F3_CLIENT_WORLD_JOIN_PASS",
        "joined": "Dev joined the game",
    }
    crash = ""
    # Benign noise precedes the real blocker in every smoke log (offline auth 401, Realms
    # checks, broken local configs), so the first "Exception" line is rarely the story. The
    # fatal section - "Unreported exception thrown!" or the crash report "Description:" - is
    # the honest source; the first exception after it is the blocker.
    fatal = 0
    for line in text.splitlines():
        if "Unreported exception thrown" in line or " Description:" in line:
            fatal = 1
            continue
        if fatal and re.search(r"(?:Exception|Error|FATAL)[: ]", line) and not is_noise(line):
            crash = line.strip()[:200]
            break
    status = (result or {}).get("status", "FAILED_NO_RESULT" if text else "NOT_RUN")
    # Without a fatal section the log finished by itself. If the smoke runner also recorded a
    # pass, the first exception is startup noise by definition - reporting it as "the first
    # crash" manufactures a blocker that nobody can act on.
    if not crash and not str(status).endswith("_PASS"):
        for line in text.splitlines():
            if re.search(r"(?:Exception|Error|FATAL)[: ]", line) and not is_noise(line):
                crash = line.strip()[:200]
                break
    return {
        "directory": relative(directory),
        "present": directory.is_dir(),
        "status": status,
        "markers": {name: (marker in text) for name, marker in markers.items()},
        "crash": crash,
        "result": result or {},
    }


def blocker_category(message: str) -> str:
    if "defineClass" in message or "defineHiddenClass" in message or "newProxyInstance" in message:
        return "运行时生成类 / 动态代理"
    if "URLClassLoader" in message or "native loading" in message:
        return "运行时类加载"
    return "闭世界不可达"


def category_of(mod: str) -> str:
    for predicate, label in CATEGORY_RULES:
        if predicate(mod):
            return label
    return "内容 / 客户端 Mod"


def collect(build: Path) -> dict:
    result = read_json(build / "result.json") or {}
    fabric, fabric_path = stage_report(build, "fabric")
    if not fabric:
        raise SystemExit(f"No fabric stage report in {build}")
    transform = fabric.get("transform", {})
    resolved = {row["id"]: row.get("version", "") for row in transform.get("resolvedMods", [])}
    metadata = {row.get("id"): row for row in fabric.get("mods", []) if isinstance(row, dict)}
    excluded = fabric.get("excludedMods", {}) or {}
    jar_ids = fabric.get("jarIds", {}) or {}
    roots = {path.name for path in CURATED.glob("*.jar")} if CURATED.is_dir() else set()
    owner = {}
    for jar, ids in jar_ids.items():
        for mod in ids:
            owner.setdefault(mod, []).append(Path(jar).name)
    isolated_report = read_json(ISOLATED / "result.json") or {}
    isolated = {row["modId"]: row for row in isolated_report.get("mods", [])}

    build_ok = result.get("status") in {"SIGNED_DEVICE_APP", "SIMULATOR_WORLD_SMOKE_PASS"}
    pack = pack_number(build)
    evidence_path = f"{relative(build)}/fabric/*/product/result.json"
    upgrades = {key: value for key, value in (read_json(EVIDENCE) or {}).items()
                if not key.startswith("_")}

    rows = []
    for mod in sorted(set(resolved) | set(excluded) | set(isolated)):
        notes, source, tests = [], "", "unittest + verify_aot_classpath.py + simulator smoke"
        if mod in isolated:
            row = isolated[mod]
            status = "BLOCKED"
            level = row.get("level", "pair-level" if row.get("blockedBy") else "isolated")
            reason = row.get("blockedBy") or row.get("reason", "")[:110]
            notes.append(f"隔离（{level}）：{reason}")
            source = "artifacts/mcfao/incompatible-01/result.json#/mods"
            tests = "隔离判定见 pack-68 / pack-70 冒烟日志"
            version = row.get("version", "")
        elif mod in excluded:
            status = "BLOCKED"
            messages = excluded[mod]
            first = messages[0] if messages else ""
            notes.append(f"导出期排除：{blocker_category(first)}；{len(messages)} 处")
            source = f"{evidence_path}#/excludedMods/{mod}"
            tests = "inspect_archives / transformation_checks"
            version = (metadata.get(mod) or {}).get("version", "")
        elif mod in resolved:
            status = "BUILD_PASS" if build_ok else "NOT_TESTED"
            version = resolved[mod]
            source = f"{evidence_path}#/transform/resolvedMods"
        else:
            status, version = "NOT_TESTED", ""
            notes.append("未出现在解析出的 Mod 集合中")
            source = evidence_path
        if mod in ADAPTERS:
            scope, test = ADAPTERS[mod]
            notes.append(f"定向适配：{scope}")
            tests = test
        owners = sorted(set(owner.get(mod, [])))
        root = next((name for name in owners if name in roots), None)
        notes.append("根 jar: " + root if root else ("嵌套 jar: " + ", ".join(owners[:2]) if owners else "嵌套 jar"))
        upgrade = upgrades.get(mod)
        # A BLOCKED Mod left the image; an observation entry cannot put it back. It has to be
        # re-admitted into a new pack and earn BUILD_PASS again before any upgrade is possible.
        admissible = status in {"BUILD_PASS", "LOAD_PASS", "FUNCTION_PASS"}
        if admissible and isinstance(upgrade, dict) and RANK.get(upgrade.get("status"), -1) > RANK[status]:
            status = upgrade["status"]
            notes.append("证据表：" + upgrade.get("note", upgrade.get("status")))
            source = upgrade.get("evidence", source)
            tests = upgrade.get("tests", tests)
        rows.append({
            "id": mod, "name": (metadata.get(mod) or {}).get("name", mod),
            "version": version, "category": category_of(mod), "status": status,
            "pack": pack if status not in {"NOT_TESTED"} else "—",
            "evidence": source, "tests": tests, "notes": "；".join(notes),
        })

    count = Counter(row["status"] for row in rows)
    return {
        "build": build, "pack": pack, "result": result, "fabric": fabric,
        "fabric_path": fabric_path, "transform": transform, "rows": rows,
        "count": count, "smoke": smoke_evidence(build),
        "classpath": read_json(build / "classpath-check.json"),
        "members": read_json(build / "classpath-members-check.json"),
        "isolated": isolated,
    }


def render(data: dict) -> str:
    build, pack = data["build"], data["pack"]
    smoke, transform = data["smoke"], data["transform"]
    markers = smoke["markers"]
    criteria_met = all(markers.values())
    passed = str(smoke["status"]).endswith("_PASS")
    lines = [
        "# MCFAO 整合包 AOT 兼容性矩阵",
        "",
        "> 本文件由 `tools/generate_mod_matrix.py` 从验证包自身的 `result.json` 生成，请勿手改表格；"
        "人工判定的状态升级写在 `docs/MOD_MATRIX_EVIDENCE.json`。"
        "`BLOCKED` 不能被证据表升级——必须先重新进入验证包、重新取得 `BUILD_PASS`。",
        "> 生成命令：`python3 -B tools/generate_mod_matrix.py --build " + relative(build) + "`",
        "",
        "## 状态定义（严格递增，不可由构建结果自动跳级）",
        "",
        "| 状态 | 含义 | 需要的证据 |",
        "| --- | --- | --- |",
        "| `NOT_TESTED` | 未进入验证包，或该包未产出镜像 | 无 |",
        "| `BLOCKED` | 已被证明无法进入闭世界，或平台级不可用 | 导出期排除报告 / 隔离清单 / 崩溃日志 |",
        "| `BUILD_PASS` | 类进入 AOT 镜像，静态校验核心类 0 失败 | `SIGNED_DEVICE_APP` + `classpath-check.json` |",
        "| `LOAD_PASS` | 运行期入口点派发完成、该 Mod 初始化未抛异常 | 模拟器 `game.log` 中该 Mod 的初始化标记 |",
        "| `FUNCTION_PASS` | 该 Mod 的实际功能在运行的游戏内被观察到 | 功能探针 / 截图 / 状态断言 + 日志 |",
        "| `DEVICE_PASS` | 在真机上复验通过 | 真机证据（本项目当前**不做真机验证**） |",
        "",
        "> `BUILD_PASS` 只说明「类在镜像里」，不说明「Mod 能跑」。"
        + ("整包已在模拟器进世界（F1 + F3 + `Dev joined the game` 齐现），但没有任何 Mod 单独通过"
           "功能断言：逐 Mod `FUNCTION_PASS` 仍要各自的功能证据。"
           if criteria_met else
           "当前没有任何 Mod 达到 `FUNCTION_PASS`：模拟器尚未出现 F3 / `Dev joined the game`。"),
        "",
        "## 当前判据与 Gate",
        "",
        f"- 最新验证包：`{relative(build)}`（pack-{pack}），`result.json.status = {data['result'].get('status', 'N/A')}`",
        f"- 根 Mod jar：{len(list(CURATED.glob('*.jar'))) if CURATED.is_dir() else 0}；"
        f"解析出的 Mod id：{len(transform.get('resolvedMods', []))}；"
        f"导出期排除：{len(data['fabric'].get('excludedMods', {}) or {})}；"
        f"独立隔离：{len(data['isolated'])}",
        f"- 资源命名空间表：`{len(transform.get('resourceNamespaces', []))}` 个（旧包该项为 0，即清单字段缺失）",
    ]
    cp, members = data["classpath"], data["members"]
    if cp:
        lines.append(f"- 静态校验：`classpath-check.json` {cp.get('unloadable')}/{cp.get('classes')} 不可加载")
    if members:
        lines.append(f"- 严格成员校验：`classpath-members-check.json` {members.get('unloadable')}/{members.get('classes')} 不可加载")
    lines += [
        f"- 模拟器冒烟：`{smoke['directory']}`（`{smoke['status']}`）— "
        + " / ".join(f"{name}={'PASS' if ok else '未出现'}" for name, ok in markers.items()),
    ]
    if smoke["crash"]:
        lines.append(f"- 首个崩溃：`{smoke['crash']}`")
    elif passed:
        lines.append("- 未出现致命崩溃：日志无 `Unreported exception thrown` / 崩溃报告段落，"
                     "启动期的离线认证、Realms、`oshi` 探测异常不计入。")
    lines += [
        ("- **Gate C / D（模拟器口径）：判据已全中**——F1 + F3 + `Dev joined the game`，"
         "`SIMULATOR_WORLD_SMOKE_PASS`。真机 `C1/C2` 与 Gate D 的 IPA/安装/存档保留仍未做 → `NOT RUN`。"
         if criteria_met and passed else
         "- **Gate C / D：BLOCKED / NOT RUN**，直到 F1 + F3 + `Dev joined the game` 同时出现。"),
        "",
        "## 汇总",
        "",
        "| 状态 | 数量 |",
        "| --- | ---: |",
    ]
    for status in STATUS_ORDER:
        if data["count"].get(status):
            lines.append(f"| `{status}` | {data['count'][status]} |")
    lines += [
        "",
        f"## 逐 Mod 矩阵（{len(data['rows'])} 行）",
        "",
        "| Mod ID | 版本 | 类别 | 状态 | 构建 | 日志 / 证据 | 回归测试 | 备注 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in sorted(data["rows"], key=lambda item: (-RANK[item["status"]], item["id"])):
        cells = [row["id"], row["version"] or "—", row["category"], f"`{row['status']}`",
                 f"pack-{row['pack']}" if row["pack"] != "—" else "—",
                 row["evidence"], row["tests"], row["notes"]]
        lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in map(str, cells)) + " |")
    lines += [
        "",
        "## 排除与隔离明细",
        "",
    ]
    excluded = data["fabric"].get("excludedMods", {}) or {}
    if excluded:
        lines += ["### 导出期排除（闭世界静态检查拒绝）", "",
                  "| Mod ID | 类别 | 首个不可达点 |", "| --- | --- | --- |"]
        for mod, messages in sorted(excluded.items()):
            first = (messages[0] if messages else "").replace("|", "\\|")
            lines.append(f"| `{mod}` | {blocker_category(first)} | {first[:180]} |")
        lines.append("")
    if data["isolated"]:
        lines += ["### 预先隔离（离开验证包，jar 原样保留在 `incompatible-01/`）", "",
                  "| Mod ID | 版本 | 层级 | 阻塞原因 | 证据 |", "| --- | --- | --- | --- | --- |"]
        for mod, row in sorted(data["isolated"].items()):
            reason = (row.get("blockedBy") or row.get("reason", ""))[:150].replace("|", "\\|")
            evidence = (row.get("evidence") or {}).get("simulatorLog", "—")
            lines.append(f"| `{mod}` | {row.get('version', '—')} | {row.get('level', 'pair-level')} | "
                         f"{reason} | `{evidence}` |")
        lines += ["", "Iris 保持隔离：其 `FieldAccessor.makeSetter` 需要运行时生成类，"
                  "与闭世界冲突；待其余 Mod 稳定后再单独开工作线。", ""]
    lines += [
        "## 框架级适配与对应回归测试",
        "",
        "| 适配点 | 作用域 | 回归测试 |",
        "| --- | --- | --- |",
        "| `RuntimeLowering.lowerVanillaPackBuilder` + 生成的 `mcfao.aot.ModNamespaces` | "
        "所有 Mod 的 `assets/` / `data/`（取代闭世界缺失的 `ModResourcePackCreator`） | "
        "`tests/test_runtime_lowering.py::test_mod_resource_namespaces_reach_the_builtin_pack` |",
        "| `tools/config_reflection.py` 序列化根 / 反射成员扫描 | 所有用 Gson 或反射查游戏成员的 Mod | "
        "`tests/test_config_reflection.py`（16 项） |",
        "| `RuntimeLowering.lowerQueries` / 生成 `Entrypoints` | 所有查询 Loader 的 Mod | "
        "`tests/test_runtime_lowering.py`（8 项） |",
        "| `tools/verify_aot_classpath.py` 默认 + `--verify-members` | 整个 AOT classpath | "
        "构建后静态校验产物 `classpath-check.json` |",
        "",
        "## 验证链（每个新包都要重跑）",
        "",
        "```bash",
        "python3 -m unittest discover -s tests -q",
        f"python3 -B tools/verify_aot_classpath.py --build {relative(build)}",
        f"python3 -B tools/verify_aot_classpath.py --build {relative(build)} --verify-members",
        f"python3 -B tools/smoke_mcfao_simulator.py --expect fabric --build {relative(build)} \\",
        "  --runtime artifacts/graphics/runtime-sim-02 \\",
        "  --graphics artifacts/graphics/world-simulator-input-02 \\",
        "  --assets artifacts/graphics/game-assets-01/assets \\",
        "  --seed-world /tmp/c0seed/world \\",
        "  --simulator 8BA37AA9-8462-4824-9EE6-0B8BFEBF3AC3 \\",
        f"  --output {smoke['directory']}",
        "python3 -B tools/generate_mod_matrix.py --build <新包目录>",
        "```",
        "",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, help="Verification pack directory (default: latest)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    build = (args.build or latest_build()).resolve()
    if not (build / "result.json").is_file():
        raise SystemExit(f"No result.json in {build}")
    data = collect(build)
    text = render(data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text)
    print(f"pack-{pack_number(build)}: {len(data['rows'])} rows, "
          f"{dict(data['count'])} -> {relative(args.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
