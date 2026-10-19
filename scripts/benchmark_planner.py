"""Repeatable synthetic planner profile, without media, GPU, or Resolve access."""

from __future__ import annotations

import argparse
import cProfile
import hashlib
import io
import json
import platform
import pstats
import statistics
import time
from dataclasses import replace
from pathlib import Path

from o_editor.demo_podcast import podcast_session
from o_editor.domain.enums import TrackType
from o_editor.domain.microphone_cleanup import MicrophoneCleanupSettings
from o_editor.domain.rough_cut import CutSettings, SilenceSettings, build_rough_cut_plan
from o_editor.domain.speech import SpeechSegment, TranscribedTrack
from o_editor.domain.timeline_layout import ClipInfo, TimelineLayout, TrackInfo


def scenario(phrases: int):
    session = podcast_session()
    duration = phrases * 120
    tracks = (
        TrackInfo(TrackType.VIDEO, 1, "Video"),
        *(TrackInfo(TrackType.AUDIO, index, f"Voice {index}") for index in range(1, 6)),
    )
    clips = tuple(
        ClipInfo(
            f"clip-{track.key}",
            track.track_type,
            track.index,
            1,
            "synthetic",
            track.track_type.value,
            0,
            duration,
            source_start_frame=0,
            source_end_frame=duration,
            media_pool_item_id="synthetic-media",
            media_fps=24.0,
        )
        for track in tracks
    )
    layout = TimelineLayout(
        "synthetic",
        "synthetic",
        "synthetic",
        24.0,
        0,
        duration,
        "00:00:00:00",
        False,
        tracks,
        clips,
    )
    segments = tuple(
        SpeechSegment(
            f"SEG_{phrase * 2 + index:05d}",
            index,
            f"Voice {index}",
            phrase * 120 + 10,
            phrase * 120 + 70,
            f"Frase sintetica numero {phrase}",
            f"Frase sintetica numero {phrase}",
            energy_db=-15.0 if index == 1 else -35.0,
        )
        for phrase in range(phrases)
        for index in (1, 2)
    )
    return replace(
        session,
        start_frame=0,
        end_frame=duration,
        fps=24.0,
        layout=layout.to_dict(),
        layout_fingerprint=layout.fingerprint,
        segments=segments,
        activity={i: () for i in range(1, 6)},
        tracks=tuple(TranscribedTrack(i, f"Voice {i}", "mono") for i in range(1, 6)),
    ), layout


def measure(phrases: int, repeats: int) -> dict:
    session, layout = scenario(phrases)

    def plan():
        return build_rough_cut_plan(
            session,
            layout,
            silence=SilenceSettings(enabled=False),
            cut=CutSettings(),
            microphone_cleanup=MicrophoneCleanupSettings(enabled=True),
            target_timeline_name="synthetic-copy",
            plan_id="benchmark",
            created_at="benchmark",
        )

    times = []
    for _ in range(repeats):
        start = time.perf_counter()
        result = plan()
        times.append(time.perf_counter() - start)
    profile = cProfile.Profile()
    profile.runcall(plan)
    buffer = io.StringIO()
    pstats.Stats(profile, stream=buffer).sort_stats("cumulative").print_stats(14)
    payload = json.dumps(result.to_dict(mode="VALIDATE"), sort_keys=True).encode()
    return {
        "phrases": phrases,
        "segments": len(session.segments),
        "tracks": 6,
        "operations": len(result.operations),
        "blocked": result.blocked,
        "seconds": times,
        "median_seconds": statistics.median(times),
        "plan_sha256": hashlib.sha256(payload).hexdigest(),
        "profile": buffer.getvalue(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phrases", type=int, nargs="+", default=[100, 500])
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    report = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "scenario": "synthetic 24fps; five microphones, equal text with 20dB return",
        "results": [measure(n, args.repeats) for n in args.phrases],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps([{k: v for k, v in r.items() if k != "profile"} for r in report["results"]]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
