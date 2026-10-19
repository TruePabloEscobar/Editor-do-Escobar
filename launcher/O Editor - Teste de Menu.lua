-- Visible O Editor internal menu execution test. No Resolve mutations.

local SCRIPT_VERSION = "2.4.0"
local BUILD_HASH = "microphone-clip-state-20261019"
local appdata = os.getenv("APPDATA")
local base = appdata and (appdata .. "\\O Editor") or "."
local log_path = base .. "\\logs\\menu-test.log"

local function raw_log(message)
    os.execute('cmd.exe /d /c if not exist "' .. base .. '\\logs" mkdir "'
        .. base .. '\\logs"')
    local handle = io.open(log_path, "ab")
    if handle then
        handle:write(os.date("!%Y-%m-%dT%H:%M:%SZ") .. " " .. tostring(message) .. "\n")
        handle:close()
    end
end

local function bootstrap_failure(message)
    raw_log("BOOTSTRAP FAILED: " .. tostring(message))
    os.execute('cmd.exe /d /c if not exist "' .. base .. '\\reports" mkdir "'
        .. base .. '\\reports"')
    local handle = io.open(base .. "\\reports\\menu-test-bootstrap-error.txt", "wb")
    if handle then
        handle:write(tostring(message))
        handle:close()
    end
    local safe = tostring(message):gsub('"', "'"):gsub("[\r\n]", " ")
    os.execute('cmd.exe /d /s /c ""' .. base
        .. '\\launch-editor.cmd" --show-message "' .. safe .. '""')
    print("O Editor: " .. tostring(message))
end

raw_log("Menu test bootstrap started; version=" .. SCRIPT_VERSION
    .. "; build=" .. BUILD_HASH)
local loaded, common = xpcall(function()
    return dofile(base .. "\\internal_common.lua")
end, debug.traceback)
if not loaded then
    bootstrap_failure(common)
    return
end

local action_ok, action_error = xpcall(function()
    return common.run_internal_action("menu_test", function(runtime)
    local confirmation_path = base .. "\\menu-test-success.txt"
    local context = runtime.context or {}
    local content = table.concat({
        "timestamp=" .. common.timestamp(),
        "script_path=" .. common.script_path(2),
        "script_version=" .. SCRIPT_VERSION,
        "build_hash=" .. BUILD_HASH,
        "project=" .. tostring(context.project_name or ""),
        "timeline=" .. tostring(context.timeline_name or ""),
        "success=true",
    }, "\n") .. "\n"
    common.write_text(confirmation_path, content)
    return {
        status = "SUCCESS",
        message = "Teste de menu concluído.",
        details = {
            confirmation_file = confirmation_path,
            resolve_context_available = runtime.context ~= nil,
        },
        markdown_lines = {
            "O DaVinci Resolve executou corretamente o script interno.",
            "",
            "- Arquivo de confirmação: `" .. confirmation_path .. "`",
        },
    }
end, {
    log_name = "menu-test",
    script_path = common.script_path(2),
    script_version = SCRIPT_VERSION,
    build_hash = BUILD_HASH,
    })
end, debug.traceback)
if not action_ok then
    bootstrap_failure(action_error)
end