-- Visible internal Resolve capability probe. READ_ONLY is mandatory.

local SCRIPT_VERSION = "2.4.0"
local BUILD_HASH = "microphone-clip-state-20261019"
local appdata = os.getenv("APPDATA")
local base = appdata and (appdata .. "\\O Editor") or "."
local log_path = base .. "\\logs\\internal-capability.log"

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
    local handle = io.open(base .. "\\reports\\capability-bootstrap-error.txt", "wb")
    if handle then
        handle:write(tostring(message))
        handle:close()
    end
    local safe = tostring(message):gsub('"', "'"):gsub("[\r\n]", " ")
    os.execute('cmd.exe /d /s /c ""' .. base
        .. '\\launch-editor.cmd" --show-message "' .. safe .. '""')
    print("O Editor: " .. tostring(message))
end

raw_log("Capability bootstrap started; mode=READ_ONLY; version=" .. SCRIPT_VERSION
    .. "; build=" .. BUILD_HASH)
local loaded, common = xpcall(function()
    return dofile(base .. "\\internal_common.lua")
end, debug.traceback)
if not loaded then
    bootstrap_failure(common)
    return
end

local action_ok, action_error = xpcall(function()
    return common.run_internal_action("capability_probe", function(runtime)
    local results = {}
    local function result(name, status, method, value, failure, notes)
        results[#results + 1] = {
            name = name,
            status = status,
            method = method,
            value = value,
            error = failure,
            notes = notes,
        }
    end
    local function probe(name, method, operation, validator)
        local value, failure = common.safe_call(method, operation)
        if failure then
            result(name, "FAILED", method, nil, failure, "Leitura executada e falhou.")
            return nil
        end
        if validator and not validator(value) then
            result(name, "FAILED", method, tostring(value), "Retorno inválido.",
                "Leitura executada, mas não validada.")
            return nil
        end
        result(name, "SUPPORTED", method, tostring(value), nil,
            "Leitura executada e retorno validado.")
        return value
    end

    if runtime.resolve_object then
        result("resolve_object", "SUPPORTED", runtime.context.resolve_source,
            runtime.context.resolve_version, nil, "Objeto interno verificado por GetProjectManager.")
        probe("fusion_object", "Resolve.Fusion", function()
            return runtime.resolve_object:Fusion()
        end, function(value) return value ~= nil end)
        probe("project_manager", "Resolve.GetProjectManager", function()
            return runtime.resolve_object:GetProjectManager()
        end, function(value) return value ~= nil end)
    else
        result("resolve_object", "FAILED", nil, nil, runtime.context_error,
            "Nenhum fallback externo foi usado.")
    end
    if runtime.project then
        probe("active_project", "ProjectManager.GetCurrentProject", function()
            return runtime.project_manager:GetCurrentProject()
        end, function(value) return value ~= nil end)
        probe("media_pool", "Project.GetMediaPool", function()
            return runtime.project:GetMediaPool()
        end, function(value) return value ~= nil end)
    end
    if runtime.timeline then
        probe("active_timeline", "Project.GetCurrentTimeline", function()
            return runtime.project:GetCurrentTimeline()
        end, function(value) return value ~= nil end)
        probe("timeline_start_frame", "Timeline.GetStartFrame", function()
            return runtime.timeline:GetStartFrame()
        end, function(value) return tonumber(value) ~= nil end)
        probe("timeline_end_frame", "Timeline.GetEndFrame", function()
            return runtime.timeline:GetEndFrame()
        end, function(value) return tonumber(value) ~= nil end)
        probe("timeline_start_timecode", "Timeline.GetStartTimecode", function()
            return runtime.timeline:GetStartTimecode()
        end, function(value) return type(value) == "string" end)
        probe("timeline_fps", "Timeline.GetSetting(timelineFrameRate)", function()
            return runtime.timeline:GetSetting("timelineFrameRate")
        end, function(value) return tonumber(value) ~= nil end)
        probe("markers", "Timeline.GetMarkers", function()
            return runtime.timeline:GetMarkers()
        end, function(value) return type(value) == "table" end)

        for _, track_type in ipairs({"video", "audio", "subtitle"}) do
            local count = probe("track_count_" .. track_type, "Timeline.GetTrackCount", function()
                return runtime.timeline:GetTrackCount(track_type)
            end, function(value) return tonumber(value) ~= nil end)
            for index = 1, tonumber(count) or 0 do
                local items = probe(
                    "timeline_items_" .. track_type .. "_" .. index,
                    "Timeline.GetItemListInTrack",
                    function() return runtime.timeline:GetItemListInTrack(track_type, index) end,
                    function(value) return type(value) == "table" end
                )
                if track_type == "audio" then
                    probe("audio_track_name_" .. index, "Timeline.GetTrackName", function()
                        return runtime.timeline:GetTrackName("audio", index)
                    end, function(value) return type(value) == "string" end)
                    probe("audio_track_type_" .. index, "Timeline.GetTrackSubType", function()
                        return runtime.timeline:GetTrackSubType("audio", index)
                    end, function(value) return type(value) == "string" end)
                    probe("audio_track_enabled_" .. index,
                        "Timeline.GetIsTrackEnabled", function()
                            return runtime.timeline:GetIsTrackEnabled("audio", index)
                        end, function(value) return type(value) == "boolean" end)
                    probe("audio_track_locked_" .. index,
                        "Timeline.GetIsTrackLocked", function()
                            return runtime.timeline:GetIsTrackLocked("audio", index)
                        end, function(value) return type(value) == "boolean" end)
                end
                if track_type == "video" and type(items) == "table" then
                    -- Resolve 21 proxy tables can expose metadata keys such as
                    -- __flags. Only numeric editorial entries are timeline items.
                    for item_index, item in ipairs(items) do
                        probe("clip_properties_" .. tostring(item_index),
                            "TimelineItem.GetProperty",
                            function() return item:GetProperty() end,
                            function(value) return type(value) == "table" end)
                        local count_name = "fusion_comp_count_" .. tostring(item_index)
                        local comp_count = probe(count_name,
                            "TimelineItem.GetFusionCompCount",
                            function() return item:GetFusionCompCount() end,
                            function(value) return tonumber(value) ~= nil end)
                        for comp_index = 1, tonumber(comp_count) or 0 do
                            probe("fusion_comp_" .. tostring(item_index) .. "_" .. comp_index,
                                "TimelineItem.GetFusionCompByIndex",
                                function() return item:GetFusionCompByIndex(comp_index) end,
                                function(value) return value ~= nil end)
                        end
                    end
                end
            end
        end
    end

    for _, capability in ipairs({
        "create_marker", "delete_marker", "add_video_track", "rename_track",
        "duplicate_timeline", "fusion_composition", "fusion_nodes",
        "fusion_transform", "fusion_keyframes", "fusion_title", "text_plus",
        "set_title_duration", "position_title", "export_audio", "save_project",
        "select_single_audio_track_for_render", "select_multiple_audio_tracks_for_render",
        "export_audio_only", "export_wav", "set_audio_sample_rate", "set_audio_channels",
        "create_render_job", "start_render", "render_progress", "cancel_render",
        "validate_rendered_file", "remove_render_job", "restore_original_track_state",
    }) do
        result(capability, "UNVERIFIED", nil, nil, nil,
            "Modo READ_ONLY: mutação não executada. Backend permanece bloqueado.")
    end
    local capability_path = base .. "\\internal-capabilities.json"
    common.write_json(capability_path, {
        schema_version = 1,
        generated_at = common.timestamp(),
        mode = "READ_ONLY",
        mutations_executed = false,
        project = runtime.context and runtime.context.project_name or nil,
        timeline = runtime.context and runtime.context.timeline_name or nil,
        resolve_version = runtime.context and runtime.context.resolve_version or nil,
        script_version = SCRIPT_VERSION,
        build_hash = BUILD_HASH,
        common_version = common.COMMON_VERSION,
        common_hash = common.COMMON_HASH,
        results = results,
    })
    return {
        status = runtime.resolve_object and "SUCCESS" or "FAILED",
        message = runtime.resolve_object
            and "Capability probe interno concluído em modo READ_ONLY."
            or "Capability probe interno falhou ao obter o Resolve.",
        details = {
            mode = "READ_ONLY",
            mutation_mode = false,
            capability_file = capability_path,
            results = results,
        },
        markdown_lines = {
            "Resultados `UNVERIFIED` são exibidos e não habilitam backends.",
            "",
            "- Snapshot canônico: `" .. capability_path .. "`",
            "- Bridge externa: `não usada`",
            "- Mutações: `não executadas`",
        },
    }
end, {
    log_name = "internal-capability",
    script_path = common.script_path(2),
    script_version = SCRIPT_VERSION,
    build_hash = BUILD_HASH,
    })
end, debug.traceback)
if not action_ok then
    bootstrap_failure(action_error)
end