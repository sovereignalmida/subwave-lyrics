from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import asyncio
import logging
import re
import unicodedata
from typing import Any

import httpx

from .models import LyricLine, LyricsResult, Track

logger = logging.getLogger(__name__)

_TIMESTAMP = re.compile(r"\[(\d{1,3}):(\d{2}(?:\.\d{1,3})?)\]")
_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE = re.compile(r"\s+")


def normalize(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKC", value).casefold()
    text = text.replace("’", "'").replace("&", " and ")
    return _SPACE.sub(" ", _PUNCTUATION.sub(" ", text)).strip()


def parse_lrc(value: str | None) -> tuple[LyricLine, ...]:
    if not value:
        return ()
    parsed: list[LyricLine] = []
    for raw_line in value.splitlines():
        stamps = list(_TIMESTAMP.finditer(raw_line))
        if not stamps:
            continue
        text = _TIMESTAMP.sub("", raw_line).strip()
        for stamp in stamps:
            parsed.append(LyricLine(time=int(stamp.group(1)) * 60 + float(stamp.group(2)), text=text))
    return tuple(sorted(parsed, key=lambda line: line.time))


@dataclass(frozen=True, slots=True)
class ScoredMatch:
    score: float
    item: dict[str, Any]


def artist_similarity(wanted: str, candidate: str) -> float:
    if wanted == candidate:
        return 1.0
    feature_markers = (" with ", " feat ", " featuring ", " ft ")
    if any(candidate.startswith(wanted + marker) for marker in feature_markers):
        return 1.0
    if any(wanted.startswith(candidate + marker) for marker in feature_markers):
        return 1.0
    return SequenceMatcher(None, wanted, candidate).ratio()


def score_match(track: Track, item: dict[str, Any]) -> float:
    wanted_artist = normalize(track.artist)
    wanted_title = normalize(track.title)
    artist = normalize(str(item.get("artistName") or ""))
    title = normalize(str(item.get("trackName") or ""))
    artist_ratio = artist_similarity(wanted_artist, artist)
    title_ratio = SequenceMatcher(None, wanted_title, title).ratio()
    if artist_ratio < 0.85 or title_ratio < 0.88:
        return 0

    score = artist_ratio * 40 + title_ratio * 40
    wanted_album = normalize(track.album)
    album = normalize(str(item.get("albumName") or ""))
    if wanted_album and album:
        score += SequenceMatcher(None, wanted_album, album).ratio() * 12

    candidate_duration = item.get("duration")
    if track.duration and isinstance(candidate_duration, (int, float)):
        difference = abs(track.duration - float(candidate_duration))
        if difference <= 3:
            score += 8
        elif difference <= 8:
            score += 5
        elif difference <= 20:
            score += 1
        else:
            score -= min(15, difference / 10)
    return round(score, 3)


def choose_match(track: Track, items: list[dict[str, Any]]) -> ScoredMatch | None:
    candidates = [ScoredMatch(score_match(track, item), item) for item in items]
    candidates = [candidate for candidate in candidates if candidate.score >= 72]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda candidate: (
            candidate.score,
            bool(candidate.item.get("syncedLyrics")),
            bool(candidate.item.get("plainLyrics")),
        ),
    )


class LrclibClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient) -> None:
        self.base_url = base_url
        self.client = client

    async def _search(self, params: dict[str, str]) -> list[dict[str, Any]]:
        response: httpx.Response | None = None
        for attempt in range(3):
            response = await self.client.get(
                f"{self.base_url}/api/search",
                params=params,
                headers={"User-Agent": "SUBWAVE-Lyrics/1.0 (self-hosted)"},
                timeout=12,
            )
            if response.status_code not in (429, 503):
                break
            if attempt < 2:
                await asyncio.sleep(0.75 * (attempt + 1))
        assert response is not None
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("LRCLIB returned an unexpected response")
        return [item for item in payload if isinstance(item, dict)]

    async def lookup(self, track: Track) -> LyricsResult:
        params = {"track_name": track.title, "artist_name": track.artist}
        if track.album:
            params["album_name"] = track.album
        items = await self._search(params)
        match = choose_match(track, items)
        if not match and track.album:
            fallback_items = await self._search({"track_name": track.title, "artist_name": track.artist})
            known_ids = {item.get("id") for item in items}
            items.extend(item for item in fallback_items if item.get("id") not in known_ids)
            match = choose_match(track, items)
        if not match:
            return LyricsResult(status="not_found", source="lrclib")
        item = match.item
        synced = item.get("syncedLyrics") if isinstance(item.get("syncedLyrics"), str) else None
        plain = item.get("plainLyrics") if isinstance(item.get("plainLyrics"), str) else None
        if not synced and not plain:
            return LyricsResult(status="not_found", source="lrclib")
        return LyricsResult(
            status="found",
            source="lrclib",
            plain=plain,
            synced=synced,
            lines=parse_lrc(synced),
            match_confidence=match.score,
            source_record_id=str(item.get("id")) if item.get("id") is not None else None,
        )
