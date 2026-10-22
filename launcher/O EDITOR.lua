-- Open O Editor from the internal DaVinci Resolve host.

local SCRIPT_VERSION = "2.5.0"
local BUILD_HASH = "take-zoom-20261022"
local appdata = os.getenv("APPDATA")
local base = appdata and (appdata .. "\\O Editor") or "."
local log_path = base .. "\\logs\\internal-open.log"

local function raw_log(message)
    -- Only spawn cmd.exe when the log folder is really missing (BUG-0029).
    local handle = io.open(log_path, "ab")
    if not handle then
        os.execute('cmd.exe /d /c if not exist "' .. base .. '\\logs" mkdir "'
            .. base .. '\\logs"')
        handle = io.open(log_path, "ab")
    end
    if handle then
        handle:write(os.date("!%Y-%m-%dT%H:%M:%SZ") .. " " .. tostring(message) .. "\n")
        handle:close()
    end
end

local function bootstrap_failure(message)
    raw_log("BOOTSTRAP FAILED: " .. tostring(message))
    local error_path = base .. "\\reports\\open-bootstrap-error.txt"
    os.execute('cmd.exe /d /c if not exist "' .. base .. '\\reports" mkdir "'
        .. base .. '\\reports"')
    local handle = io.open(error_path, "wb")
    if handle then
        handle:write(tostring(message))
        handle:close()
    end
    local launcher = base .. "\\launch-editor.cmd"
    local safe = tostring(message):gsub('"', "'"):gsub("[\r\n]", " ")
    os.execute('cmd.exe /d /s /c ""' .. launcher .. '" --show-message "'
        .. safe .. '""')
    print("O Editor: " .. tostring(message))
end

raw_log("Internal open bootstrap started; version=" .. SCRIPT_VERSION
    .. "; build=" .. BUILD_HASH)
local loaded, common = xpcall(function()
    return dofile(base .. "\\internal_common.lua")
end, debug.traceback)
if not loaded then
    bootstrap_failure(common)
    return
end

-- A normal launch never acts on a leftover plan. Only a fresh, one-use UI request
-- can dispatch an auxiliary action through this single menu entry.
local dispatch_ok, dispatched = xpcall(function()
    return common.dispatch_menu_action(base)
end, debug.traceback)
if not dispatch_ok then
    bootstrap_failure(dispatched)
    return
end
if dispatched then return end

local action_ok, action_error = xpcall(function()
    return common.run_internal_action("open", function(runtime)
    if not runtime.context then
        error(runtime.context_error or "O contexto interno do Resolve não está disponível.")
    end
    return {
        status = "SUCCESS",
        message = "O Editor aberto pelo DaVinci Resolve.",
        details = {
            resolve_source = runtime.context.resolve_source,
        },
        markdown_lines = {
            "A interface foi aberta ou recebeu foco por meio do host interno.",
            "Clipes capturados para transcrição: "
                .. tostring(type(runtime.context.layout) == "table"
                    and type(runtime.context.layout.clips) == "table"
                    and #runtime.context.layout.clips or 0),
        },
    }
end, {
    log_name = "internal-open",
    capture_layout = true,
    script_path = common.script_path(2),
    script_version = SCRIPT_VERSION,
    build_hash = BUILD_HASH,
    })
end, debug.traceback)
if not action_ok then
    bootstrap_failure(action_error)
end