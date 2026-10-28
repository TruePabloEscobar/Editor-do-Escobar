-- EDE Bridge. Start only from Workspace > Scripts, never Fusion.Execute/scriptlib.
-- The mailbox is DATA. No externally supplied chunk is ever executed.
-- @@CORE@@
local B = {protocol = 1}
local PREFIX = "Global.EDEBridge."
local MAILBOX = "@@MAILBOX@@"
local MAX_HEX = 2097152
local token = tostring(os.time()) .. tostring({}):gsub("[^%w]", "")
local last_id, owner, stopped = nil, nil, false
local seen, seen_order = {}, {}
local playhead_supported = false
local capabilities = {
    DuplicateTimeline = "UNVERIFIED", SetCurrentTimeline = "UNVERIFIED",
    DeleteClips = "UNVERIFIED", AppendToTimeline = "UNVERIFIED",
    SetProperty = "UNVERIFIED", SetProperties = "UNVERIFIED",
    markers = "UNVERIFIED", playhead = "UNVERIFIED", capture = "UNVERIFIED",
}

local function hex(text)
    return (text:gsub(".", function(c) return string.format("%02x", string.byte(c)) end))
end
local function unhex(text)
    return (text:gsub("..", function(pair) return string.char(tonumber(pair, 16)) end))
end
local function valid_id(id)
    return type(id) == "string" and #id == 32 and id:match("^[0-9a-f]+$") ~= nil
end
local function resolve_host()
    local r = M.get_internal_resolve(nil)
    if not r then error("Resolve interno indisponível.") end
    return r
end
local function fusion_host()
    return rawget(_G, "fusion") or rawget(_G, "fu") or resolve_host():Fusion()
end

-- Compile for inspection only. Match the ENTIRE compiler output to a trusted
-- literal compiled with the same source name. Extract the hex constant as data.
-- Empty environments alone do not stop loops or arbitrary bytecode; never call chunk.
function B.read_request(path)
    local ok, chunk = pcall(loadfile, path, "t")
    if not ok or type(chunk) ~= "function" then return nil end
    local dumped = string.dump(chunk, true)
    local data = dumped:match("EDE1_([0-9a-f]+)_END")
    if not data or #data > MAX_HEX or #data % 2 ~= 0 then return nil end
    local literal = 'return "EDE1_' .. data .. '_END"'
    local expected = loadstring(literal, "@" .. path)
    if not expected or string.dump(expected, true) ~= dumped then return nil end
    local decoded, result = pcall(M.json_decode, unhex(data))
    if not decoded or type(result) ~= "table" then return nil end
    return result
end

local function version_supported(version)
    local major, minor = tostring(version):match("^(%d+)%.(%d+)")
    return major and (tonumber(major) > 21 or (tonumber(major) == 21 and tonumber(minor) >= 1))
end
local function identity(context)
    return {project_name=context.project_name, timeline_id=context.timeline_id,
        timeline_name=context.timeline_name, fps=context.fps,
        start_frame=context.start_frame, end_frame=context.end_frame}
end
local function capture()
    local context, r, manager, project, timeline = M.capture_context(nil, {capture_layout=true})
    local active = manager:GetCurrentProject()
    local current = active and active:GetCurrentTimeline()
    if not current or current:GetUniqueId() ~= context.timeline_id
            or active:GetName() ~= context.project_name then
        error("A timeline ativa mudou durante a captura. Atualize novamente.")
    end
    if not version_supported(context.resolve_version) then error("Incompatível: Resolve 21.1 ou superior necessário.") end
    capabilities.capture = "SUPPORTED"
    context.integration_mode = "internal_resolve_host"
    context.bridge_transport = "lua_mailbox"
    context.bridge_session = token
    if context.product_name ~= "DaVinci Resolve" and context.product_name ~= "DaVinci Resolve Studio" then
        error("Incompatível: edição do Resolve não identificada.")
    end
    context.edition = context.product_name:find("Studio") and "Studio" or "Free"
    context.capabilities = capabilities
    return context, r, project, timeline
end
local function same_context(expected, current)
    if type(expected) ~= "table" then return false end
    for key, value in pairs(identity(current)) do
        if expected[key] ~= value then return false end
    end
    return true
end

function B.dispatch(req)
    if req.protocol ~= 1 or not valid_id(req.id) or not valid_id(req.client_session)
            or type(req.expires_at) ~= "number" or req.expires_at < os.time()
            or req.expires_at > os.time() + 35 then error("Pedido inválido ou expirado.") end
    if req.command ~= "hello" and req.bridge_session ~= token then error("Sessão do Bridge mudou. Atualize a timeline.") end
    local args = req.arguments
    if type(args) ~= "table" then error("Argumentos inválidos.") end
    if req.command == "hello" then
        local r = resolve_host()
        if not version_supported(r:GetVersionString()) then error("Incompatível: Resolve 21.1 ou superior necessário.") end
        return {bridge_session=token, protocol=1, resolve_version=r:GetVersionString(),
            product_name=r:GetProductName(), capabilities=capabilities}
    elseif req.command == "stop" then
        stopped = true
        return {stopped=true}
    elseif req.command == "capture" then
        return (capture())
    elseif req.command == "capabilities" then
        return {capabilities=capabilities, write_enabled=false,
            reason="Escritas no Free NÃO VALIDADAS em instalação real; bloqueadas por segurança."}
    elseif req.command == "probe_playhead" or req.command == "set_playhead" then
        local context, _, _, timeline = capture()
        if not same_context(args.context, context) then error("A timeline ativa mudou. Atualize novamente.") end
        local tc = timeline:GetCurrentTimecode()
        if type(tc) ~= "string" then error("Timecode não disponível.") end
        if req.command == "probe_playhead" then
            playhead_supported = timeline:SetCurrentTimecode(tc) == true and timeline:GetCurrentTimecode() == tc
            capabilities.playhead = playhead_supported and "SUPPORTED" or "FAILED"
            return {supported=playhead_supported, timecode=tc}
        end
        if not playhead_supported then error("Posicionamento do playhead não validado nesta sessão.") end
        if type(args.timecode) ~= "string" or not args.timecode:match("^%d%d:%d%d:%d%d[:;]%d%d$") then
            error("Timecode inválido.")
        end
        if timeline:SetCurrentTimecode(args.timecode) ~= true or timeline:GetCurrentTimecode() ~= args.timecode then
            error("O Resolve não confirmou o posicionamento do playhead.")
        end
        return {verified=true, timecode=args.timecode}
    elseif req.command == "validate_rough_cut" then
        local context, r, project, timeline = capture()
        if not same_context(args.context, context) then error("A timeline ativa mudou. Atualize novamente.") end
        local plan = args.plan
        if type(plan) ~= "table" or plan.mode ~= "VALIDATE" or plan.confirmed_by_user ~= false
                or not valid_id(plan.plan_id) then error("Somente validação sem alterações é permitida.") end
        local result = M.apply_rough_cut({context=context, resolve=r, project=project, timeline=timeline}, plan)
        if result.status == "SUCCESS" then
            result.message = "Validação do plano concluída, sem alterações. Aplicação no Free continua bloqueada até validação física."
        end
        return result
    elseif req.command == "apply_rough_cut" or req.command == "apply_take_zoom" then
        error("Escritas no Free NÃO VALIDADAS em instalação real; Rough Cut e Zoom bloqueados. A prévia continua disponível.")
    end
    error("Comando não permitido pelo EDE Bridge.")
end

function B.tick()
    if stopped then return false end
    local path = MAILBOX .. "/request.lua"
    if not bmd.fileexists(path) then return true end
    local req = B.read_request(path)
    if not req or not valid_id(req.id) or seen[req.id] then return true end
    if owner:GetPrefs(PREFIX .. "Owner") ~= token then return false end
    seen[req.id] = true; seen_order[#seen_order + 1] = req.id
    if #seen_order > 256 then seen[table.remove(seen_order, 1)] = nil end
    last_id = req.id
    local ok, result = pcall(B.dispatch, req)
    local response = {protocol=1, id=req.id, client_session=req.client_session,
        bridge_session=token, ok=ok, result=ok and result or JSON_NULL,
        error=not ok and tostring(result) or JSON_NULL}
    local encoded = M.json_encode(response)
    if #encoded > 1048576 then
        encoded = M.json_encode({protocol=1, id=req.id, client_session=req.client_session,
            bridge_session=token, ok=false, error="Resposta excede o limite de 1 MiB. Reduza a timeline de teste."})
    end
    owner:SetPrefs(PREFIX .. "EDEResponse", req.id .. ":" .. hex(encoded))
    if owner:SavePrefs() == false then error("Não foi possível salvar a resposta do Bridge.") end
    return not stopped
end
function B.claim()
    owner = fusion_host()
    if not owner or type(owner.SetPrefs) ~= "function" or type(loadfile) ~= "function"
            or type(loadstring) ~= "function" or type(string.dump) ~= "function"
            or not bmd or type(bmd.wait) ~= "function" or type(bmd.fileexists) ~= "function" then
        error("Sandbox incompatível: compilador de dados, Fusion prefs ou espera indisponível.")
    end
    -- Takeover only on a manual menu invocation. Old owner exits before next command.
    owner:SetPrefs(PREFIX .. "Owner", token)
end
function B.start()
    B.claim()
    while true do
        bmd.wait(0.25)
        local ok, keep = pcall(B.tick)
        if not ok then print("EDE Bridge encerrado: " .. tostring(keep)); return end
        if not keep then return end
    end
    -- Do not call Fusion prefs on Resolve shutdown.
end
B.core = M
B.session = token
if ... == "EDE_BRIDGE_TEST" then return B end
B.start()
