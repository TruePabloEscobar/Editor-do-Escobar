"""Application-specific errors with user-safe Portuguese messages."""


class OEditorError(Exception):
    """Base error that is safe to present to the user."""


class ConfigurationError(OEditorError):
    """Invalid or unavailable configuration."""


class ResolveUnavailableError(OEditorError):
    """Resolve API or active context is unavailable."""


class ResolveBridgeCrashedError(ResolveUnavailableError):
    """The isolated native Resolve bridge terminated unexpectedly."""


class CapabilityGateError(OEditorError):
    """A required operation was not proven safe."""


class TimelineChangedError(OEditorError):
    """The timeline no longer matches the analyzed snapshot."""


class OperationVerificationError(OEditorError):
    """An operation returned but could not be verified."""


class CancelledError(OEditorError):
    """A cancellable workflow was interrupted."""
