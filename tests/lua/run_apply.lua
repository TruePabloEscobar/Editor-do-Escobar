-- Usage: lua5.1 run_apply.lua <launcher_dir> <tests_lua_dir> <plan.json> <options.json>
local launcher_dir, tests_dir, plan_path, options_path = arg[1], arg[2], arg[3], arg[4]
local common = dofile(launcher_dir .. "/internal_common.lua")
local F = dofile(tests_dir .. "/fake_resolve.lua")
local options = common.read_json(options_path)
local resolve_object, project, original = F.podcast_fixture(options)
resolve = resolve_object
if options.capture_only then
    local context = common.capture_context(nil, {capture_layout = true})
    io.write(common.json_encode(context))
    return
end
local context, _r, _pm, live_project, timeline = common.capture_context(nil, {capture_layout = false})
local runtime = {context = context, project = live_project, timeline = timeline, log_path = nil}
if options.tamper then
    original.tracks.audio[2].items[1].start = original.tracks.audio[2].items[1].start + 5
end
if options.slip_source then
    local item = original.tracks.audio[2].items[1]
    item.src_start = item.src_start + 50
    item.src_end = item.src_end + 50
end
if options.reroute_source then
    original.tracks.audio[2].items[1].mapping = '{"track_mapping":{"1":{"channel_idx":[7],"mute":false,"type":"mono"}}}'
end
local plan = common.read_json(plan_path)
local logs = {}
local result = common.apply_rough_cut(runtime, plan, function(message) logs[#logs + 1] = message end)

local function dump_timeline(tl)
    local items = {}
    for _, track_type in ipairs({"video", "audio", "subtitle"}) do
        for index, track in ipairs(tl.tracks[track_type]) do
            for _, item in ipairs(track.items) do
                items[#items + 1] = {
                    track_type = track_type, track_index = index, name = item.name,
                    start = item.start, finish = item.finish, src_start = item.src_start,
                    src_end = item.src_end, media = item.mpi and item.mpi.id or "",
                    mapping = item.mapping or "", enabled = item.enabled,
                    effective_stream = item.effective_stream,
                    link_group = item.link_group or "", props = item.props or {},
                }
            end
        end
    end
    local markers = {}
    for frame, marker in pairs(tl.markers) do markers[#markers + 1] = {frame = frame, name = marker.name} end
    return {name = tl.name, id = tl.id, items = items, mutation_log = tl.mutation_log, markers = markers}
end

local timelines = {}
for _, tl in ipairs(project.timelines) do timelines[#timelines + 1] = dump_timeline(tl) end
io.write(common.json_encode({
    result = {status = result.status, message = result.message, mutations = result.mutations_executed,
        details = result.details},
    timelines = timelines,
    current = project.current.name,
    logs = logs,
}))
