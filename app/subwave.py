from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

import httpx

from .models import Track

logger = logging.getLogger(__name__)


def _timestamp(value: Any) -> float:
    if isinstance(value, (int, float)):
        result = float(value)
        return result / 1000 if result > 10_000_000_000 else result
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    raise ValueError("now-playing timestamp is missing or invalid")


def parse_now_playing(payload: dict[str, Any]) -> tuple[Track | None, bool, float | None]:
    online = bool(payload.get("streamOnline"))
    stream = payload.get("stream") if isinstance(payload.get("stream"), dict) else {}
    buffer_seconds = stream.get("bufferSeconds")
    now = payload.get("nowPlaying")
    if not online or not isinstance(now, dict):
        return None, online, float(buffer_seconds) if isinstance(buffer_seconds, (int, float)) else None

    artist = str(now.get("artist") or "").strip()
    title = str(now.get("title") or "").strip()
    if not artist or not title:
        raise ValueError("now-playing payload lacks artist or title")

    duration_raw = now.get("duration")
    duration = float(duration_raw) if isinstance(duration_raw, (int, float)) and duration_raw > 0 else None
    year_raw = now.get("year")
    year = int(year_raw) if isinstance(year_raw, (int, float)) else None
    genres_raw = now.get("genres")
    genres = tuple(str(item) for item in genres_raw if item) if isinstance(genres_raw, list) else ()

    return (
        Track(
            artist=artist,
            title=title,
            album=str(now["album"]).strip() if now.get("album") else None,
            duration=duration,
            subsonic_id=str(now["subsonic_id"]) if now.get("subsonic_id") else None,
            started_at=_timestamp(now.get("timestamp")),
            year=year,
            genres=genres,
        ),
        online,
        float(buffer_seconds) if isinstance(buffer_seconds, (int, float)) else None,
    )


class SubwaveClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient) -> None:
        self.base_url = base_url
        self.client = client

    async def now_playing(self) -> tuple[Track | None, bool, float | None]:
        response = await self.client.get(f"{self.base_url}/now-playing", timeout=5)
        response.raise_for_status()
        return parse_now_playing(response.json())

    async def artwork(self, subsonic_id: str) -> tuple[bytes, str]:
        response = await self.client.get(f"{self.base_url}/cover/{subsonic_id}", timeout=10)
        response.raise_for_status()
        return response.content, response.headers.get("content-type", "image/jpeg")
