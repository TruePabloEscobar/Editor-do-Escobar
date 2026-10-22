-- Usage: lua5.1 run_open_startup.lua <launcher_dir> <tests_lua_dir> <runs>
-- Runs the real "O EDITOR.lua" menu script against a fake Resolve and an
-- in-memory Windows filesystem, counting every process spawned via os.execute.
-- Writing a file whose directory does not exist fails, exactly like on Windows.
local launcher_dir, tests_dir, runs = arg[1], arg[2], tonumber(arg[3]) or 2
local real_open, real_dofile = io.open, dofile
-- Reproduce allocator address reuse within the same second deterministically.
local real_tostring = tostring
tostring = function(value)
    if type(value) == "table" then return "table: 0x1234" end
    return real_tostring(value)
end
os.time = function() return 1700000000 end
local APPDATA = "C:\\Users\\Teste\\AppData\\Roaming"
local BASE = APPDATA .. "\\O Editor"

local directories = {["C:"] = true, ["C:\\Users"] = true, ["C:\\Users\\Teste"] = true,
    ["C:\\Users\\Teste\\AppData"] = true, [APPDATA] = true, [BASE] = true}
local files = {[BASE .. "\\launch-editor.cmd"] = "@echo off"}

local function parent(path)
    return path:match("^(.*)\\[^\\]+$")
end

local function fake_handle(path, mode)
    local buffer = {}
    if mode:sub(1, 1) == "a" and files[path] then buffer[1] = files[path] end
    local handle = {}
    function handle:write(...)
        for index = 1, select("#", ...) do buffer[#buffer + 1] = tostring((select(index, ...))) end
        return self
    end
    function handle:read(_format) return files[path] end
    function handle:close()
        if mode:sub(1, 1) ~= "r" then files[path] = table.concat(buffer) end
        return true
    end
    return handle
end

io.open = function(path, mode)
    mode = mode or "r"
    path = tostring(path)
    if not path:find("^C:") then return real_open(path, mode) end
    if mode:sub(1, 1) == "r" then
        if files[path] == nil then return nil, path .. ": No such file or directory" end
        return fake_handle(path, mode)
    end
    if not directories[parent(path) or ""] then
        return nil, path .. ": No such file or directory"
    end
    return fake_handle(path, mode)
end

local spawned = {}
os.execute = function(command)
    spawned[#spawned + 1] = command
    for target in command:gmatch('mkdir "([^"]+)"') do
        local current = target
        local chain = {}
        while current and not directories[current] do
            chain[#chain + 1] = current
            current = parent(current)
        end
        for _, item in ipairs(chain) do directories[item] = true end
    end
    return 0
end
os.getenv = function(name)
    if name == "APPDATA" then return APPDATA end
    if name == "TEMP" or name == "TMP" then return "C:\\Users\\Teste\\AppData\\Local\\Temp" end
    return nil
end
dofile = function(path)
    path = tostring(path)
    if path:find("internal_common.lua$") then
        return real_dofile(launcher_dir .. "/internal_common.lua")
    end
    return real_dofile(path)
end

local F = real_dofile(tests_dir .. "/fake_resolve.lua")
resolve = F.podcast_fixture({})
print = function(...) end

local results = {}
for run = 1, runs do
    local before = #spawned
    real_dofile(launcher_dir .. "/O EDITOR.lua")
    local commands = {}
    for index = before + 1, #spawned do commands[#commands + 1] = spawned[index] end
    local launched = 0
    for _, command in ipairs(commands) do
        if command:find("launch-editor.cmd", 1, true) then launched = launched + 1 end
    end
    local requests = 0
    for path, _ in pairs(files) do
        if path:find("\\requests\\request-", 1, true) then requests = requests + 1 end
    end
    results[run] = {spawned = #commands, launched = launched, requests = requests,
        commands = commands}
end
local common = real_dofile(launcher_dir .. "/internal_common.lua")
local log = files[BASE .. "\\logs\\internal-open.log"] or ""
io.write(common.json_encode({runs = results, open_log_lines = select(2, log:gsub("\n", ""))}))
