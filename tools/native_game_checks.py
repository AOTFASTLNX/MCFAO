"""Reject successful AOT images whose startup path pruned the game itself."""
from __future__ import annotations

import mmap
from pathlib import Path
import subprocess


GAME_SYMBOLS = (
    "_Minecraft_runTick_",
    "_ClientPacketListener_handlePlayerInfoUpdate_",
    "_PlayDiagnostics_dumpThreads_",
)
DIAGNOSTIC_MARKERS = ("tickStallSeconds", "client_tick_stall", "handlerActive")


def verify_game_image(path: Path) -> dict:
    symbols = subprocess.run(["xcrun", "nm", "-a", str(path)], check=True,
                             capture_output=True, text=True, timeout=60).stdout
    missing = [name for name in GAME_SYMBOLS if name not in symbols]
    with path.open("rb") as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
        missing += [text for text in DIAGNOSTIC_MARKERS
                    if data.find(text.encode()) < 0 and data.find(text.encode("utf-16-le")) < 0]
    if missing:
        raise ValueError(f"AOT game code or current diagnostics absent from {path}: {missing}")
    return {"status": "GAME_CODE_PRESENT", "symbols": list(GAME_SYMBOLS),
            "markers": list(DIAGNOSTIC_MARKERS), "deviceRun": "NOT RUN"}
