-- Read-only Workflow Integration bootstrap. Reuse the current application protocol.
-- Deliberately does not call dispatch_menu_action: startup cannot apply a plan.
return function(receipt_path, launch_id)
    local base = assert(os.getenv("APPDATA"), "APPDATA indisponível") .. "/O Editor"
    local common = dofile(base .. "/internal_common.lua")
    local status, request_path, launched, launch_error = common.run_internal_action(
        "open", function(runtime)
            if not runtime.context then
                error(runtime.context_error or "Abra um projeto e uma timeline no Resolve.")
            end
            return {
                status = "SUCCESS",
                message = "EDE iniciado pela integração de fluxo do DaVinci Resolve.",
                details = {integration_entry = "workflow_integration"},
            }
        end, {
            capture_layout = true,
            log_name = "workflow-open",
            script_path = common.script_path(2),
            script_version = "0.2.0",
            build_hash = "workflow-integration-20261027",
        }
    )
    common.write_json(receipt_path .. ".tmp", {
        schema_version = 1,
        launch_id = launch_id,
        launched = launched == true,
        status = status,
        request_file = request_path,
        error = not launched and tostring(launch_error) or nil,
        mutations_executed = false,
    })
    assert(os.rename(receipt_path .. ".tmp", receipt_path))
end
