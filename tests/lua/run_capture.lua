-- Usage: lua5.1 run_capture.lua <launcher_dir> <tests_lua_dir>
local launcher_dir, tests_dir = arg[1], arg[2]
local common = dofile(launcher_dir .. "/internal_common.lua")
local F = dofile(tests_dir .. "/fake_resolve.lua")
local resolve_object = F.podcast_fixture({})
resolve = resolve_object
local context = common.capture_context(nil, {capture_layout = true})
io.write(common.json_encode(context))
