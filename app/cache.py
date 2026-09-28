from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import time

import aiosqlite

from .lyrics import normalize, parse_lrc
from .models import LyricsResult, Track

CACHE_MATCHER_VERSION = 2


def cache_key(track: Track) -> str:
    if track.subsonic_id:
        return f"subsonic:{track.subsonic_id}"
    material = "|".join((normalize(track.artist), normalize(track.title), normalize(track.album), str(round(track.duration or 0))))
    return "metadata:" + hashlib.sha256(material.encode()).hexdigest()


class LyricsCache:
    def __init__(self, path: str) -> None:
        self.path = path

    async def initialize(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS lyrics_cache (
                    cache_key TEXT PRIMARY KEY,
                    subsonic_id TEXT,
                    artist TEXT NOT NULL,
                    title TEXT NOT NULL,
                    album TEXT,
                    duration REAL,
                    source TEXT,
                    status TEXT NOT NULL,
                    plain_lyrics TEXT,
                    synced_lyrics TEXT,
                    match_confidence REAL,
                    source_record_id TEXT,
                    retrieved_at TEXT NOT NULL,
                    retry_after REAL,
                    matcher_version INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            columns = {row[1] for row in await (await db.execute("PRAGMA table_info(lyrics_cache)")).fetchall()}
            if "matcher_version" not in columns:
                await db.execute("ALTER TABLE lyrics_cache ADD COLUMN matcher_version INTEGER NOT NULL DEFAULT 1")
            await db.commit()

    async def healthcheck(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("SELECT 1")

    async def get(self, track: Track) -> LyricsResult | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM lyrics_cache WHERE cache_key = ?", (cache_key(track),))
            row = await cursor.fetchone()
        if not row:
            return None
        if row["status"] != "found" and row["matcher_version"] < CACHE_MATCHER_VERSION:
            return None
        if row["status"] != "found" and row["retry_after"] and row["retry_after"] <= time.time():
            return None
        return LyricsResult(
            status=row["status"],
            source=row["source"],
            plain=row["plain_lyrics"],
            synced=row["synced_lyrics"],
            lines=parse_lrc(row["synced_lyrics"]),
            match_confidence=row["match_confidence"],
            source_record_id=row["source_record_id"],
        )

    async def put(self, track: Track, result: LyricsResult, retry_after: float | None = None) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO lyrics_cache (
                    cache_key, subsonic_id, artist, title, album, duration, source, status,
                    plain_lyrics, synced_lyrics, match_confidence, source_record_id,
                    retrieved_at, retry_after, matcher_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    artist=excluded.artist, title=excluded.title, album=excluded.album,
                    duration=excluded.duration, source=excluded.source, status=excluded.status,
                    plain_lyrics=excluded.plain_lyrics, synced_lyrics=excluded.synced_lyrics,
                    match_confidence=excluded.match_confidence,
                    source_record_id=excluded.source_record_id,
                    retrieved_at=excluded.retrieved_at, retry_after=excluded.retry_after,
                    matcher_version=excluded.matcher_version
                """,
                (
                    cache_key(track), track.subsonic_id, track.artist, track.title, track.album,
                    track.duration, result.source, result.status, result.plain, result.synced,
                    result.match_confidence, result.source_record_id,
                    datetime.now(timezone.utc).isoformat(), retry_after, CACHE_MATCHER_VERSION,
                ),
            )
            await db.commit()
