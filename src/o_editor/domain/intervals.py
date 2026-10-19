"""Half-open integer frame intervals ``[start, end)`` and set algebra."""

from __future__ import annotations

from collections.abc import Iterable

Interval = tuple[int, int]


def normalize(intervals: Iterable[Interval], *, join_gap: int = 0) -> tuple[Interval, ...]:
    """Sort, drop empties and merge overlapping (or nearly touching) intervals."""

    ordered = sorted((start, end) for start, end in intervals if end > start)
    merged: list[list[int]] = []
    for start, end in ordered:
        if merged and start <= merged[-1][1] + join_gap:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return tuple((start, end) for start, end in merged)


def union(*groups: Iterable[Interval]) -> tuple[Interval, ...]:
    return normalize(item for group in groups for item in group)


def subtract(base: Iterable[Interval], removal: Iterable[Interval]) -> tuple[Interval, ...]:
    result: list[Interval] = []
    cuts = normalize(removal)
    for start, end in normalize(base):
        cursor = start
        for cut_start, cut_end in cuts:
            if cut_end <= cursor:
                continue
            if cut_start >= end:
                break
            if cut_start > cursor:
                result.append((cursor, cut_start))
            cursor = max(cursor, cut_end)
            if cursor >= end:
                break
        if cursor < end:
            result.append((cursor, end))
    return tuple(result)


def intersect(left: Iterable[Interval], right: Iterable[Interval]) -> tuple[Interval, ...]:
    a, b = normalize(left), normalize(right)
    result: list[Interval] = []
    i = j = 0
    while i < len(a) and j < len(b):
        start = max(a[i][0], b[j][0])
        end = min(a[i][1], b[j][1])
        if end > start:
            result.append((start, end))
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return tuple(result)


def clip_to(intervals: Iterable[Interval], bounds: Interval) -> tuple[Interval, ...]:
    return intersect(intervals, (bounds,))


def total(intervals: Iterable[Interval]) -> int:
    return sum(end - start for start, end in normalize(intervals))


def expand(intervals: Iterable[Interval], before: int, after: int) -> tuple[Interval, ...]:
    return normalize((start - before, end + after) for start, end in intervals)
