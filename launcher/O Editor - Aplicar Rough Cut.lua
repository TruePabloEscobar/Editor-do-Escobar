-- Applies an approved rough-cut plan by building a NEW timeline (copy of the original,
-- emptied and rebuilt by the verified engine in internal_common.lua). The original
-- timeline is verified before and after and is never edited.

local SCRIPT_VERSION = "2.4.0"
local BUILD_HASH = "microphone-clip-state-20261019"
local appdata = os.getenv("APPDATA")
local base = appdata and (appdata .. "\\O Editor") or "."
local log_path = base .. "\\logs\\internal-roughcut.log"

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
    local handle = io.open(base .. "\\reports\\roughcut-bootstrap-error.txt", "wb")
    if handle then
        handle:write(tostring(message))
        handle:close()
    end
    local safe = tostring(message):gsub('"', "'"):gsub("[\r\n]", " ")
    os.execute('cmd.exe /d /s /c ""' .. base
        .. '\\launch-editor.cmd" --show-message "' .. safe .. '""')
    print("O Editor: " .. tostring(message))
end

raw_log("Rough cut bootstrap started; version=" .. SCRIPT_VERSION .. "; build=" .. BUILD_HASH)
local loaded, common = xpcall(function()
    return dofile(base .. "\\internal_common.lua")
end, debug.traceback)
if not loaded then
    bootstrap_failure(common)
    return
end

local action_ok, action_error = xpcall(function()
    return common.run_internal_action("apply_rough_cut", function(runtime)
    local plan_path = base .. "\\plans\\rough-cut-pending.json"
    if not common.file_exists(plan_path) then
        return {
            status = "BLOCKED",
            message = "Nenhum plano de rough cut pendente. Gere e aprove a prévia no O Editor.",
            details = {plan_path = plan_path},
        }
    end
    local plan_ok, plan = pcall(common.read_json, plan_path)
    if not plan_ok or type(plan) ~= "table" then
        return {
            status = "FAILED",
            message = "O plano de rough cut não pôde ser lido. Nada foi alterado.",
            details = {plan_path = plan_path, error = tostring(plan)},
        }
    end
    runtime.correlation = {plan_id = plan.plan_id, mode = plan.mode}
    common.ensure_directory(base .. "\\plans\\applied")
    local applied_marker = base .. "\\plans\\applied\\" .. tostring(plan.plan_id) .. ".json"
    if common.file_exists(applied_marker) then
        return {
            status = "BLOCKED",
            message = "Este plano já foi aplicado. Gere uma nova prévia para aplicar novamente.",
            details = {plan_path = plan_path, applied_marker = applied_marker},
        }
    end
    local result = common.apply_rough_cut(runtime, plan, function(message)
        common.append_log(runtime.log_path, message)
    end)
    result.details.plan_path = plan_path
    if result.mutations_executed then
        local marker_ok, marker_error = pcall(common.write_json, applied_marker, {
            plan_id = plan.plan_id,
            status = result.status,
            created_timeline = result.details.created_timeline,
            applied_at = common.timestamp(),
        })
        if not marker_ok then
            result.details.warnings = result.details.warnings or {}
            result.details.warnings[#result.details.warnings + 1] =
                "O resultado editorial foi conferido, mas o recibo não pôde ser salvo: " .. tostring(marker_error)
        end
        local archived = os.rename(plan_path, base .. "\\plans\\rough-cut-" .. tostring(plan.plan_id) .. "-done.json")
        if not archived then
            result.details.warnings = result.details.warnings or {}
            result.details.warnings[#result.details.warnings + 1] = "Não foi possível arquivar o plano pendente."
        end
    end
    return result
end, {
    log_name = "internal-roughcut",
    script_path = common.script_path(2),
    script_version = SCRIPT_VERSION,
    build_hash = BUILD_HASH,
    })
end, debug.traceback)
if not action_ok then
    bootstrap_failure(action_error)
end
