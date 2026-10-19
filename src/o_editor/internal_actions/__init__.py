"""Internal Resolve menu action requests and local IPC."""

from o_editor.internal_actions.request import (
    InternalActionRequest,
    create_internal_action_request,
    load_internal_action_request,
    mark_request_processed,
)

__all__ = [
    "InternalActionRequest",
    "create_internal_action_request",
    "load_internal_action_request",
    "mark_request_processed",
]
