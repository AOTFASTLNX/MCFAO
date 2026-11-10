#!/usr/bin/env python3
"""Static bytecode shape census for classes inside a jar (read-only, nothing is executed).

Purpose: the Graal points-to analysis materialises a type-flow graph per reachable method.
`MethodTypeFlowBuilder.createTypeFlow` walks that graph with `PostOrderNodeIterator`, and the
iterator keeps one **full copy** of the node->flow map for every control split / invoke-with-
exception it visits (`nodeStates.put(x, state)` after `state.clone()`). Retained build-host memory
for one method therefore grows with

    (number of state snapshots) x (map entries per snapshot)

which is quadratic in the method's size. A single huge static initialiser such as
`net.minecraft.world.level.block.Blocks.<clinit>` (40199 bytes of bytecode, 7213 invokes) can
therefore exhaust a multi-gigabyte heap on its own.

This tool measures the *bytecode shape* that drives those two factors. It is a static census of
the input jar, not a measurement of the analysis, not a memory measurement, and not Gate evidence.

Metrics per method:
  instructions        decoded JVM instructions
  invokes             invoke* instructions (each may become InvokeWithExceptionNode)
  conditionalBranches if* instructions (control splits)
  switches            tableswitch/lookupswitch instructions
  switchEntries       total switch cases (extra control-split successors)
  exceptionHandlers   Code attribute exception table entries (extra handler roots)
  snapshotSites       invokes + conditionalBranches + switches  (upper bound on state clones)
  snapshotSitesLower  conditionalBranches + switches            (lower bound: splits only)
  shapeCostProxy      snapshotSites * instructions / 2  (map entries, order-of-magnitude proxy)
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
import zipfile
from pathlib import Path

# opcode -> operand byte count for the fixed-width instruction set.
_FIXED = {}
for _op in range(0x00, 0x10):
    _FIXED[_op] = 0
_FIXED.update({0x10: 1, 0x11: 2, 0x12: 1, 0x13: 2, 0x14: 2})
for _op in range(0x15, 0x1A):
    _FIXED[_op] = 1
for _op in range(0x1A, 0x36):
    _FIXED[_op] = 0
for _op in range(0x36, 0x3B):
    _FIXED[_op] = 1
for _op in range(0x3B, 0x84):
    _FIXED[_op] = 0
_FIXED[0x84] = 2  # iinc
for _op in range(0x85, 0x99):
    _FIXED[_op] = 0
for _op in range(0x99, 0xA9):  # if*, goto, jsr
    _FIXED[_op] = 2
_FIXED[0xA9] = 1  # ret
for _op in range(0xAC, 0xB2):  # *return, athrow handled below
    _FIXED[_op] = 0
for _op in range(0xB2, 0xB9):  # get/put/invokevirtual/special/static
    _FIXED[_op] = 2
_FIXED.update({0xB9: 4, 0xBA: 4, 0xBB: 2, 0xBC: 1, 0xBD: 2, 0xBE: 0, 0xBF: 0,
               0xC0: 2, 0xC1: 2, 0xC2: 0, 0xC3: 0, 0xC5: 3, 0xC6: 2, 0xC7: 2,
               0xC8: 4, 0xC9: 4, 0xCA: 0})

CONDITIONAL = set(range(0x99, 0xA7)) | {0xC6, 0xC7}
INVOKES = {0xB6, 0xB7, 0xB8, 0xB9, 0xBA}


def _switch(code: bytes, offset: int) -> tuple[int, int]:
    """Return (instruction length, case count) for tableswitch/lookupswitch at offset."""
    pad = (4 - (offset + 1) % 4) % 4
    base = offset + 1 + pad
    if base + 8 > len(code):
        raise ValueError("truncated switch at offset %d" % offset)
    if code[offset] == 0xAA:
        if base + 12 > len(code):
            raise ValueError("truncated tableswitch at offset %d" % offset)
        low, high = struct.unpack_from(">ii", code, base + 4)
        count = max(0, high - low + 1)
        return 1 + pad + 12 + count * 4, count
    count = struct.unpack_from(">i", code, base + 4)[0]
    if count < 0:
        raise ValueError("negative lookupswitch pair count at offset %d" % offset)
    return 1 + pad + 8 + count * 8, count


def scan_code(code: bytes, exception_handlers: int = 0) -> dict:
    """Decode one Code attribute's instruction stream and count shape metrics."""
    offset = 0
    instructions = invokes = indy = cond = switches = entries = returns = 0
    length = len(code)
    while offset < length:
        opcode = code[offset]
        if opcode in (0xAA, 0xAB):
            size, count = _switch(code, offset)
            entries += count
            switches += 1
        elif opcode == 0xC4:  # wide
            if offset + 1 >= length:
                raise ValueError("truncated wide at offset %d" % offset)
            size = 6 if code[offset + 1] == 0x84 else 4
        elif opcode in _FIXED:
            size = 1 + _FIXED[opcode]
        else:
            raise ValueError("unsupported opcode 0x%02x at offset %d" % (opcode, offset))
        if offset + size > length:
            raise ValueError("instruction at offset %d overruns code length %d" % (offset, length))
        if opcode in INVOKES:
            invokes += 1
            if opcode == 0xBA:
                indy += 1
        if opcode in CONDITIONAL:
            cond += 1
        if 0xAC <= opcode <= 0xB1:
            returns += 1
        instructions += 1
        offset += size
    if exception_handlers < 0:
        raise ValueError("negative exception handler count")
    upper = invokes + cond + switches
    lower = cond + switches
    return {"instructions": instructions, "codeLength": length, "invokes": invokes,
            "invokedynamic": indy, "conditionalBranches": cond, "switches": switches,
            "switchEntries": entries, "returns": returns,
            "exceptionHandlers": exception_handlers,
            "snapshotSites": upper, "snapshotSitesLower": lower,
            "shapeCostProxy": upper * instructions // 2}


class _Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.i = 0

    def u1(self) -> int:
        value = self.data[self.i]
        self.i += 1
        return value

    def u2(self) -> int:
        value = struct.unpack_from(">H", self.data, self.i)[0]
        self.i += 2
        return value

    def u4(self) -> int:
        value = struct.unpack_from(">I", self.data, self.i)[0]
        self.i += 4
        return value

    def skip(self, count: int) -> None:
        self.i += count

    def bytes_(self, count: int) -> bytes:
        value = self.data[self.i:self.i + count]
        self.i += count
        return value


def _constant_pool(reader: _Reader) -> list:
    count = reader.u2()
    pool: list = [None] * count
    index = 1
    while index < count:
        tag = reader.u1()
        if tag == 1:
            length = reader.u2()
            pool[index] = reader.bytes_(length).decode("utf-8", "replace")
        elif tag in (3, 4):
            reader.skip(4)
        elif tag in (5, 6):
            reader.skip(8)
            index += 1
        elif tag in (7, 8, 16, 19, 20):
            reader.skip(2)
        elif tag in (9, 10, 11, 12, 17, 18):
            reader.skip(4)
        elif tag == 15:
            reader.skip(3)
        else:
            raise ValueError("unknown constant pool tag %d at index %d" % (tag, index))
        index += 1
    return pool


def _attributes(reader: _Reader) -> list:
    """Read attributes as (name_index, payload_start, length)."""
    out = []
    for _ in range(reader.u2()):
        name = reader.u2()
        length = reader.u4()
        out.append((name, reader.i, length))
        reader.skip(length)
    return out


def methods_of(data: bytes) -> list:
    """Return [{name, descriptor, ...shape}] for every method declared in one class file."""
    reader = _Reader(data)
    if reader.u4() != 0xCAFEBABE:
        raise ValueError("not a class file")
    reader.skip(4)
    pool = _constant_pool(reader)
    reader.skip(6)  # access flags, this_class, super_class
    reader.skip(2 * reader.u2())  # interfaces
    for _ in range(reader.u2()):  # fields
        reader.skip(6)
        _attributes(reader)
    out = []
    for _ in range(reader.u2()):
        reader.u2()
        name = pool[reader.u2()]
        descriptor = pool[reader.u2()]
        shape = None
        handlers = 0
        code_length = 0
        for attr_name, start, length in _attributes(reader):
            if pool[attr_name] != "Code":
                continue
            body = _Reader(data)
            body.i = start
            body.u2()  # max_stack
            body.u2()  # max_locals
            code_length = body.u4()
            code = body.bytes_(code_length)
            handlers = body.u2()
            shape = scan_code(code, handlers)
        if shape is not None:
            out.append({"name": name, "descriptor": descriptor, "codeLength": code_length, **shape})
    return out


def census(jar: Path, include_inner: bool = False, top: int = 25) -> dict:
    rows = []
    classes = 0
    skipped = 0
    with zipfile.ZipFile(jar) as archive:
        for info in archive.infolist():
            if not info.filename.endswith(".class"):
                continue
            if not include_inner and "$" in info.filename:
                continue
            try:
                shape = methods_of(archive.read(info))
            except ValueError:
                skipped += 1
                continue
            classes += 1
            for entry in shape:
                rows.append({"class": info.filename[:-6].replace("/", "."), **entry})
    rows.sort(key=lambda row: -row["shapeCostProxy"])
    total = sum(row["instructions"] for row in rows)
    return {"jar": str(jar), "classesScanned": classes, "classesSkipped": skipped,
            "methodsScanned": len(rows), "instructionsTotal": total,
            "methodsOver8kBytecode": sum(1 for row in rows if row["codeLength"] > 8192),
            "methodsOver32kBytecode": sum(1 for row in rows if row["codeLength"] > 32768),
            "top": rows[:top],
            "scope": "static bytecode census of the input jar; shapeCostProxy is an order-of-magnitude "
                     "proxy for retained type-flow snapshots during points-to analysis, not a memory "
                     "measurement, not analysis output and not Gate evidence"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--jar", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="write JSON here instead of stdout")
    parser.add_argument("--top", type=int, default=25)
    parser.add_argument("--include-inner", action="store_true", help="also scan $Inner classes")
    args = parser.parse_args(argv)
    if not args.jar.is_file():
        parser.error("--jar must be an existing class/jar file")
    if args.top < 1:
        parser.error("--top must be positive")
    result = census(args.jar, args.include_inner, args.top)
    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
        print(json.dumps({key: result[key] for key in
                          ("classesScanned", "methodsScanned", "methodsOver8kBytecode",
                           "methodsOver32kBytecode")}, indent=2))
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
