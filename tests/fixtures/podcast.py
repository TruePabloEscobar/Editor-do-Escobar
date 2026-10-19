"""Test fixture: re-export of the demo podcast used by the mock mode."""

from o_editor.demo_podcast import (
    BURSTS,
    DURATION_SECONDS,
    FPS,
    PHRASES,
    SAMPLE_RATE,
    SPEAKERS,
    START_FRAME,
    Burst,
    demo_phrase_resolver,
    frames,
    phrase_for_frequency,
    podcast_layout,
    podcast_session,
    write_podcast_media,
)

__all__ = [
    "BURSTS",
    "DURATION_SECONDS",
    "FPS",
    "PHRASES",
    "SAMPLE_RATE",
    "SPEAKERS",
    "START_FRAME",
    "Burst",
    "demo_phrase_resolver",
    "frames",
    "phrase_for_frequency",
    "podcast_layout",
    "podcast_session",
    "write_podcast_media",
]
