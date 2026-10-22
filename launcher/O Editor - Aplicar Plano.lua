-- Visible, read-only application preflight. It never mutates a timeline.

local SCRIPT_VERSION = "2.5.0"
local BUILD_HASH = "take-zoom-20261022"
local appdata = os.getenv("APPDATA")
local base = appdata and (appdata .. "\\O Editor") or "."
local log_path = base .. "\\logs\\internal-apply.log"

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
    os.execute('cmd.exe /d /c if not exist "' .. base .. '\\reports" mkdir "'
        .. base .. '\\reports"')
    local handle = io.open(base .. "\\reports\\apply-bootstrap-error.txt", "wb")
    if handle then
        handle:write(tostring(message))
        handle:close()
    end
    local safe = tostring(message):gsub('"', "'"):gsub("[\r\n]", " ")
    os.execute('cmd.exe /d /s /c ""' .. base
        .. '\\launch-editor.cmd" --show-message "' .. safe .. '""')
    print("O Editor: " .. tostring(message))
end

raw_log("Apply preflight bootstrap started; no mutations; version=" .. SCRIPT_VERSION
    .. "; build=" .. BUILD_HASH)
local loaded, common = xpcall(function()
    return dofile(base .. "\\internal_common.lua")
end, debug.traceback)
if not loaded then
    bootstrap_failure(common)
    return
end

local action_ok, action_error = xpcall(function()
    return common.run_internal_action("apply_plan", function(runtime)
    local plan_path = base .. "\\plans\\latest-approved-plan.json"
    local details = {
        preflight_status = "NO_PLAN",
        plan_path = plan_path,
        mutations_executed = false,
        missing_capabilities = {},
        checks = {},
    }
    local function checked(name, status, detail)
        details.checks[#details.checks + 1] = {
            name = name,
            status = status,
            detail = detail,
        }
    end
    if not common.file_exists(plan_path) then
        checked("plan", "FAILED", "Nenhum plano aprovado foi encontrado.")
        return {
            status = "BLOCKED",
            message = "Aplicação bloqueada. Nenhum plano aprovado foi encontrado.",
            details = details,
            markdown_lines = {
                "Analise a timeline, aprove sugestões e exporte o plano primeiro.",
                "",
                "A timeline original não foi alterada.",
            },
        }
    end

    local plan_ok, plan = pcall(common.read_json, plan_path)
    if not plan_ok or type(plan) ~= "table" or plan.schema_version ~= 1 then
        details.preflight_status = "INVALID_PLAN"
        checked("schema", "FAILED", tostring(plan))
        return {
            status = "FAILED",
            message = "Aplicação bloqueada. O plano aprovado é inválido.",
            details = details,
        }
    end
    checked("schema", "PASSED", "schema_version=1")
    details.zoom_count = type(plan.zooms) == "table" and #plan.zooms or 0
    details.text_count = type(plan.texts) == "table" and #plan.texts or 0

    if not runtime.context then
        details.preflight_status = "BLOCKED"
        checked("resolve_context", "FAILED", runtime.context_error)
        return {
            status = "BLOCKED",
            message = "Aplicação bloqueada. O contexto interno não está disponível.",
            details = details,
        }
    end
    local mismatches = {}
    if plan.project ~= runtime.context.project_name then
        mismatches[#mismatches + 1] = "projeto"
    end
    if plan.timeline ~= runtime.context.timeline_name then
        mismatches[#mismatches + 1] = "timeline"
    end
    if tonumber(plan.fps) ~= tonumber(runtime.context.fps) then
        mismatches[#mismatches + 1] = "frame rate"
    end
    if #mismatches > 0 then
        details.preflight_status = "INVALID_PLAN"
        checked("context_match", "FAILED", table.concat(mismatches, ", "))
        return {
            status = "FAILED",
            message = "Aplicação bloqueada. Projeto, timeline ou frame rate divergem do plano.",
            details = details,
        }
    end
    checked("context_match", "PASSED", "projeto, timeline e fps correspondem")
    if type(plan.timeline_fingerprint) ~= "string" or plan.timeline_fingerprint == "" then
        details.preflight_status = "INVALID_PLAN"
        checked("fingerprint", "FAILED", "Fingerprint ausente.")
        return {
            status = "FAILED",
            message = "Aplicação bloqueada. O plano não contém fingerprint válido.",
            details = details,
        }
    end
    checked("fingerprint", "UNVERIFIED",
        "O host mínimo não recalcula o fingerprint completo; aplicação permanece bloqueada.")

    local supported = {}
    local capability_path = base .. "\\internal-capabilities.json"
    if common.file_exists(capability_path) then
        local capability_ok, capabilities = pcall(common.read_json, capability_path)
        if capability_ok
                and type(capabilities) == "table"
                and capabilities.schema_version == 1
                and capabilities.mode == "READ_ONLY"
                and capabilities.mutations_executed == false
                and capabilities.script_version == SCRIPT_VERSION
                and capabilities.build_hash == BUILD_HASH
                and capabilities.common_version == common.COMMON_VERSION
                and capabilities.common_hash == common.COMMON_HASH
                and capabilities.project == runtime.context.project_name
                and capabilities.timeline == runtime.context.timeline_name
                and capabilities.resolve_version == runtime.context.resolve_version
                and type(capabilities.results) == "table" then
            for _, item in ipairs(capabilities.results or {}) do
                if item.status == "SUPPORTED" then
                    supported[item.name] = true
                end
            end
            checked("capability_snapshot", "PASSED", capability_path)
        else
            checked("capability_snapshot", "FAILED",
                "Snapshot de capabilities ausente ou incompatível.")
        end
    else
        checked("capability_snapshot", "UNVERIFIED",
            "Execute O Editor - Capability Probe antes do preflight.")
    end
    local missing_capabilities = {}
    local function require_capability(name)
        if not supported[name] and not missing_capabilities[name] then
            missing_capabilities[name] = true
            details.missing_capabilities[#details.missing_capabilities + 1] = name
        end
    end
    for _, name in ipairs(plan.required_capabilities or {}) do
        require_capability(name)
    end
    if not supported.duplicate_timeline then
        require_capability("duplicate_timeline")
        details.preflight_status = "BLOCKED"
        checked("duplicate_timeline", "UNVERIFIED",
            "A duplicação segura da timeline ainda não foi validada.")
        return {
            status = "BLOCKED",
            message = "Aplicação bloqueada. A duplicação segura da timeline ainda não foi validada.",
            details = details,
            markdown_lines = {
                "A timeline original não foi alterada.",
            },
        }
    end
    if #details.missing_capabilities > 0 then
        details.preflight_status = "CAPABILITIES_MISSING"
        checked("required_capabilities", "FAILED",
            table.concat(details.missing_capabilities, ", "))
        return {
            status = "BLOCKED",
            message = "Aplicação bloqueada. Existem capabilities ausentes.",
            details = details,
        }
    end

    details.preflight_status = "BLOCKED"
    checked("fingerprint_readback", "UNVERIFIED",
        "O fingerprint ativo não foi recalculado por este preflight.")
    return {
        status = "BLOCKED",
        message = "Aplicação bloqueada. O fingerprint ativo ainda não foi verificado.",
        details = details,
        markdown_lines = {
            "O plano passou pelas verificações disponíveis, mas nenhuma mutação foi executada.",
        },
    }
end, {
    log_name = "internal-apply",
    script_path = common.script_path(2),
    script_version = SCRIPT_VERSION,
    build_hash = BUILD_HASH,
    })
end, debug.traceback)
if not action_ok then
    bootstrap_failure(action_error)
end