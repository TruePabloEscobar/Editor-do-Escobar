-- Usage: lua5.1 run_take_zoom.lua <launcher_dir> <tests_lua_dir> <options.json> [plan.json]
-- Fake project with the original timeline and a copy created by O Editor.
-- Without a plan it prints the captured context (layout) of the active timeline.
local launcher_dir, tests_dir, options_path, plan_path = arg[1], arg[2], arg[3], arg[4]
local common = dofile(launcher_dir .. "/internal_common.lua")
local F = dofile(tests_dir .. "/fake_resolve.lua")
local options = common.read_json(options_path)

local project = F.new_project("Podcast", {})
local camera = F.new_media({id = "mpi-cam", name = "cam.mov", frames = 200000})
local cam_b = F.new_media({id = "mpi-camb", name = "camb.mov", frames = 200000})
local mic = F.new_media({id = "mpi-mic", name = "mic.wav", frames = 200000})
local original = F.add_timeline(project, F.new_timeline({name = "Episodio 1", id = "tl-original",
    fps = 24, start_frame = 86400, start_tc = "01:00:00:00"}))
original:add_track("video", "Camera")
original:add_item("video", 1, {id = "orig-v1", start = 86400, finish = 86700, mpi = camera,
    props = {ZoomX = 1.1, ZoomY = 1.1, AnchorPointX = 0.0, AnchorPointY = 0.0}})
local copy = F.add_timeline(project, F.new_timeline({
    name = options.copy_name or "Episodio 1_OE_ROUGHCUT_001", id = "tl-copy",
    fps = 24, start_frame = 86400, start_tc = "01:00:00:00"}))
copy:add_track("video", "Camera")
copy:add_track("video", "Cam B")
copy:add_track("audio", "Pablo", "mono")
local base_props = {ZoomX = 1.1, ZoomY = 1.1, AnchorPointX = 0.0, AnchorPointY = 0.0}
copy:add_item("video", 1, {id = "c-v1-1", start = 86400, finish = 86500, mpi = camera, props = base_props})
copy:add_item("video", 1, {id = "c-v1-2", start = 86500, finish = 86650, mpi = camera, props = base_props})
copy:add_item("video", 1, {id = "c-v1-3", start = 86650, finish = 86700, mpi = camera, props = base_props})
copy:add_item("video", 2, {id = "c-v2-1", start = 86400, finish = 86700, mpi = cam_b})
copy:add_item("audio", 1, {id = "c-a1-1", start = 86400, finish = 86700, mpi = mic,
    props = {AudioVolume = -3.0}})
project.current = options.current == "original" and original or copy

local by_id = {}
for _, tl in ipairs(project.timelines) do
    for _, track_type in ipairs({"video", "audio"}) do
        for _, track in ipairs(tl.tracks[track_type]) do
            for _, item in ipairs(track.items) do by_id[item.id] = item end
        end
    end
end
for id, props in pairs(options.props or {}) do
    by_id[id].props = {}
    for key, value in pairs(props) do by_id[id].props[key] = value end
end
if options.move_item then
    by_id[options.move_item].start = by_id[options.move_item].start + 1
end

-- Fault injection on the shared TimelineItem class.
local item_class = getmetatable(by_id["c-v1-1"])
local original_set = item_class.SetProperties
local calls = 0
item_class.SetProperties = function(self, values)
    calls = calls + 1
    if options.switch_after_calls and calls > options.switch_after_calls then
        project.current = original
    end
    if options.ignore_item == self.id and calls <= (options.ignore_calls or 1) then
        return true
    end
    return original_set(self, values)
end

resolve = F.new_resolve(project)
if not plan_path or plan_path == "" then
    local context = common.capture_context(nil, {capture_layout = true})
    io.write(common.json_encode(context))
    return
end
local context, _r, _pm, live_project, timeline = common.capture_context(nil, {capture_layout = false})
local runtime = {context = context, project = live_project, timeline = timeline, log_path = nil}
local plan = common.read_json(plan_path)
local logs = {}
local result = common.apply_take_zoom(runtime, plan, function(message) logs[#logs + 1] = message end)

local function dump(tl)
    local items = {}
    for _, track_type in ipairs({"video", "audio"}) do
        for _, track in ipairs(tl.tracks[track_type]) do
            for _, item in ipairs(track.items) do
                items[item.id] = item.props or {}
            end
        end
    end
    return {name = tl.name, id = tl.id, props = items, mutation_log = tl.mutation_log}
end
io.write(common.json_encode({
    result = {status = result.status, message = result.message,
        mutations = result.mutations_executed, details = result.details},
    original = dump(original),
    copy = dump(copy),
    logs = logs,
}))
