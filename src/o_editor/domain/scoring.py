"""Pure scoring and frequency rules."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ImportanceSignals:
    numeric: bool = False
    question: bool = False
    conclusion: bool = False
    contrast: bool = False
    configured_keyword: bool = False
    pause_before_seconds: float = 0.0
    repetition_count: int = 0


def score_importance(signals: ImportanceSignals) -> float:
    score = 0.18
    score += 0.22 if signals.numeric else 0.0
    score += 0.10 if signals.question else 0.0
    score += 0.25 if signals.conclusion else 0.0
    score += 0.14 if signals.contrast else 0.0
    score += 0.18 if signals.configured_keyword else 0.0
    score += min(0.15, max(0.0, signals.pause_before_seconds) * 0.05)
    score -= min(0.25, max(0, signals.repetition_count - 1) * 0.08)
    return round(min(1.0, max(0.0, score)), 4)


def select_by_frequency(
    candidates: list[tuple[int, float]],
    *,
    fps: float,
    minimum_gap_seconds: float,
    maximum_per_minute: int,
    duration_frames: int,
) -> set[int]:
    if fps <= 0 or minimum_gap_seconds < 0 or maximum_per_minute < 1:
        raise ValueError("invalid frequency settings")
    duration_minutes = max(duration_frames / fps / 60.0, 1 / 60)
    limit = max(1, int(maximum_per_minute * duration_minutes + 0.999))
    minimum_gap_frames = round(minimum_gap_seconds * fps)
    selected: list[int] = []
    for frame, _score in sorted(candidates, key=lambda item: (-item[1], item[0])):
        if len(selected) >= limit:
            break
        if all(abs(frame - existing) >= minimum_gap_frames for existing in selected):
            selected.append(frame)
    return set(selected)
