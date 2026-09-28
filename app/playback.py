from __future__ import annotations

from .models import LyricLine


def adjusted_elapsed(now: float, started_at: float, offset_seconds: float, duration: float | None = None) -> float:
    elapsed = max(0.0, now - started_at - offset_seconds)
    if duration is not None:
        return min(elapsed, duration)
    return elapsed


def current_line_index(lines: tuple[LyricLine, ...], elapsed: float) -> int:
    current = -1
    for index, line in enumerate(lines):
        if line.time > elapsed:
            break
        current = index
    return current
