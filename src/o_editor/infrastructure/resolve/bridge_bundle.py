"""Build a self-contained restricted host from the existing editorial engine."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def build_bridge(root: Path, mailbox: Path) -> str:
    """Include audited pure sections; never ship Studio file/process helpers."""
    common = (root / "launcher/internal_common.lua").read_text(encoding="utf-8")

    def section(start: str, end: str) -> str:
        return common[common.index(start) : common.index(end)]

    core = "\n".join(
        (
            "local M = {}\nlocal JSON_NULL = {}",
            section("function M.timestamp()", "function M.app_data_dir()"),
            section("local function encode_string", "function M.read_json("),
            section("function M.safe_call", "function M.uuid()"),
            section("local function read_member", "function M.try_capture_context"),
            section("M.ROUGH_CUT_PLAN_MAX_AGE_SECONDS", "function M.run_take_zoom_action"),
        )
    )
    # Explicit, checked adaptations keep Studio source intact. A changed engine
    # must be audited again instead of silently losing the restricted guards.
    adaptations = (
        (  # capture_layout and collect_items both enumerate all track types.
            2,
            'local count = tonumber((M.call_method(timeline, "GetTrackCount", track_type))) or 0',
            'local count = tonumber((M.call_method(timeline, "GetTrackCount", track_type)))\n'
            "        if not count or count < 0 or count % 1 ~= 0 then\n"
            '            error("Contagem de faixas indisponível.") end',
        ),
        (
            1,
            'warnings[#warnings + 1] = "Não foi possível listar itens de " .. track_type\n'
            '                    .. " " .. tostring(index) .. ": " .. tostring(items_error)',
            'error("Não foi possível listar itens de " .. track_type .. " " .. tostring(index))',
        ),
        (
            1,
            'local fps = timeline:GetSetting("timelineFrameRate")',
            'local settings = M.call_method(timeline, "GetSettings")\n'
            '    local fps = type(settings) == "table" and settings.timelineFrameRate\n'
            '        or M.call_method(timeline, "GetSetting", "timelineFrameRate")',
        ),
    )
    for expected, original, restricted in adaptations:
        if core.count(original) != expected:
            raise ValueError("A engine mudou; revise a adaptação restrita antes de instalar.")
        core = core.replace(original, restricted, expected)
    forbidden = ("io.open", "os.execute", "os.rename", "require(", "dofile(", "package.")
    if any(item in core for item in forbidden):
        raise ValueError("A engine restrita contém uma operação proibida.")
    template = (root / "launcher/ede_bridge.lua").read_text(encoding="utf-8")
    path = mailbox.resolve().as_posix()
    if any(char in path for char in "\n\r\x00"):
        raise ValueError("Caminho inválido para o mailbox.")
    # JSON quoting is Lua-compatible for Windows paths normalized to forward slashes.
    return template.replace("-- @@CORE@@", core).replace(
        '"@@MAILBOX@@"', json.dumps(path, ensure_ascii=False)
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--mailbox", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    text = build_bridge(args.root, args.mailbox)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
