"""Frame/seconds/timecode conversion utilities."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def seconds_to_frames(seconds: float, fps: float, *, timeline_start_frame: int = 0) -> int:
    if seconds < 0:
        raise ValueError("seconds must be non-negative")
    if fps <= 0:
        raise ValueError("fps must be positive")
    value = Decimal(str(seconds)) * Decimal(str(fps))
    return timeline_start_frame + int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def frames_to_seconds(frames: int, fps: float, *, timeline_start_frame: int = 0) -> float:
    if fps <= 0:
        raise ValueError("fps must be positive")
    if frames < timeline_start_frame:
        raise ValueError("frames must not precede timeline start")
    return (frames - timeline_start_frame) / fps


def frames_to_timecode(frames: int, fps: float, *, drop_frame: bool = False) -> str:
    if frames < 0:
        raise ValueError("frames must be non-negative")
    if fps <= 0:
        raise ValueError("fps must be positive")
    if drop_frame:
        return _drop_frame_timecode(frames, fps)
    nominal_fps = round(fps)
    hours, remainder = divmod(frames, nominal_fps * 3600)
    minutes, remainder = divmod(remainder, nominal_fps * 60)
    seconds, frame = divmod(remainder, nominal_fps)
    return f"{hours % 24:02d}:{minutes:02d}:{seconds:02d}:{frame:02d}"


def _drop_frame_timecode(frames: int, fps: float) -> str:
    nominal_fps = round(fps)
    if nominal_fps not in (30, 60) or abs(fps - nominal_fps * 1000 / 1001) > 0.02:
        raise ValueError("drop-frame is supported only for 29.97 and 59.94 fps")
    drop_frames = 2 if nominal_fps == 30 else 4
    frames_per_10_minutes = nominal_fps * 600 - drop_frames * 9
    frames_per_minute = nominal_fps * 60 - drop_frames
    frames_per_24_hours = frames_per_10_minutes * 6 * 24
    frame_number = frames % frames_per_24_hours
    ten_minute_chunks, remainder = divmod(frame_number, frames_per_10_minutes)
    dropped = drop_frames * 9 * ten_minute_chunks
    if remainder >= drop_frames:
        dropped += drop_frames * ((remainder - drop_frames) // frames_per_minute)
    timecode_frames = frame_number + dropped
    hours, remainder = divmod(timecode_frames, nominal_fps * 3600)
    minutes, remainder = divmod(remainder, nominal_fps * 60)
    seconds, frame = divmod(remainder, nominal_fps)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d};{frame:02d}"


def frames_to_clock(frames: int, fps: float) -> str:
    """Elapsed time as ``HH:MM:SS.mmm`` (wall-clock seconds, not timecode frames)."""

    if fps <= 0:
        raise ValueError("fps must be positive")
    total_ms = int(
        (Decimal(frames) / Decimal(str(fps)) * 1000).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    sign = "-" if total_ms < 0 else ""
    total_ms = abs(total_ms)
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{sign}{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def parse_clock(value: str) -> float:
    """Parse ``HH:MM:SS.mmm``/``MM:SS,mmm``/``SS.mmm`` into seconds."""

    text = value.strip().replace(",", ".")
    if not text:
        raise ValueError("empty time")
    parts = text.split(":")
    if len(parts) > 3:
        raise ValueError(f"invalid time: {value}")
    try:
        numbers = [float(part) for part in parts]
    except ValueError as exc:
        raise ValueError(f"invalid time: {value}") from exc
    if any(number < 0 for number in numbers):
        raise ValueError(f"invalid time: {value}")
    seconds = 0.0
    for number in numbers:
        seconds = seconds * 60 + number
    return seconds


def source_time_matches_frame(seconds: float, frame: int, fps: float) -> bool:
    """Match source time without drift from Resolve's rounded NTSC FPS label."""
    rates = [fps]
    for nominal in (24, 30, 48, 60, 120):
        rational = nominal * 1000 / 1001
        if abs(fps - rational) < 0.0002:
            rates.append(rational)
    return any(abs(seconds * rate - frame) < 0.01 for rate in rates)
