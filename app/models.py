from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Track:
    artist: str
    title: str
    album: str | None
    duration: float | None
    subsonic_id: str | None
    started_at: float
    year: int | None = None
    genres: tuple[str, ...] = ()

    @property
    def play_identity(self) -> str:
        base = self.subsonic_id or f"{self.artist.casefold()}|{self.title.casefold()}|{(self.album or '').casefold()}"
        return f"{base}|{self.started_at:.3f}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "artist": self.artist,
            "title": self.title,
            "album": self.album,
            "duration": self.duration,
            "subsonic_id": self.subsonic_id,
            "started_at": self.started_at,
            "year": self.year,
            "genres": list(self.genres),
        }


@dataclass(frozen=True, slots=True)
class LyricLine:
    time: float
    text: str

    def as_dict(self) -> dict[str, Any]:
        return {"time": self.time, "text": self.text}


@dataclass(frozen=True, slots=True)
class LyricsResult:
    status: str
    source: str | None = None
    plain: str | None = None
    synced: str | None = None
    lines: tuple[LyricLine, ...] = ()
    match_confidence: float | None = None
    source_record_id: str | None = None

    @property
    def lyric_type(self) -> str | None:
        if self.lines:
            return "synced"
        if self.plain:
            return "plain"
        return None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "source": self.source,
            "type": self.lyric_type,
            "plain": self.plain if not self.lines else None,
            "lines": [line.as_dict() for line in self.lines],
            "match_confidence": self.match_confidence,
        }


@dataclass(slots=True)
class DisplayState:
    connected: bool = False
    stream_online: bool = False
    track: Track | None = None
    lyrics: LyricsResult = field(default_factory=lambda: LyricsResult(status="idle"))
    last_error: str | None = None
    updated_at: float = 0
