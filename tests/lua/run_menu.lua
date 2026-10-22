local common_path, base = arg[1], arg[2]
local common = dofile(common_path)
local dispatched = ""
_G.dofile = function(path) dispatched = path end
common.run_take_zoom_action = function(_base, plan_path) dispatched = "take_zoom:" .. plan_path end
local ok, handled = pcall(common.dispatch_menu_action, base)
io.write(common.json_encode({ok = ok, handled = ok and handled or false,
    error = not ok and tostring(handled) or "", dispatched = dispatched}))
