"""CUDA discovery in a disposable child, outside Qt and Resolve."""

from __future__ import annotations

import json
import os
import subprocess


def discover_devices() -> list[dict[str, int | str]]:
    import ctranslate2

    count = ctranslate2.get_cuda_device_count()
    names: list[str] = []
    if not os.environ.get("CUDA_VISIBLE_DEVICES") and not os.environ.get("CUDA_DEVICE_ORDER"):
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=3,
                check=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            names = result.stdout.strip().splitlines()
        except (OSError, subprocess.SubprocessError):
            pass
    # Multiple physical adapters can have a different CUDA order: use logical ordinals.
    return [
        {"index": index, "name": names[0] if count == 1 and len(names) == 1 else "CUDA"}
        for index in range(count)
    ]


if __name__ == "__main__":
    try:
        print(json.dumps({"devices": discover_devices()}))
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"devices": [], "error": str(exc)}))
