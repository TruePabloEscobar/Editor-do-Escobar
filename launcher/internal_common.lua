-- Shared stdlib-only helpers for O Editor scripts hosted inside DaVinci Resolve.

local M = {}
local JSON_NULL = {}

M.COMMON_VERSION = "2.4.0"
M.COMMON_HASH = "microphone-clip-state-20261019"

local function parent_directory(path)
    return tostring(path):match("^(.*)[/\\][^/\\]+$")
end

local function traceback_message(message)
    if debug and debug.traceback then
        return debug.traceback(tostring(message), 2)
    end
    return tostring(message)
end

function M.timestamp()
    return os.date("!%Y-%m-%dT%H:%M:%SZ")
end

function M.app_data_dir()
    local appdata = os.getenv("APPDATA")
    if not appdata or appdata == "" then
        error("APPDATA não está disponível.")
    end
    return appdata .. "\\O Editor"
end

function M.temp_dir()
    local temporary = os.getenv("TEMP") or os.getenv("TMP")
    if not temporary or temporary == "" then
        error("TEMP não está disponível.")
    end
    return temporary .. "\\o-editor"
end

function M.quote_windows_arg(value)
    local text = tostring(value or "")
    if text:find("[\r\n%z]") then
        error("Argumento contém CR, LF ou NUL.")
    end
    return '"' .. text:gsub('"', '""') .. '"'
end

function M.ensure_directory(path)
    local command = "cmd.exe /d /c if not exist " .. M.quote_windows_arg(path)
        .. " mkdir " .. M.quote_windows_arg(path)
    local result = os.execute(command)
    if result ~= true and result ~= 0 then
        error("Não foi possível criar o diretório: " .. tostring(path))
    end
end

function M.file_exists(path)
    local handle = io.open(path, "rb")
    if handle then
        handle:close()
        return true
    end
    return false
end

function M.read_text(path)
    local handle, open_error = io.open(path, "rb")
    if not handle then
        error("Não foi possível abrir " .. tostring(path) .. ": " .. tostring(open_error))
    end
    local content = handle:read("*a")
    handle:close()
    return content
end

function M.write_text(path, content)
    local parent = parent_directory(path)
    if parent then
        M.ensure_directory(parent)
    end
    local handle, open_error = io.open(path, "wb")
    if not handle then
        error("Não foi possível gravar " .. tostring(path) .. ": " .. tostring(open_error))
    end
    handle:write(tostring(content or ""))
    handle:close()
end

function M.append_log(path, message)
    local parent = parent_directory(path)
    if parent then
        pcall(M.ensure_directory, parent)
    end
    local handle = io.open(path, "ab")
    if handle then
        handle:write(M.timestamp() .. " " .. tostring(message) .. "\n")
        handle:close()
    end
end

function M.script_path(level)
    local info = debug.getinfo(level or 2, "S")
    local source = info and info.source or ""
    return source:sub(1, 1) == "@" and source:sub(2) or source
end

function M.current_directory()
    return os.getenv("CD") or "(não informado pelo host)"
end

local function encode_string(value)
    local escaped = tostring(value)
        :gsub("\\", "\\\\")
        :gsub('"', '\\"')
        :gsub("\b", "\\b")
        :gsub("\f", "\\f")
        :gsub("\n", "\\n")
        :gsub("\r", "\\r")
        :gsub("\t", "\\t")
    return '"' .. escaped .. '"'
end

local function is_array(value)
    local count = 0
    local maximum = 0
    for key, _ in pairs(value) do
        if type(key) ~= "number" or key < 1 or key % 1 ~= 0 then
            return false
        end
        count = count + 1
        maximum = math.max(maximum, key)
    end
    return maximum == count
end

local function json_encode_value(value, stack)
    local value_type = type(value)
    if value == JSON_NULL or value_type == "nil" then
        return "null"
    elseif value_type == "boolean" or value_type == "number" then
        return tostring(value)
    elseif value_type == "string" then
        return encode_string(value)
    elseif value_type ~= "table" then
        return encode_string(tostring(value))
    end
    if stack[value] then
        error("Referência circular não pode ser serializada.")
    end
    stack[value] = true
    local values = {}
    if is_array(value) then
        for index = 1, #value do
            values[#values + 1] = json_encode_value(value[index], stack)
        end
        stack[value] = nil
        return "[" .. table.concat(values, ",") .. "]"
    end
    local keys = {}
    for key, _ in pairs(value) do
        keys[#keys + 1] = key
    end
    table.sort(keys, function(left, right)
        return tostring(left) < tostring(right)
    end)
    for _, key in ipairs(keys) do
        values[#values + 1] = encode_string(tostring(key)) .. ":"
            .. json_encode_value(value[key], stack)
    end
    stack[value] = nil
    return "{" .. table.concat(values, ",") .. "}"
end

function M.json_encode(value)
    return json_encode_value(value, {})
end

local function decode_error(position, message)
    error("JSON inválido na posição " .. tostring(position) .. ": " .. message)
end

local function json_parser(text)
    local position = 1
    local length = #text
    local parse_value

    local function skip_space()
        while position <= length and text:sub(position, position):match("%s") do
            position = position + 1
        end
    end

    local function parse_string()
        if text:sub(position, position) ~= '"' then
            decode_error(position, "string esperada")
        end
        position = position + 1
        local output = {}
        while position <= length do
            local character = text:sub(position, position)
            if character == '"' then
                position = position + 1
                return table.concat(output)
            end
            if character == "\\" then
                position = position + 1
                local escaped = text:sub(position, position)
                local replacements = {
                    ['"'] = '"',
                    ["\\"] = "\\",
                    ["/"] = "/",
                    ["b"] = "\b",
                    ["f"] = "\f",
                    ["n"] = "\n",
                    ["r"] = "\r",
                    ["t"] = "\t",
                }
                if replacements[escaped] then
                    output[#output + 1] = replacements[escaped]
                elseif escaped == "u" then
                    local hex = text:sub(position + 1, position + 4)
                    if not hex:match("^%x%x%x%x$") then
                        decode_error(position, "escape unicode inválido")
                    end
                    local code = tonumber(hex, 16)
                    if code and code < 128 then
                        output[#output + 1] = string.char(code)
                    else
                        output[#output + 1] = "?"
                    end
                    position = position + 4
                else
                    decode_error(position, "escape inválido")
                end
            else
                output[#output + 1] = character
            end
            position = position + 1
        end
        decode_error(position, "string não terminada")
    end

    local function parse_array()
        position = position + 1
        local result = {}
        skip_space()
        if text:sub(position, position) == "]" then
            position = position + 1
            return result
        end
        while true do
            result[#result + 1] = parse_value()
            skip_space()
            local separator = text:sub(position, position)
            if separator == "]" then
                position = position + 1
                return result
            elseif separator ~= "," then
                decode_error(position, "',' ou ']' esperado")
            end
            position = position + 1
        end
    end

    local function parse_object()
        position = position + 1
        local result = {}
        skip_space()
        if text:sub(position, position) == "}" then
            position = position + 1
            return result
        end
        while true do
            skip_space()
            local key = parse_string()
            skip_space()
            if text:sub(position, position) ~= ":" then
                decode_error(position, "':' esperado")
            end
            position = position + 1
            result[key] = parse_value()
            skip_space()
            local separator = text:sub(position, position)
            if separator == "}" then
                position = position + 1
                return result
            elseif separator ~= "," then
                decode_error(position, "',' ou '}' esperado")
            end
            position = position + 1
        end
    end

    function parse_value()
        skip_space()
        local character = text:sub(position, position)
        if character == '"' then
            return parse_string()
        elseif character == "{" then
            return parse_object()
        elseif character == "[" then
            return parse_array()
        end
        local literal = text:sub(position)
        if literal:sub(1, 4) == "true" then
            position = position + 4
            return true
        elseif literal:sub(1, 5) == "false" then
            position = position + 5
            return false
        elseif literal:sub(1, 4) == "null" then
            position = position + 4
            return JSON_NULL
        end
        local number = literal:match("^%-?%d+%.?%d*[eE]?[%+%-]?%d*")
        if number and number ~= "" then
            position = position + #number
            return tonumber(number)
        end
        decode_error(position, "valor esperado")
    end

    local result = parse_value()
    skip_space()
    if position <= length then
        decode_error(position, "conteúdo adicional")
    end
    return result
end

function M.json_decode(text)
    return json_parser(text)
end

function M.read_json(path)
    return M.json_decode(M.read_text(path))
end

function M.write_json(path, value)
    M.write_text(path, M.json_encode(value))
end

function M.safe_call(label, operation)
    local ok, value = pcall(operation)
    if not ok then
        return nil, label .. ": " .. tostring(value)
    end
    return value, nil
end

function M.uuid()
    local address = tostring({}):match("0x(%x+)")
    local salt = tonumber(address or "0", 16) or 0
    math.randomseed(os.time() + salt)
    local template = "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx"
    return template:gsub("[xy]", function(character)
        local value = character == "x" and math.random(0, 15) or math.random(8, 11)
        return string.format("%x", value)
    end)
end

function M.load_launcher_config()
    local path = M.app_data_dir() .. "\\launcher.json"
    local config = M.read_json(path)
    if type(config) ~= "table" or config.schema_version ~= 1 then
        error("launcher.json possui schema_version incompatível.")
    end
    for _, key in ipairs({"project_root", "python_executable", "module"}) do
        if type(config[key]) ~= "string" or config[key] == "" then
            error("launcher.json não contém " .. key .. " válido.")
        end
    end
    if config.internal_host_enabled ~= true then
        error("O host interno está desabilitado em launcher.json.")
    end
    if config.external_bridge_enabled ~= false then
        error("A bridge externa deve permanecer desabilitada.")
    end
    if not M.file_exists(config.python_executable) then
        error("O Python configurado não existe: " .. config.python_executable)
    end
    return config
end

local function read_member(target, name)
    local ok, value = pcall(function()
        return target and target[name]
    end)
    return ok and value or nil
end

local function validate_resolve_candidate(candidate)
    if candidate == nil then
        return nil, "objeto ausente"
    end
    local method = read_member(candidate, "GetProjectManager")
    if type(method) ~= "function" then
        return nil, "GetProjectManager não está disponível"
    end
    local ok, manager = pcall(method, candidate)
    if not ok then
        return nil, "GetProjectManager falhou: " .. tostring(manager)
    end
    if manager == nil then
        return nil, "GetProjectManager retornou nil"
    end
    return candidate, nil
end

function M.get_internal_resolve(log_path)
    local function log(message)
        if log_path then
            M.append_log(log_path, message)
        end
    end
    log("Internal globals: resolve=" .. type(rawget(_G, "resolve"))
        .. "; app=" .. type(rawget(_G, "app"))
        .. "; Resolve=" .. type(rawget(_G, "Resolve")))
    local failures = {}
    local candidate, reason = validate_resolve_candidate(rawget(_G, "resolve"))
    if candidate then
        log("Internal Resolve source: global resolve")
        return candidate, "global resolve", nil
    end
    failures[#failures + 1] = "global resolve: " .. tostring(reason)

    local app_object = rawget(_G, "app")
    candidate, reason = validate_resolve_candidate(app_object)
    if candidate then
        log("Internal Resolve source: global app (Resolve-compatible object)")
        return candidate, "global app", nil
    end
    failures[#failures + 1] = "global app: " .. tostring(reason)

    local get_resolve = read_member(app_object, "GetResolve")
    if type(get_resolve) == "function" then
        local ok, app_resolve = pcall(get_resolve, app_object)
        if ok then
            candidate, reason = validate_resolve_candidate(app_resolve)
            if candidate then
                log("Internal Resolve source: app.GetResolve")
                return candidate, "app.GetResolve", nil
            end
        else
            reason = tostring(app_resolve)
        end
        failures[#failures + 1] = "app.GetResolve: " .. tostring(reason)
    else
        failures[#failures + 1] =
            "app.GetResolve: método não exposto; não documentado para scripts de menu"
    end

    local resolve_function = rawget(_G, "Resolve")
    if type(resolve_function) == "function" then
        local ok, official_resolve = pcall(resolve_function)
        if ok then
            candidate, reason = validate_resolve_candidate(official_resolve)
            if candidate then
                log("Internal Resolve source: documented Resolve()")
                return candidate, "documented Resolve()", nil
            end
        else
            reason = tostring(official_resolve)
        end
        failures[#failures + 1] = "Resolve(): " .. tostring(reason)
    else
        failures[#failures + 1] = "Resolve(): função global ausente"
    end

    local message = table.concat(failures, "; ")
    log("Internal Resolve unavailable: " .. message)
    return nil, nil, message
end

-- Calls target:method(...) only when the host exposes it. Returns value, error.
function M.call_method(target, method, ...)
    if target == nil then
        return nil, method .. ": objeto ausente"
    end
    local member = read_member(target, method)
    if type(member) ~= "function" then
        return nil, method .. ": método não exposto"
    end
    local arguments = {...}
    local count = select("#", ...)
    local ok, value = pcall(function()
        return member(target, unpack(arguments, 1, count))
    end)
    if not ok then
        return nil, method .. ": " .. tostring(value)
    end
    return value, nil
end

local function number_or_null(value)
    local parsed = tonumber(value)
    if parsed == nil then
        return JSON_NULL
    end
    return parsed
end

local function string_or_null(value)
    if value == nil or type(value) == "table" then
        return JSON_NULL
    end
    local text = tostring(value)
    if text == "" then
        return JSON_NULL
    end
    return text
end

local function list_items(value)
    local result = {}
    if type(value) ~= "table" then
        return result
    end
    for _, item in ipairs(value) do
        result[#result + 1] = item
    end
    if #result == 0 then
        local keys = {}
        for key, _ in pairs(value) do
            if type(key) == "number" then
                keys[#keys + 1] = key
            end
        end
        table.sort(keys)
        for _, key in ipairs(keys) do
            result[#result + 1] = value[key]
        end
    end
    return result
end
M.list_items = list_items

local function capture_clip(item, track_type, track_index, item_index, warnings)
    local id = M.call_method(item, "GetUniqueId")
    if id == nil or tostring(id) == "" then
        id = track_type .. tostring(track_index) .. "_item" .. tostring(item_index)
        warnings[#warnings + 1] = "Item sem GetUniqueId em " .. track_type .. " "
            .. tostring(track_index) .. "; identificador sintético usado."
    end
    local start_frame = tonumber((M.call_method(item, "GetStart", false)))
    local end_frame = tonumber((M.call_method(item, "GetEnd", false)))
    if start_frame == nil or end_frame == nil then
        warnings[#warnings + 1] = "Item " .. tostring(id) .. " sem início/fim legível; ignorado."
        return nil
    end
    local item_type = M.call_method(item, "GetType")
    if type(item_type) ~= "string" or item_type == "" then
        item_type = track_type
    end
    local clip = {
        item_id = tostring(id),
        track_type = track_type,
        track_index = track_index,
        item_index = item_index,
        name = string_or_null((M.call_method(item, "GetName"))),
        item_type = tostring(item_type):lower(),
        start_frame = start_frame,
        end_frame = end_frame,
        subframe_start = number_or_null((M.call_method(item, "GetStart", true))),
        subframe_end = number_or_null((M.call_method(item, "GetEnd", true))),
        source_start_frame = number_or_null((M.call_method(item, "GetSourceStartFrame"))),
        source_end_frame = number_or_null((M.call_method(item, "GetSourceEndFrame"))),
        source_start_seconds = number_or_null((M.call_method(item, "GetSourceStartTime"))),
        source_end_seconds = number_or_null((M.call_method(item, "GetSourceEndTime"))),
        left_offset_frames = number_or_null((M.call_method(item, "GetLeftOffset", false))),
        right_offset_frames = number_or_null((M.call_method(item, "GetRightOffset", false))),
        media_pool_item_id = JSON_NULL,
        file_path = JSON_NULL,
        media_fps = JSON_NULL,
        enabled = true,
        linked_item_ids = {},
        audio_channel_mapping = JSON_NULL,
        fusion_comp_count = 0,
        speed_percent = JSON_NULL,
    }
    local enabled = M.call_method(item, "GetClipEnabled")
    if type(enabled) == "boolean" then
        clip.enabled = enabled
    end
    local media_item = M.call_method(item, "GetMediaPoolItem")
    if media_item ~= nil then
        clip.media_pool_item_id = string_or_null((M.call_method(media_item, "GetUniqueId")))
        clip.file_path = string_or_null((M.call_method(media_item, "GetClipProperty", "File Path")))
        clip.media_fps = number_or_null((M.call_method(media_item, "GetClipProperty", "FPS")))
    end
    for _, linked in ipairs(list_items((M.call_method(item, "GetLinkedItems")))) do
        local linked_id = M.call_method(linked, "GetUniqueId")
        if linked_id ~= nil and tostring(linked_id) ~= tostring(id) then
            clip.linked_item_ids[#clip.linked_item_ids + 1] = tostring(linked_id)
        end
    end
    if track_type == "audio" then
        clip.audio_channel_mapping = string_or_null(
            (M.call_method(item, "GetSourceAudioChannelMapping")))
    else
        clip.fusion_comp_count = tonumber((M.call_method(item, "GetFusionCompCount"))) or 0
    end
    local speed = M.call_method(item, "GetSpeed")
    if type(speed) == "table" then
        clip.speed_percent = number_or_null(speed.Percentage)
    end
    return clip
end

-- Read-only clip-level capture of every track. Never mutates the timeline.
function M.capture_layout(timeline)
    local warnings = {}
    local tracks = {}
    local clips = {}
    for _, track_type in ipairs({"video", "audio", "subtitle"}) do
        local count = tonumber((M.call_method(timeline, "GetTrackCount", track_type))) or 0
        for index = 1, count do
            local subtype = JSON_NULL
            if track_type == "audio" then
                subtype = string_or_null((M.call_method(timeline, "GetTrackSubType", "audio", index)))
            end
            local enabled = M.call_method(timeline, "GetIsTrackEnabled", track_type, index)
            local locked = M.call_method(timeline, "GetIsTrackLocked", track_type, index)
            tracks[#tracks + 1] = {
                track_type = track_type,
                index = index,
                name = tostring((M.call_method(timeline, "GetTrackName", track_type, index)) or ""),
                subtype = subtype,
                enabled = type(enabled) == "boolean" and enabled or JSON_NULL,
                locked = type(locked) == "boolean" and locked or JSON_NULL,
            }
            if type(enabled) == "boolean" and enabled == false then
                tracks[#tracks].enabled = false
            end
            if type(locked) == "boolean" and locked == false then
                tracks[#tracks].locked = false
            end
            local items, items_error = M.call_method(timeline, "GetItemListInTrack", track_type, index)
            if items == nil then
                warnings[#warnings + 1] = "Não foi possível listar itens de " .. track_type
                    .. " " .. tostring(index) .. ": " .. tostring(items_error)
            end
            for item_index, item in ipairs(list_items(items)) do
                local clip = capture_clip(item, track_type, index, item_index, warnings)
                if clip then
                    clips[#clips + 1] = clip
                end
            end
        end
    end
    return {
        schema_version = 1,
        tracks = tracks,
        clips = clips,
        warnings = warnings,
    }
end

local function capture_audio_tracks(timeline)
    local count = tonumber(timeline:GetTrackCount("audio")) or 0
    local tracks = {}
    for index = 1, count do
        local name = M.safe_call("GetTrackName(audio)", function()
            return timeline:GetTrackName("audio", index)
        end)
        local subtype = M.safe_call("GetTrackSubType(audio)", function()
            return timeline:GetTrackSubType("audio", index)
        end)
        local enabled = M.safe_call("GetIsTrackEnabled(audio)", function()
            return timeline:GetIsTrackEnabled("audio", index)
        end)
        local locked = M.safe_call("GetIsTrackLocked(audio)", function()
            return timeline:GetIsTrackLocked("audio", index)
        end)
        local items = M.safe_call("GetItemListInTrack(audio)", function()
            return timeline:GetItemListInTrack("audio", index)
        end)
        local item_count = 0
        if type(items) == "table" then
            for _, _ in ipairs(items) do
                item_count = item_count + 1
            end
        end
        local audio_type = tostring(subtype or ""):lower()
        if audio_type ~= "mono" and audio_type ~= "stereo"
            and audio_type ~= "adaptive" then
            audio_type = "unknown"
        end
        local enabled_value = JSON_NULL
        local muted_value = JSON_NULL
        local locked_value = JSON_NULL
        if type(enabled) == "boolean" then
            enabled_value = enabled
            muted_value = not enabled
        end
        if type(locked) == "boolean" then
            locked_value = locked
        end
        tracks[#tracks + 1] = {
            index = index,
            label = "A" .. tostring(index),
            name = name ~= nil and tostring(name) or "",
            track_type = "audio",
            audio_type = audio_type,
            enabled = enabled_value,
            muted = muted_value,
            locked = locked_value,
            item_count = item_count,
        }
    end
    return tracks, count
end

function M.capture_context(log_path, options)
    options = options or {}
    local resolve_object, source_name, resolve_error = M.get_internal_resolve(log_path)
    if not resolve_object then
        error(resolve_error or "Objeto Resolve interno indisponível.")
    end
    local project_manager, manager_error = M.safe_call("GetProjectManager", function()
        return resolve_object:GetProjectManager()
    end)
    if not project_manager then
        error(manager_error or "ProjectManager indisponível.")
    end
    local project, project_error = M.safe_call("GetCurrentProject", function()
        return project_manager:GetCurrentProject()
    end)
    if not project then
        error(project_error or "Nenhum projeto está ativo.")
    end
    local timeline, timeline_error = M.safe_call("GetCurrentTimeline", function()
        return project:GetCurrentTimeline()
    end)
    if not timeline then
        error(timeline_error or "Nenhuma timeline está ativa.")
    end
    -- Resolve proxy objects can be sensitive to later collection reads. Capture stable
    -- identity before enumerating timeline items/tracks and verify it afterwards.
    local project_name, project_name_error = M.safe_call("Project.GetName", function()
        return project:GetName()
    end)
    local timeline_name, timeline_name_error = M.safe_call("Timeline.GetName", function()
        return timeline:GetName()
    end)
    if type(project_name) ~= "string" or project_name == "" then
        error(project_name_error or "O projeto ativo não retornou um nome válido.")
    end
    if type(timeline_name) ~= "string" or timeline_name == "" then
        error(timeline_name_error or "A timeline ativa não retornou um nome válido.")
    end
    local fps = timeline:GetSetting("timelineFrameRate")
    local start_frame = timeline:GetStartFrame()
    local end_frame = timeline:GetEndFrame()
    if tonumber(fps) == nil or tonumber(start_frame) == nil or tonumber(end_frame) == nil then
        error("O contexto interno retornou frames ou frame rate inválidos.")
    end
    local timeline_id = nil
    local id_value = M.safe_call("GetUniqueId", function()
        return timeline:GetUniqueId()
    end)
    if id_value then
        timeline_id = tostring(id_value)
    end
    local audio_tracks, audio_track_count = capture_audio_tracks(timeline)
    local layout = nil
    if options.capture_layout then
        layout = M.capture_layout(timeline)
    end
    local project_name_readback = M.safe_call("Project.GetName readback", function()
        return project:GetName()
    end)
    local timeline_name_readback = M.safe_call("Timeline.GetName readback", function()
        return timeline:GetName()
    end)
    if project_name_readback ~= project_name or timeline_name_readback ~= timeline_name then
        error("A identidade do projeto/timeline mudou durante a captura do contexto.")
    end
    return {
        schema_version = layout and 3 or 2,
        layout = layout or JSON_NULL,
        context_kind = "internal_resolve_host",
        timestamp = M.timestamp(),
        launched_from_resolve = true,
        resolve_source = source_name,
        resolve_version = tostring(resolve_object:GetVersionString() or ""),
        product_name = tostring(resolve_object:GetProductName() or ""),
        project_name = project_name,
        timeline_name = timeline_name,
        timeline_id = timeline_id or JSON_NULL,
        fps = tonumber(fps),
        start_frame = tonumber(start_frame),
        end_frame = tonumber(end_frame),
        duration_frames = tonumber(end_frame) - tonumber(start_frame),
        start_timecode = tostring(timeline:GetStartTimecode() or ""),
        track_counts = {
            video = tonumber(timeline:GetTrackCount("video")) or 0,
            audio = audio_track_count,
            subtitle = tonumber(timeline:GetTrackCount("subtitle")) or 0,
        },
        audio_track_count = audio_track_count,
        audio_tracks = audio_tracks,
    }, resolve_object, project_manager, project, timeline
end

function M.try_capture_context(log_path, options)
    local ok, context, resolve_object, project_manager, project, timeline =
        pcall(M.capture_context, log_path, options)
    if not ok then
        return nil, nil, nil, nil, nil, tostring(context)
    end
    return context, resolve_object, project_manager, project, timeline, nil
end

function M.launch_internal_request(request_path, log_path)
    local config_ok, config = pcall(M.load_launcher_config)
    if not config_ok then
        M.append_log(log_path,
            "Launcher configuration warning; using installed CMD: " .. tostring(config))
        config = nil
    end
    local launcher_cmd = M.app_data_dir() .. "\\launch-editor.cmd"
    if not M.file_exists(launcher_cmd) then
        error("launch-editor.cmd não foi instalado.")
    end
    local command = 'cmd.exe /d /s /c ""' .. launcher_cmd
        .. '" --internal-action-request ' .. M.quote_windows_arg(request_path) .. '"'
    M.append_log(log_path, "External launcher: " .. launcher_cmd)
    M.append_log(log_path, "External arguments: --internal-action-request " .. request_path)
    local result = os.execute(command)
    if result ~= true and result ~= 0 then
        error("launch-editor.cmd retornou " .. tostring(result))
    end
    M.append_log(log_path, "External request dispatched; module="
        .. tostring(config and config.module or "embedded in launch-editor.cmd"))
    return true
end

function M.markdown_escape(value)
    return tostring(value or ""):gsub("|", "\\|"):gsub("\r", " "):gsub("\n", " ")
end

local function render_generic_markdown(result)
    local lines = {
        "# Ação interna do O Editor",
        "",
        "- Ação: `" .. tostring(result.action) .. "`",
        "- Status: `" .. tostring(result.status) .. "`",
        "- Gerado em: `" .. tostring(result.created_at) .. "`",
        "- Projeto: `" .. tostring(result.project or "não disponível") .. "`",
        "- Timeline: `" .. tostring(result.timeline or "não disponível") .. "`",
        "- Script: `" .. tostring(result.script_version) .. "`",
        "- Build: `" .. tostring(result.build_hash) .. "`",
        "- Helper: `" .. tostring(result.common_version) .. "`",
        "- Mutações executadas: `" .. tostring(result.mutations_executed == true) .. "`",
        "",
        tostring(result.message or ""),
    }
    local custom = result.markdown_lines
    if type(custom) == "table" then
        lines[#lines + 1] = ""
        for _, line in ipairs(custom) do
            lines[#lines + 1] = tostring(line)
        end
    end
    return table.concat(lines, "\n") .. "\n"
end

function M.run_internal_action(action_name, action_function, options)
    options = options or {}
    local base = M.app_data_dir()
    local log_path = base .. "\\logs\\" .. tostring(options.log_name or action_name) .. ".log"
    local common_log_path = base .. "\\logs\\internal-common.log"
    for _, directory in ipairs({"logs", "requests", "requests\\processed", "reports", "plans"}) do
        M.ensure_directory(base .. "\\" .. directory)
    end
    local script_path = options.script_path or M.script_path(3)
    M.append_log(common_log_path, "Helper " .. M.COMMON_VERSION .. " action=" .. action_name)
    M.append_log(log_path, "Internal action start: " .. tostring(action_name))
    M.append_log(log_path, "script_path=" .. tostring(script_path))
    M.append_log(log_path, "cwd=" .. M.current_directory())
    M.append_log(log_path, "APPDATA=" .. tostring(os.getenv("APPDATA") or ""))
    M.append_log(log_path, "TEMP=" .. tostring(os.getenv("TEMP") or os.getenv("TMP") or ""))
    M.append_log(log_path, "script_version=" .. tostring(options.script_version or "unknown")
        .. "; build_hash=" .. tostring(options.build_hash or "unknown")
        .. "; common_version=" .. M.COMMON_VERSION
        .. "; common_hash=" .. M.COMMON_HASH)

    local context, resolve_object, project_manager, project, timeline, context_error =
        M.try_capture_context(log_path, {capture_layout = options.capture_layout == true})
    local runtime = {
        base = base,
        log_path = log_path,
        context = context,
        context_error = context_error,
        resolve_object = resolve_object,
        project_manager = project_manager,
        project = project,
        timeline = timeline,
    }
    local ok, action_result = xpcall(function()
        return action_function(runtime)
    end, traceback_message)
    if not ok then
        action_result = {
            status = "FAILED",
            message = "A ação interna falhou.",
            details = {error = tostring(action_result), context_error = context_error},
        }
    elseif type(action_result) ~= "table" then
        action_result = {
            status = "FAILED",
            message = "A ação interna não retornou um resultado válido.",
            details = {},
        }
    end
    local allowed = {
        SUCCESS = true,
        BLOCKED = true,
        FAILED = true,
        CANCELLED = true,
        UNSUPPORTED = true,
    }
    if not allowed[action_result.status] then
        action_result.status = "FAILED"
        action_result.message = "A ação interna retornou um status inválido."
    end
    action_result.details = type(action_result.details) == "table"
        and action_result.details or {}
    if type(runtime.correlation) == "table" then
        action_result.details.plan_id = action_result.details.plan_id or runtime.correlation.plan_id
        action_result.details.mode = action_result.details.mode or runtime.correlation.mode
    end
    if context then
        action_result.details.context = context
    elseif context_error then
        action_result.details.context_error = context_error
    end

    local request_id = M.uuid()
    local result_path = base .. "\\reports\\" .. action_name .. "-" .. request_id .. ".json"
    local report_path = base .. "\\reports\\" .. action_name .. "-" .. request_id .. ".md"
    local result = {
        schema_version = 1,
        request_id = request_id,
        action = action_name,
        created_at = M.timestamp(),
        status = action_result.status,
        project = context and context.project_name or action_result.project or JSON_NULL,
        timeline = context and context.timeline_name or action_result.timeline or JSON_NULL,
        message = action_result.message or "",
        details = action_result.details,
        script_path = script_path,
        script_version = options.script_version or "unknown",
        build_hash = options.build_hash or "unknown",
        common_version = M.COMMON_VERSION,
        common_hash = M.COMMON_HASH,
        cwd = M.current_directory(),
        appdata = os.getenv("APPDATA") or JSON_NULL,
        temporary_directory = os.getenv("TEMP") or os.getenv("TMP") or JSON_NULL,
        log_file = log_path,
        result_file = result_path,
        report_file = report_path,
        mutations_executed = action_result.mutations_executed == true,
        markdown_lines = action_result.markdown_lines,
    }
    M.write_json(result_path, result)
    M.write_text(report_path, render_generic_markdown(result))
    result.markdown_lines = nil
    local request_path = base .. "\\requests\\request-" .. request_id .. ".json"
    M.write_json(request_path, {
        schema_version = 1,
        request_id = request_id,
        action = action_name,
        created_at = result.created_at,
        status = result.status,
        project = result.project,
        timeline = result.timeline,
        result_file = result_path,
        report_file = report_path,
        log_file = log_path,
        message = result.message,
        details = result.details,
        script_version = result.script_version,
        build_hash = result.build_hash,
        common_version = result.common_version,
        common_hash = result.common_hash,
        mutations_executed = result.mutations_executed,
    })
    M.append_log(log_path, "Result JSON: " .. result_path)
    M.append_log(log_path, "Report Markdown: " .. report_path)
    M.append_log(log_path, "Request JSON: " .. request_path)

    local launched, launch_error = xpcall(function()
        return M.launch_internal_request(request_path, log_path)
    end, traceback_message)
    if not launched then
        M.append_log(log_path, "FAILED to open external interface: " .. tostring(launch_error))
        print("O Editor: não foi possível abrir a interface externa. " .. tostring(launch_error))
    else
        M.append_log(log_path, "Internal action completed: " .. result.status)
        print("O Editor: " .. tostring(result.message))
    end
    M.append_log(common_log_path, "Helper completed action=" .. action_name)
    return result.status, request_path, launched, launch_error
end

-- ---------------------------------------------------------------------------
-- Rough cut engine. Mutations happen ONLY on a timeline created by
-- DuplicateTimeline in this run; every step is verified by readback.
-- ---------------------------------------------------------------------------

M.ROUGH_CUT_PLAN_MAX_AGE_SECONDS = 12 * 3600

local COPY_PROPERTY_KEYS = {
    "TransformEnabled", "Pan", "Tilt", "ZoomX", "ZoomY", "ZoomGang", "RotationAngle",
    "AnchorPointX", "AnchorPointY", "Pitch", "Yaw", "FlipX", "FlipY", "CroppingEnabled",
    "CropLeft", "CropRight", "CropTop", "CropBottom", "CropSoftness", "CropRetain",
    "DynamicZoomEnabled", "DynamicZoomEase", "CompositeEnabled", "CompositeMode", "Opacity",
    "LensCorrectionEnabled", "Distortion", "RetimeAndScalingEnabled", "RetimeProcess",
    "MotionEstimation", "Scaling", "ResizeFilter", "AudioVolumeEnabled", "AudioVolume",
    "AudioPanEnabled", "AudioPan", "AudioPitchEnabled", "AudioPitchSemiTones",
    "AudioPitchCents", "AudioVoiceIsolationEnabled", "AudioVoiceIsolationAmount",
    "AudioDialogueLevelerEnabled", "AudioDialogueLevelerMode",
    "AudioDialogueLevelerReduceLoudDialogue", "AudioDialogueLevelerLiftSoftDialogue",
    "AudioDialogueLevelerBackgroundReduction", "AudioDialogueLevelerOutputGain",
}

local function iso_to_epoch(value)
    if type(value) ~= "string" then
        return nil
    end
    local year, month, day, hour, minute, second =
        value:match("^(%d%d%d%d)%-(%d%d)%-(%d%d)T(%d%d):(%d%d):(%d%d)")
    if not year then
        return nil
    end
    return os.time({year = tonumber(year), month = tonumber(month), day = tonumber(day),
        hour = tonumber(hour), min = tonumber(minute), sec = tonumber(second)})
end

local function utc_now_epoch()
    return os.time(os.date("!*t"))
end

local function item_track(item)
    local value = M.call_method(item, "GetTrackTypeAndIndex")
    if type(value) == "table" then
        local items = list_items(value)
        if #items >= 2 then
            return tostring(items[1]), tonumber(items[2])
        end
    end
    return nil, nil
end

local function collect_items(timeline)
    local result = {}
    for _, track_type in ipairs({"video", "audio", "subtitle"}) do
        local count = tonumber((M.call_method(timeline, "GetTrackCount", track_type))) or 0
        for index = 1, count do
            local items = list_items((M.call_method(timeline, "GetItemListInTrack", track_type, index)))
            for _, item in ipairs(items) do
                result[#result + 1] = {item = item, track_type = track_type, track_index = index}
            end
        end
    end
    return result
end

-- Exact structural comparison between the plan's captured clips and the live timeline.
function M.verify_source_layout(timeline, plan_source)
    local problems = {}
    local counts = plan_source.track_counts or {}
    for _, track_type in ipairs({"video", "audio", "subtitle"}) do
        local live = tonumber((M.call_method(timeline, "GetTrackCount", track_type))) or 0
        local expected = tonumber(counts[track_type]) or 0
        if live ~= expected then
            problems[#problems + 1] = "quantidade de tracks de " .. track_type .. " mudou ("
                .. tostring(expected) .. " -> " .. tostring(live) .. ")"
        end
    end
    local live_items = {}
    local live_count = 0
    for _, entry in ipairs(collect_items(timeline)) do
        local id = M.call_method(entry.item, "GetUniqueId")
        if id ~= nil then
            live_items[tostring(id)] = entry
        end
        live_count = live_count + 1
    end
    local expected_count = 0
    for _, clip in ipairs(plan_source.clips or {}) do
        expected_count = expected_count + 1
        local entry = live_items[tostring(clip.item_id)]
        if entry == nil then
            problems[#problems + 1] = "item " .. tostring(clip.item_id) .. " não existe mais"
        else
            local start_frame = tonumber((M.call_method(entry.item, "GetStart", false)))
            local end_frame = tonumber((M.call_method(entry.item, "GetEnd", false)))
            if entry.track_type ~= clip.track_type or entry.track_index ~= tonumber(clip.track_index)
                    or start_frame ~= tonumber(clip.start_frame)
                    or end_frame ~= tonumber(clip.end_frame) then
                problems[#problems + 1] = "item " .. tostring(clip.item_id) .. " foi movido ou alterado"
            end
            local mpi = M.call_method(entry.item, "GetMediaPoolItem")
            if type(clip.media_pool_item_id) == "string"
                    and tostring(M.call_method(mpi, "GetUniqueId")) ~= clip.media_pool_item_id then
                problems[#problems + 1] = "mídia de origem mudou: " .. tostring(clip.item_id)
            end
            if type(clip.left_offset_frames) == "number" then
                local left = tonumber((M.call_method(entry.item, "GetLeftOffset", false)))
                if left == nil or math.abs(left - clip.left_offset_frames) > 0.000001 then
                    problems[#problems + 1] = "ponto de entrada mudou: " .. tostring(clip.item_id)
                end
            elseif type(clip.source_start_frame) == "number"
                    and tonumber((M.call_method(entry.item, "GetSourceStartFrame"))) ~= clip.source_start_frame then
                problems[#problems + 1] = "origem do clipe mudou: " .. tostring(clip.item_id)
            end
            if type(clip.enabled) == "boolean"
                    and M.call_method(entry.item, "GetClipEnabled") ~= clip.enabled then
                problems[#problems + 1] = "estado do clipe mudou: " .. tostring(clip.item_id)
            end
            if type(clip.audio_channel_mapping) == "string" and clip.audio_channel_mapping ~= "" then
                local current = M.call_method(entry.item, "GetSourceAudioChannelMapping")
                local expected_ok, expected_mapping = pcall(M.json_decode, clip.audio_channel_mapping)
                local current_ok, current_mapping = pcall(M.json_decode, current)
                if not expected_ok or not current_ok
                        or type(expected_mapping) ~= "table" or type(current_mapping) ~= "table"
                        or M.json_encode(expected_mapping.track_mapping) ~= M.json_encode(current_mapping.track_mapping) then
                    problems[#problems + 1] = "canais de áudio mudaram: " .. tostring(clip.item_id)
                end
            end
        end
        if #problems > 20 then
            break
        end
    end
    if live_count ~= expected_count then
        problems[#problems + 1] = "quantidade de itens mudou (" .. tostring(expected_count)
            .. " -> " .. tostring(live_count) .. ")"
    end
    return problems, live_items
end

local function timeline_name_exists(project, name)
    local count = tonumber((M.call_method(project, "GetTimelineCount"))) or 0
    for index = 1, count do
        local timeline = M.call_method(project, "GetTimelineByIndex", index)
        if timeline ~= nil and M.call_method(timeline, "GetName") == name then
            return true
        end
    end
    return false
end

function M.unique_timeline_name(project, requested)
    local base = tostring(requested or "OE_ROUGHCUT")
    if not timeline_name_exists(project, base) then
        return base
    end
    local stem = base:gsub("_%d%d%d$", "")
    for number = 1, 999 do
        local candidate = stem .. string.format("_%03d", number)
        if not timeline_name_exists(project, candidate) then
            return candidate
        end
    end
    error("Não foi possível escolher um nome livre para a nova timeline.")
end

-- Compare only the documented mutable mapping, independently of JSON formatting.
local function audio_mapping_key(item)
    local text = M.call_method(item, "GetSourceAudioChannelMapping")
    if type(text) ~= "string" or text == "" then return nil end
    local ok, value = pcall(M.json_decode, text)
    if not ok or type(value) ~= "table" or type(value.track_mapping) ~= "table" then return nil end
    return M.json_encode(value.track_mapping)
end

local function source_time_matches(seconds, frame, fps)
    if math.abs(seconds * fps - frame) < 0.01 then return true end
    for _, nominal in ipairs({24, 30, 48, 60, 120}) do
        local rational = nominal * 1000 / 1001
        if math.abs(fps - rational) < 0.0002
                and math.abs(seconds * rational - frame) < 0.01 then return true end
    end
    return false
end

local function copy_item_attributes(original, created, op, counters)
    local properties = M.call_method(original, "GetProperties")
    local getter_single = false
    if type(properties) ~= "table" then
        properties = M.call_method(original, "GetProperty")
        getter_single = true
    end
    if type(properties) == "table" then
        for _, key in ipairs(COPY_PROPERTY_KEYS) do
            local value = properties[key]
            if value ~= nil and type(value) ~= "table" then
                local ok = M.call_method(created, "SetProperties", {[key] = value})
                if ok == nil then
                    ok = M.call_method(created, "SetProperty", key, value)
                end
                if ok == true then
                    counters.properties = counters.properties + 1
                else
                    counters.property_failures = counters.property_failures + 1
                end
            end
        end
    end
    if getter_single then
        counters.legacy_property_api = true
    end
    if op.media_type == 2 then
        local mapping = M.call_method(original, "GetSourceAudioChannelMapping")
        if type(mapping) == "string" and mapping ~= "" then
            local current = M.call_method(created, "GetSourceAudioChannelMapping")
            local expected_key = audio_mapping_key(original)
            if current ~= mapping and (expected_key == nil or audio_mapping_key(created) ~= expected_key) then
                local ok = M.call_method(created, "SetSourceAudioChannelMapping", mapping)
                if ok == true then
                    counters.channel_mappings = counters.channel_mappings + 1
                else
                    counters.channel_mapping_failures = counters.channel_mapping_failures + 1
                end
            end
        end
    end
    if op.enabled == false then
        M.call_method(created, "SetClipEnabled", false)
    end
    local color = M.call_method(original, "GetClipColor")
    if type(color) == "string" and color ~= "" then
        M.call_method(created, "SetClipColor", color)
    end
end

function M.apply_rough_cut(runtime, plan, log)
    log = log or function(_message) end
    local details = {
        plan_id = plan and plan.plan_id or JSON_NULL,
        mode = plan and plan.mode or JSON_NULL,
        checks = {},
        warnings = {},
        created_timeline = JSON_NULL,
        created_timeline_id = JSON_NULL,
        operations_total = 0,
        operations_applied = 0,
        calibration = {},
        original_verified_after = false,
    }
    local function check(name, status, detail)
        details.checks[#details.checks + 1] = {name = name, status = status, detail = tostring(detail or "")}
        log("check " .. name .. "=" .. status .. " " .. tostring(detail or ""))
    end
    local function outcome(status, message, mutated, lines)
        return {status = status, message = message, details = details,
            mutations_executed = mutated == true, markdown_lines = lines}
    end

    if type(plan) ~= "table" or plan.schema_version ~= 1 or plan.kind ~= "rough_cut" then
        check("plan_schema", "FAILED", "schema/kind inválido")
        return outcome("FAILED", "Plano de rough cut inválido. Nada foi alterado.", false)
    end
    check("plan_schema", "PASSED", "schema_version=1")
    local operations = type(plan.operations) == "table" and plan.operations or {}
    details.operations_total = #operations
    local created_epoch = iso_to_epoch(plan.created_at)
    if created_epoch == nil or utc_now_epoch() - created_epoch > M.ROUGH_CUT_PLAN_MAX_AGE_SECONDS then
        check("plan_age", "FAILED", tostring(plan.created_at))
        return outcome("BLOCKED", "O plano expirou ou não tem data válida. Gere a prévia novamente no O Editor.", false)
    end
    check("plan_age", "PASSED", tostring(plan.created_at))
    if not runtime.context or runtime.timeline == nil or runtime.project == nil then
        check("resolve_context", "FAILED", runtime.context_error)
        return outcome("BLOCKED", "Nenhuma timeline ativa disponível. Nada foi alterado.", false)
    end
    local source = plan.source or {}
    local context = runtime.context
    local mismatches = {}
    if source.project_name ~= context.project_name then mismatches[#mismatches + 1] = "projeto" end
    if source.timeline_name ~= context.timeline_name then mismatches[#mismatches + 1] = "timeline" end
    if type(source.timeline_id) == "string" and source.timeline_id ~= ""
            and context.timeline_id ~= JSON_NULL and source.timeline_id ~= context.timeline_id then
        mismatches[#mismatches + 1] = "identificador da timeline"
    end
    if tonumber(source.fps) ~= tonumber(context.fps) then mismatches[#mismatches + 1] = "frame rate" end
    if tonumber(source.start_frame) ~= tonumber(context.start_frame)
            or tonumber(source.end_frame) ~= tonumber(context.end_frame) then
        mismatches[#mismatches + 1] = "início/fim"
    end
    if #mismatches > 0 then
        check("context_match", "FAILED", table.concat(mismatches, ", "))
        return outcome("BLOCKED", "A timeline ativa não é a timeline do plano ("
            .. table.concat(mismatches, ", ") .. "). Abra a timeline original e tente novamente. Nada foi alterado.", false)
    end
    check("context_match", "PASSED", "projeto, timeline, fps e limites correspondem")
    local original = runtime.timeline
    local original_id = tostring((M.call_method(original, "GetUniqueId")) or "")
    local problems, live_items = M.verify_source_layout(original, source)
    if #problems > 0 then
        check("layout_match", "FAILED", table.concat(problems, "; "))
        return outcome("BLOCKED", "A timeline mudou desde a transcrição: " .. table.concat(problems, "; ")
            .. ". Transcreva novamente. Nada foi alterado.", false)
    end
    check("layout_match", "PASSED", "todos os clipes conferem")
    local media_items = {}
    for _, op in ipairs(operations) do
        local key = tostring(op.source_item_id)
        if media_items[key] == nil then
            local entry = live_items[key]
            local mpi = entry and M.call_method(entry.item, "GetMediaPoolItem") or nil
            local mpi_id = mpi and M.call_method(mpi, "GetUniqueId") or nil
            if mpi == nil or tostring(mpi_id) ~= tostring(op.media_pool_item_id) then
                check("media_pool_items", "FAILED", "origem ausente para " .. key)
                return outcome("BLOCKED", "Um clipe de origem não possui o item esperado no Media Pool ("
                    .. key .. "). Nada foi alterado.", false)
            end
            media_items[key] = {mpi = mpi, original = entry.item}
        end
    end
    check("media_pool_items", "PASSED", tostring(#operations) .. " operações com origem válida")
    local media_pool = M.call_method(runtime.project, "GetMediaPool")
    if media_pool == nil then
        check("media_pool", "FAILED", "GetMediaPool")
        return outcome("FAILED", "Media Pool indisponível. Nada foi alterado.", false)
    end
    if plan.mode ~= "APPLY" or plan.confirmed_by_user ~= true then
        return outcome("SUCCESS", "Validação concluída no Resolve: o plano pode ser aplicado. Nada foi alterado.",
            false, {"Modo de validação: nenhuma timeline foi criada."})
    end

    -- ---------------------------------------------------------------- mutations
    local target_name = M.unique_timeline_name(runtime.project, plan.target and plan.target.timeline_name)
    local duplicate = M.call_method(original, "DuplicateTimeline", target_name)
    if duplicate == nil then
        check("duplicate_timeline", "FAILED", "DuplicateTimeline não retornou timeline")
        return outcome("FAILED", "O Resolve não criou a cópia da timeline. Nada foi alterado.", false)
    end
    local duplicate_id = tostring((M.call_method(duplicate, "GetUniqueId")) or "")
    if duplicate_id == "" or duplicate_id == original_id
            or M.call_method(duplicate, "GetName") ~= target_name then
        check("duplicate_timeline", "FAILED", "identidade da cópia não confirmada")
        return outcome("FAILED", "A cópia da timeline não pôde ser confirmada. A original não foi alterada.", true)
    end
    details.created_timeline = target_name
    details.created_timeline_id = duplicate_id
    check("duplicate_timeline", "PASSED", target_name)

    local function fail(message)
        M.call_method(duplicate, "SetName", target_name .. "_FALHOU")
        details.created_timeline = target_name .. "_FALHOU"
        local original_problems = M.verify_source_layout(original, source)
        details.original_verified_after = #original_problems == 0
        check("original_intact", details.original_verified_after and "PASSED" or "FAILED",
            details.original_verified_after and "original conferida após a falha" or table.concat(original_problems, "; "))
        local active = M.call_method(runtime.project, "GetCurrentTimeline")
        if tostring(M.call_method(active, "GetUniqueId")) == duplicate_id then
            details.original_reactivated = M.call_method(runtime.project, "SetCurrentTimeline", original) == true
        end
        check("result", "FAILED", message)
        local preserved = details.original_verified_after and " A timeline original foi conferida e permanece intacta; "
            or " A timeline original apresentou diferenças na conferência; "
        return outcome("FAILED", message .. preserved .. "a cópia incompleta foi mantida como "
            .. target_name .. "_FALHOU para inspeção.", true)
    end
    local function guard_target()
        local current = M.call_method(runtime.project, "GetCurrentTimeline")
        local current_id = current and tostring((M.call_method(current, "GetUniqueId")) or "") or ""
        return current_id == duplicate_id and current_id ~= original_id
    end

    if M.call_method(runtime.project, "SetCurrentTimeline", duplicate) ~= true or not guard_target() then
        return fail("Não foi possível ativar a cópia da timeline com segurança.")
    end
    check("activate_copy", "PASSED", duplicate_id)

    local existing = {}
    for _, entry in ipairs(collect_items(duplicate)) do
        existing[#existing + 1] = entry.item
    end
    if #existing > 0 then
        if not guard_target() then
            return fail("A timeline ativa mudou antes da limpeza da cópia.")
        end
        if M.call_method(duplicate, "DeleteClips", existing, false) ~= true then
            return fail("A limpeza da cópia falhou.")
        end
    end
    if #collect_items(duplicate) ~= 0 then
        return fail("A cópia não ficou vazia após a limpeza.")
    end
    check("clear_copy", "PASSED", tostring(#existing) .. " itens removidos da cópia")
    M.call_method(duplicate, "DeleteMarkersByColor", "All")

    local start_frame = tonumber(source.start_frame) or 0
    local end_inclusive = nil
    local record_relative = nil
    local counters = {properties = 0, property_failures = 0, channel_mappings = 0,
        channel_mapping_failures = 0, extras_removed = 0, source_frame_rounding = 0, native_audio_reused = 0}
    local link_groups = {}
    local staged_native = {}
    local future_audio = {}
    local function operation_key(op)
        return table.concat({tostring(op.media_pool_item_id), tostring(op.track_index),
            tostring(op.source_start), tostring(op.source_end),
            tostring(op.record_start), tostring(op.record_end)}, "|")
    end
    for position, op in ipairs(operations) do
        if op.media_type == 2 then
            future_audio[operation_key(op)] = {op = op, position = position}
        end
    end

    local function append(op, inclusive, relative, position)
        local info = {
            mediaPoolItem = media_items[tostring(op.source_item_id)].mpi,
            startFrame = op.source_start,
            endFrame = inclusive and (op.source_end - 1) or op.source_end,
            mediaType = op.media_type,
            trackIndex = op.track_index,
            recordFrame = relative and (op.record_start - start_frame) or op.record_start,
        }
        -- Resolve can return only the first item while inserting several linked
        -- audio items. Read the copy before/after; never trust the returned list.
        local before = {}
        for _, entry in ipairs(collect_items(duplicate)) do
            local id = M.call_method(entry.item, "GetUniqueId")
            if id ~= nil then before[tostring(id)] = true end
        end
        M.call_method(media_pool, "AppendToTimeline", {info})
        local target, extras, created = nil, {}, {}
        for _, entry in ipairs(collect_items(duplicate)) do
            local id = M.call_method(entry.item, "GetUniqueId")
            if id ~= nil and not before[tostring(id)] then
                created[#created + 1] = entry.item
                if target == nil and entry.track_type == op.track_type
                        and entry.track_index == op.track_index then
                    target = entry.item
                else
                    -- Native siblings contain distinct source streams. Reuse them
                    -- before any setter can make metadata mask a wrong source.
                    local candidate = nil
                    if op.media_type == 2 and entry.track_type == "audio" then
                        local key_op = {media_pool_item_id = op.media_pool_item_id,
                            track_index = entry.track_index, source_start = op.source_start,
                            source_end = op.source_end, record_start = op.record_start,
                            record_end = op.record_end}
                        candidate = future_audio[operation_key(key_op)]
                    end
                    local native_mapping = audio_mapping_key(entry.item)
                    local mpi = M.call_method(entry.item, "GetMediaPoolItem")
                    local expected = candidate and media_items[tostring(candidate.op.source_item_id)].original
                    if candidate and candidate.position > position
                            and staged_native[candidate.op.op_id] == nil
                            and native_mapping ~= nil and native_mapping == audio_mapping_key(expected)
                            and tostring(M.call_method(mpi, "GetUniqueId")) == tostring(op.media_pool_item_id)
                            and tonumber((M.call_method(entry.item, "GetStart", false))) == candidate.op.record_start
                            and tonumber((M.call_method(entry.item, "GetEnd", false))) == candidate.op.record_end
                            and tonumber((M.call_method(entry.item, "GetLeftOffset", false))) == candidate.op.source_start then
                        staged_native[candidate.op.op_id] = entry.item
                        log("native audio staged " .. tostring(candidate.op.op_id) .. ": track="
                            .. tostring(entry.track_index) .. "; item=" .. tostring(id)
                            .. "; mapping=" .. native_mapping)
                    else
                        extras[#extras + 1] = entry.item
                    end
                end
            end
        end
        return target, extras, created
    end

    local function measure(item)
        local item_start = tonumber((M.call_method(item, "GetStart", false)))
        local item_end = tonumber((M.call_method(item, "GetEnd", false)))
        local source_start = tonumber((M.call_method(item, "GetSourceStartFrame")))
        return item_start, item_end, source_start
    end

    for position, op in ipairs(operations) do
        if not guard_target() then
            return fail("A timeline ativa mudou durante a reconstrução.")
        end
        local target, extras, created
        local expected_length = op.source_end - op.source_start
        if staged_native[op.op_id] ~= nil then
            target, extras, created = staged_native[op.op_id], {}, {}
            staged_native[op.op_id] = nil
            counters.native_audio_reused = counters.native_audio_reused + 1
        elseif end_inclusive == nil then
            local attempts = {{false, false}, {true, false}, {false, true}, {true, true}}
            for _, attempt in ipairs(attempts) do
                target, extras, created = append(op, attempt[1], attempt[2], position)
                if target ~= nil then
                    local item_start, item_end = measure(target)
                    if item_start == op.record_start and item_end ~= nil
                            and item_end - item_start == expected_length then
                        end_inclusive, record_relative = attempt[1], attempt[2]
                        break
                    end
                end
                if #created > 0 then
                    M.call_method(duplicate, "DeleteClips", created, false)
                end
                staged_native = {}
                target = nil
            end
            if end_inclusive == nil then
                return fail("Não foi possível calibrar AppendToTimeline (posição/duração divergentes).")
            end
            details.calibration = {end_frame_inclusive = end_inclusive, record_frame_relative = record_relative}
            check("append_calibration", "PASSED", "endFrame inclusivo=" .. tostring(end_inclusive)
                .. "; recordFrame relativo=" .. tostring(record_relative))
        else
            target, extras, created = append(op, end_inclusive, record_relative, position)
        end
        if #extras > 0 then
            if not guard_target() then
                return fail("A timeline ativa mudou antes de remover itens adicionais.")
            end
            if M.call_method(duplicate, "SetClipsLinked", created, false) ~= true then
                return fail("Não foi possível desvincular os itens adicionais da cópia.")
            end
            if M.call_method(duplicate, "DeleteClips", extras, false) ~= true then
                return fail("Não foi possível remover os itens adicionais da cópia.")
            end
            counters.extras_removed = counters.extras_removed + #extras
        end
        if target == nil then
            return fail("A operação " .. tostring(op.op_id) .. " não criou item na faixa esperada.")
        end
        local item_start, item_end, source_start = measure(target)
        if item_start ~= op.record_start or item_end ~= op.record_end then
            return fail("A operação " .. tostring(op.op_id) .. " ficou em posição diferente da planejada ("
                .. tostring(item_start) .. "-" .. tostring(item_end) .. " em vez de "
                .. tostring(op.record_start) .. "-" .. tostring(op.record_end) .. ").")
        end
        if source_start ~= nil and source_start ~= op.source_start then
            -- Some 23.976 sources truncate this getter by one frame. Accept it
            -- only when BOTH independent readings prove the requested in-point.
            local left = tonumber((M.call_method(target, "GetLeftOffset", false)))
            local seconds = tonumber((M.call_method(target, "GetSourceStartTime")))
            local media_fps = tonumber((M.call_method(
                media_items[tostring(op.source_item_id)].mpi, "GetClipProperty", "FPS")))
            local consistent = math.abs(source_start - op.source_start) <= 1
                and left == op.source_start and seconds ~= nil and media_fps ~= nil
                and math.abs(media_fps - tonumber(source.fps)) < 0.001
                and source_time_matches(seconds, op.source_start, media_fps)
            if not consistent then
                return fail("A operação " .. tostring(op.op_id) .. " usou um trecho de origem diferente do planejado.")
            end
            counters.source_frame_rounding = counters.source_frame_rounding + 1
            log("source frame rounding " .. tostring(op.op_id) .. ": getter="
                .. tostring(source_start) .. "; offset=" .. tostring(left)
                .. "; seconds=" .. tostring(seconds))
        end
        copy_item_attributes(media_items[tostring(op.source_item_id)].original, target, op, counters)
        if M.call_method(target, "GetClipEnabled") ~= (op.enabled ~= false) then
            return fail("A operação " .. tostring(op.op_id) .. " não confirmou o estado ativo/desativado do clipe.")
        end
        counters.clip_states_verified = (counters.clip_states_verified or 0) + 1
        if type(op.link_group) == "string" then
            link_groups[op.link_group] = link_groups[op.link_group] or {}
            local group = link_groups[op.link_group]
            group[#group + 1] = target
        end
        details.operations_applied = position
        if position % 50 == 0 then
            log("progress " .. tostring(position) .. "/" .. tostring(#operations))
        end
    end
    check("operations", "PASSED", tostring(details.operations_applied) .. " itens criados e conferidos")

    local linked = 0
    for _, items in pairs(link_groups) do
        if #items >= 2 and M.call_method(duplicate, "SetClipsLinked", items, true) == true then
            linked = linked + 1
        end
    end

    local markers_moved, markers_dropped = 0, 0
    local markers = M.call_method(original, "GetMarkers")
    if type(markers) == "table" then
        for frame, marker in pairs(markers) do
            local absolute = start_frame + (tonumber(frame) or -1)
            local placed = false
            for _, keep in ipairs(plan.keep_ranges or {}) do
                if absolute >= keep.source_start and absolute < keep.source_end then
                    local new_frame = keep.record_start + (absolute - keep.source_start) - start_frame
                    if M.call_method(duplicate, "AddMarker", new_frame, marker.color or "Blue",
                            marker.name or "", marker.note or "", marker.duration or 1,
                            marker.customData or "") == true then
                        placed = true
                    end
                    break
                end
            end
            if placed then markers_moved = markers_moved + 1 else markers_dropped = markers_dropped + 1 end
        end
    end

    local final_items = #collect_items(duplicate)
    if final_items ~= #operations then
        return fail("A cópia contém " .. tostring(final_items) .. " itens, mas eram esperados "
            .. tostring(#operations) .. ".")
    end
    local after_problems = M.verify_source_layout(original, source)
    details.original_verified_after = #after_problems == 0
    if #after_problems > 0 then
        check("original_intact", "FAILED", table.concat(after_problems, "; "))
        return fail("A verificação final da timeline original encontrou diferenças.")
    end
    check("original_intact", "PASSED", "timeline original conferida após a aplicação")
    details.counters = counters
    details.linked_groups = linked
    details.markers_moved = markers_moved
    details.markers_dropped = markers_dropped
    if counters.property_failures > 0 then
        details.warnings[#details.warnings + 1] = tostring(counters.property_failures)
            .. " propriedade(s) de clipe não puderam ser copiadas."
    end
    if counters.channel_mapping_failures > 0 then
        details.warnings[#details.warnings + 1] = tostring(counters.channel_mapping_failures)
            .. " mapeamento(s) de canais de áudio não puderam ser copiados; confira os canais."
    end
    if counters.extras_removed > 0 then
        details.warnings[#details.warnings + 1] = tostring(counters.extras_removed)
            .. " item(ns) extra(s) criados automaticamente pelo Resolve foram removidos da nova timeline."
    end
    return outcome("SUCCESS", "Rough cut criado em " .. target_name .. " com "
        .. tostring(#operations) .. " itens conferidos. A timeline original permanece intacta.", true, {
            "Nova timeline: " .. target_name,
            "Itens criados e conferidos: " .. tostring(#operations),
            "Grupos vinculados: " .. tostring(linked),
            "Marcadores reposicionados: " .. tostring(markers_moved) .. "; descartados: " .. tostring(markers_dropped),
            "Grades de cor, composições Fusion e transições não são copiadas; confira a nova timeline.",
        })
end

-- Auxiliary commands live outside the Resolve menu tree. A request is consumed
-- before dispatch and must match the exact freshly approved/validated plan.
function M.dispatch_menu_action(base, expected_plan_id, expected_mode, on_started)
    local request_path = base .. "/plans/menu-action.json"
    if not M.file_exists(request_path) then return false end
    local request = M.read_json(request_path)
    if type(request) ~= "table" or request.schema_version ~= 1
        or type(request.request_id) ~= "string" or #request.request_id ~= 32
        or not request.request_id:match("^[0-9a-f]+$") then
        error("Solicitação do menu inválida; nenhuma operação executada.")
    end
    if expected_plan_id ~= nil and (request.plan_id ~= expected_plan_id or request.mode ~= expected_mode) then
        error("A solicitação atual pertence a outro plano ou modo; nada foi consumido.")
    end
    local consumed = base .. "/plans/menu-action-" .. request.request_id .. ".consumed.json"
    if not os.rename(request_path, consumed) then
        error("Não foi possível consumir a solicitação do menu; nenhuma operação executada.")
    end
    local created = iso_to_epoch(request.created_at)
    local age = created and (utc_now_epoch() - created) or nil
    if not age or age < -60 or age > 300 then
        print("O EDITOR: solicitação expirada; abrindo somente a interface.")
        return false
    end
    if request.action ~= "rough_cut" then
        error("Ação do menu não permitida.")
    end
    local plan = M.read_json(base .. "/plans/rough-cut-pending.json")
    if type(plan) ~= "table" or plan.plan_id ~= request.plan_id
        or plan.mode ~= request.mode
        or (request.mode ~= "VALIDATE" and request.mode ~= "APPLY")
        or (request.mode == "APPLY" and plan.confirmed_by_user ~= true) then
        error("A solicitação não corresponde ao plano confirmado; nenhuma operação executada.")
    end
    if on_started ~= nil then on_started() end
    dofile(base .. "/internal-scripts/O Editor - Aplicar Rough Cut.lua")
    return true
end

return M
