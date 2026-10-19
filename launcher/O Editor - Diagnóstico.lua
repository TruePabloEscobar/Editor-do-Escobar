-- Visible read-only internal diagnostic for O Editor.

local SCRIPT_VERSION = "2.4.0"
local BUILD_HASH = "microphone-clip-state-20261019"
local appdata = os.getenv("APPDATA")
local base = appdata and (appdata .. "\\O Editor") or "."
local log_path = base .. "\\logs\\internal-diagnostic.log"

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
    local handle = io.open(base .. "\\reports\\diagnostic-bootstrap-error.txt", "wb")
    if handle then
        handle:write(tostring(message))
        handle:close()
    end
    local safe = tostring(message):gsub('"', "'"):gsub("[\r\n]", " ")
    os.execute('cmd.exe /d /s /c ""' .. base
        .. '\\launch-editor.cmd" --show-message "' .. safe .. '""')
    print("O Editor: " .. tostring(message))
end

raw_log("Diagnostic bootstrap started; version=" .. SCRIPT_VERSION
    .. "; build=" .. BUILD_HASH)
local loaded, common = xpcall(function()
    return dofile(base .. "\\internal_common.lua")
end, debug.traceback)
if not loaded then
    bootstrap_failure(common)
    return
end

local action_ok, action_error = xpcall(function()
    return common.run_internal_action("diagnostic", function(runtime)
    local checks = {}
    local function add(name, status, value, failure)
        checks[#checks + 1] = {
            name = name,
            status = status,
            value = value,
            error = failure,
        }
    end
    local function check(name, operation, validator)
        local value, failure = common.safe_call(name, operation)
        if failure then
            add(name, "FAILED", nil, failure)
            return nil
        end
        if validator and not validator(value) then
            add(name, "FAILED", tostring(value), "Retorno inválido.")
            return nil
        end
        add(name, "PASSED", tostring(value), nil)
        return value
    end

    if runtime.context then
        add("resolve_source", "PASSED", runtime.context.resolve_source, nil)
        add("resolve_version", "PASSED", runtime.context.resolve_version, nil)
        add("project", "PASSED", runtime.context.project_name, nil)
        add("timeline", "PASSED", runtime.context.timeline_name, nil)
        add("frame_rate", "PASSED", runtime.context.fps, nil)
        add("start_timecode", "PASSED", runtime.context.start_timecode, nil)
    else
        add("resolve", "FAILED", nil, runtime.context_error)
    end

    if runtime.project then
        check("MediaPool", function()
            return runtime.project:GetMediaPool()
        end, function(value) return value ~= nil end)
    else
        add("MediaPool", "UNVERIFIED", nil, "Projeto interno indisponível.")
    end
    if runtime.resolve_object then
        check("Fusion", function()
            return runtime.resolve_object:Fusion()
        end, function(value) return value ~= nil end)
    else
        add("Fusion", "UNVERIFIED", nil, "Resolve interno indisponível.")
    end

    local clip_counts = {video = 0, audio = 0, subtitle = 0}
    if runtime.timeline and runtime.context then
        for _, track_type in ipairs({"video", "audio", "subtitle"}) do
            local count = tonumber(runtime.context.track_counts[track_type]) or 0
            add(track_type .. "_tracks", "PASSED", count, nil)
            for index = 1, count do
                local items = check(track_type .. "_items_" .. index, function()
                    return runtime.timeline:GetItemListInTrack(track_type, index)
                end, function(value) return type(value) == "table" end)
                if type(items) == "table" then
                    for _, _ in ipairs(items) do
                        clip_counts[track_type] = clip_counts[track_type] + 1
                    end
                end
            end
        end
    else
        add("timeline_items", "UNVERIFIED", nil, "Timeline interna indisponível.")
    end

    for name, path in pairs({
        launcher = base .. "\\launch-editor.cmd",
        launcher_config = base .. "\\launcher.json",
        helper = base .. "\\internal_common.lua",
        plan = base .. "\\plans\\latest-approved-plan.json",
    }) do
        add(name, common.file_exists(path) and "PASSED" or "UNVERIFIED", path, nil)
    end

    local capability_path = base .. "\\internal-capabilities.json"
    if common.file_exists(capability_path) then
        local capability_ok, capability_value = pcall(common.read_json, capability_path)
        if capability_ok
                and type(capability_value) == "table"
                and capability_value.schema_version == 1
                and capability_value.mode == "READ_ONLY"
                and capability_value.mutations_executed == false
                and capability_value.script_version == SCRIPT_VERSION
                and capability_value.build_hash == BUILD_HASH
                and capability_value.common_version == common.COMMON_VERSION
                and capability_value.common_hash == common.COMMON_HASH
                and type(capability_value.results) == "table" then
            add("capabilities", "PASSED", capability_path, nil)
        else
            add("capabilities", "FAILED", capability_path,
                "Snapshot de capabilities incompatível.")
        end
    else
        add("capabilities", "UNVERIFIED", capability_path,
            "Execute O Editor - Capability Probe.")
    end

    local config = nil
    local config_ok, config_value = pcall(common.load_launcher_config)
    if config_ok then
        config = config_value
        add("launcher_configuration", "PASSED", config.project_root, nil)
        add("script_version_match",
            config.script_version == SCRIPT_VERSION and "PASSED" or "FAILED",
            tostring(config.script_version),
            config.script_version == SCRIPT_VERSION and nil
                or ("Em execução: " .. SCRIPT_VERSION))
        add("build_hash_match",
            config.build_hash == BUILD_HASH and "PASSED" or "FAILED",
            tostring(config.build_hash),
            config.build_hash == BUILD_HASH and nil
                or ("Em execução: " .. BUILD_HASH))
        for artifact_name, hashes in pairs(config.artifacts or {}) do
            local hashes_match = type(hashes) == "table"
                and type(hashes.source_sha256) == "string"
                and hashes.source_sha256 ~= ""
                and hashes.source_sha256 == hashes.installed_sha256
            add("installed_hash_" .. tostring(artifact_name),
                hashes_match and "PASSED" or "FAILED",
                hashes_match and hashes.installed_sha256 or nil,
                hashes_match and nil or "Hashes fonte/instalado divergentes no launcher.json.")
        end
    else
        add("launcher_configuration", "FAILED", nil, tostring(config_value))
    end
    local versions = {
        script_version = SCRIPT_VERSION,
        build_hash = BUILD_HASH,
        common_version = common.COMMON_VERSION,
        common_hash = common.COMMON_HASH,
        configured_artifacts = config and config.artifacts or {},
    }
    return {
        status = runtime.context and "SUCCESS" or "FAILED",
        message = runtime.context
            and "Diagnóstico interno somente leitura concluído."
            or "Diagnóstico interno concluído com falha de contexto.",
        details = {
            checks = checks,
            clip_counts = clip_counts,
            versions = versions,
            read_only = true,
        },
        markdown_lines = {
            "O diagnóstico executou apenas leituras documentadas e verificações de arquivos.",
            "",
            "- Mutações: `não executadas`",
        },
    }
end, {
    log_name = "internal-diagnostic",
    script_path = common.script_path(2),
    script_version = SCRIPT_VERSION,
    build_hash = BUILD_HASH,
    })
end, debug.traceback)
if not action_ok then
    bootstrap_failure(action_error)
end