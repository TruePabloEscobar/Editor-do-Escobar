-- Usage: lua5.1 run_take_zoom_action.lua <launcher_dir> <base> <mutated:true|false>
-- Exercises the receipt/archive wrapper around apply_take_zoom with the engine stubbed.
local launcher_dir, base, mutated = arg[1], arg[2], arg[3] == "true"
local common = dofile(launcher_dir .. "/internal_common.lua")
local applied = 0
common.apply_take_zoom = function(_runtime, plan, _log)
    applied = applied + 1
    return {status = mutated and "SUCCESS" or "BLOCKED", message = "stub",
        mutations_executed = mutated, details = {warnings = {}, timeline_id = "tl-copy",
        purpose = plan.purpose}}
end
local captured = {}
common.run_internal_action = function(action_name, action_function, options)
    local result = action_function({log_path = nil})
    captured = {action = action_name, log_name = options.log_name, status = result.status,
        message = result.message}
    return result.status
end
common.run_take_zoom_action(base, base .. "/plans/take-zoom-pending.json")
captured.applied = applied
io.write(common.json_encode(captured))
