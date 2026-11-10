#!/usr/bin/env python3
"""Package the current tracked source and documentation for reproduction reference."""
import argparse
import hashlib
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOTE = '''# FabricAOT 复现参考包

本包包含打包时 Git 已跟踪的项目文件（包括工作区修改）及本打包脚本。项目仍处于研发阶段：正式真机 C0 为 BLOCKED，C1/C2 未完成；模拟器结果不能代替真机验收。请先阅读 README.md、AGENTS.md、docs/WORK_HANDOFF.md、docs/BUILDING.md 和 docs/GRAPHICS_BOOTSTRAP.md。

本包不含 .git、artifacts、.cache、本地运行日志、构建目录、签名材料、Minecraft 客户端、游戏资源或存档。文档中指向这些目录的历史证据链接因而可能失效；本包并非完整原始证据归档，也不能开箱即运行。复现者需要自行合法获取客户端和资源，按锁定文件准备依赖与工具链，并自行配置 Apple 签名。路径、设备标识和签名配置可能是原作者本机示例，需自行调整。请遵守各依赖的许可证；本包不授予游戏或第三方组件的分发权。

推荐先运行 `python3 -B -m unittest discover -s tests -v`，并按文档逐项检查所需环境；部分测试和实验依赖额外本地工具或资源。不可在个人主环境直接执行未经审计的第三方 Mod 或构建脚本。
'''

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit('Output already exists: ' + str(output))
    files = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    files = sorted(set(filter(None, files)) | {'tools/package_share.py'})
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        def put(name, data, mode=0o644):
            entry = zipfile.ZipInfo('FabricAOT-reference/' + name, (2020, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = (0o100000 | mode) << 16
            archive.writestr(entry, data)
        put('分享包说明.md', NOTE.encode())
        for name in files:
            path = ROOT / name
            if path.is_symlink() or not path.is_file():
                raise SystemExit('Missing or non-regular tracked file: ' + name)
            put(name, path.read_bytes(), 0o755 if path.stat().st_mode & 0o111 else 0o644)
    print(f'{output}\nfiles={len(files)+1}\nsha256={hashlib.sha256(output.read_bytes()).hexdigest()}')

if __name__ == '__main__':
    main()
