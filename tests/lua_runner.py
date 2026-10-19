"""Run the actual Lua fixtures with Lua 5.1, including on Windows."""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path


def lua_command() -> list[str] | None:
    """Return an isolated interpreter command; never use Resolve's process."""
    executable = shutil.which("lua5.1") or shutil.which("luajit")
    if executable:
        return [executable]
    if importlib.util.find_spec("lupa") is not None:
        return [sys.executable, str(Path(__file__).resolve())]
    return None


def main() -> None:
    """Execute a fixture with its usual command-line arguments."""
    from lupa.lua51 import LuaRuntime

    runtime = LuaRuntime(unpack_returned_tuples=True)
    arguments = runtime.table_from(dict(enumerate(sys.argv[1:])))
    runtime.globals().arg = arguments
    runtime.eval("dofile")(sys.argv[1])


if __name__ == "__main__":
    main()
