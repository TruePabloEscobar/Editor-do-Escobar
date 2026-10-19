from __future__ import annotations

from o_editor.domain.enums import OperationStatus, SuggestionKind
from o_editor.domain.models import ApplicationOperation
from o_editor.infrastructure.resolve.mock_adapter import MockResolveAdapter


def test_mock_duplicate_preserves_original() -> None:
    adapter = MockResolveAdapter()
    original = adapter.get_active_snapshot()
    duplicate = adapter.duplicate_timeline("Entrevista Mock_OE_EDIT_001")
    assert original.timeline_name in adapter.timeline_names
    assert duplicate.timeline_name in adapter.timeline_names
    assert adapter.active_timeline_name == duplicate.timeline_name
    assert duplicate.fingerprint != original.fingerprint


def test_mock_never_applies_to_original() -> None:
    adapter = MockResolveAdapter()
    operation = ApplicationOperation(
        id="op_test",
        suggestion_id="sug_test",
        kind=SuggestionKind.ZOOM,
        backend="mock",
        timeline_start_frame=10,
        timeline_end_frame=20,
        target_item_id="clip",
        parameters=(),
        status=OperationStatus.PENDING,
    )
    result = adapter.apply_operation(operation)
    assert not result.accepted
    assert not adapter.verify_operation(operation)
