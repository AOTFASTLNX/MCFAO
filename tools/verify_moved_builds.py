#!/usr/bin/env python3
"""校验 artifacts/mcfao 旧构建目录是否已完整复制到外接盘，并可选删除本地原件。

用法:
    python3 tools/verify_moved_builds.py --manifest /tmp/move_manifest.json \
        --src artifacts/mcfao --dst "/Volumes/K/Xcode-备份/buildAOT" [--delete]

校验口径: 逐目录比较 (文件数, 总字节) 与抽样 sha256。
只有全部分项一致的目录才会被删除。
"""
import argparse
import hashlib
import json
import os
import shutil
import sys


def walk_stats(root):
    """返回 (文件数, 总字节, {相对路径: 大小})，符号链接按目标计。

    忽略 macOS 在 exFAT 上生成的 AppleDouble 伴生文件（``._name``）：
    它们只是扩展属性的容器，不属于构建内容，且体积可观。
    """
    count = 0
    total = 0
    files = {}
    for dirpath, _, filenames in os.walk(root, followlinks=False):
        for name in filenames:
            if name.startswith("._"):
                continue
            path = os.path.join(dirpath, name)
            try:
                if os.path.islink(path):
                    if not os.path.exists(path):
                        continue  # 断链，复制时已跳过
                    st = os.stat(path)
                else:
                    st = os.lstat(path)
            except OSError:
                continue
            if not os.path.isfile(path):
                continue
            count += 1
            total += st.st_size
            files[os.path.relpath(path, root)] = st.st_size
    return count, total, files


def sha256(path, chunk=8 << 20):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--src", required=True)
    parser.add_argument("--dst", required=True)
    parser.add_argument("--delete", action="store_true")
    parser.add_argument("--sample", type=int, default=3,
                        help="每个目录抽查多少个文件做 sha256")
    args = parser.parse_args(argv)

    manifest = json.load(open(args.manifest, encoding="utf-8"))
    ok, bad, missing = [], [], []

    for name, expected in sorted(manifest.items()):
        src = os.path.join(args.src, name)
        dst = os.path.join(args.dst, name)
        if not os.path.isdir(dst):
            missing.append(name)
            continue
        dcount, dbytes, dfiles = walk_stats(dst)
        reasons = []
        if dcount != expected["files"]:
            reasons.append(f"文件数 {dcount}!={expected['files']}")
        if dbytes != expected["bytes"]:
            reasons.append(f"字节 {dbytes}!={expected['bytes']}")
        # 抽样哈希：取最大的几个文件
        if not reasons and args.sample:
            picks = sorted(dfiles.items(), key=lambda kv: -kv[1])[:args.sample]
            for rel, _size in picks:
                sp = os.path.join(src, rel)
                dp = os.path.join(dst, rel)
                try:
                    if sha256(sp) != sha256(dp):
                        reasons.append(f"哈希不符 {rel}")
                        break
                except OSError as exc:
                    reasons.append(f"读取失败 {rel}: {exc}")
                    break
        if reasons:
            bad.append((name, "; ".join(reasons)))
        else:
            ok.append(name)

    print(f"一致 {len(ok)} / 不符 {len(bad)} / 缺失 {len(missing)}")
    for name, why in bad:
        print(f"  MISMATCH {name}: {why}")
    for name in missing:
        print(f"  MISSING  {name}")

    if args.delete and ok:
        freed = 0
        for name in ok:
            src = os.path.join(args.src, name)
            try:
                freed += sum(
                    os.path.getsize(os.path.join(dp, f))
                    for dp, _, fns in os.walk(src)
                    for f in fns
                    if os.path.isfile(os.path.join(dp, f))
                )
            except OSError:
                pass
            shutil.rmtree(src)
        print(f"已删除 {len(ok)} 个本地目录，约 {freed / 2**30:.1f} GiB")
    elif ok:
        print("(未加 --delete，只校验不删除)")
    return 0 if not (bad or missing) else 1


if __name__ == "__main__":
    sys.exit(main())
