from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
import logging
from pathlib import Path
import time
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
import httpx

from .cache import LyricsCache
from .config import Settings
from .lyrics import LrclibClient
from .models import DisplayState, LyricsResult, Track
from .playback import adjusted_elapsed, current_line_index
from .subwave import SubwaveClient

settings = Settings.from_env()
logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("subwave_lyrics")
BASE_DIR = Path(__file__).resolve().parent


class ApplicationService:
    def __init__(self) -> None:
        self.cache = LyricsCache(settings.database_path)
        self.http = httpx.AsyncClient(follow_redirects=True)
        self.subwave = SubwaveClient(settings.subwave_api_url, self.http)
        self.lrclib = LrclibClient(settings.lrclib_base_url, self.http)
        self.state = DisplayState()
        self.lock = asyncio.Lock()
        self.poll_task: asyncio.Task[None] | None = None
        self.lookup_task: asyncio.Task[None] | None = None
        self.listener_task: asyncio.Task[None] | None = None
        self.viewer_active_until = 0.0
        self.stream_buffer_seconds: float | None = None
        self._was_connected: bool | None = None

    async def start(self) -> None:
        await self.cache.initialize()
        self.poll_task = asyncio.create_task(self._poll_loop(), name="subwave-poller")
        logger.info(
            "Starting SUB/WAVE Lyrics (controller=%s, poll=%.1fs, playback_offset=%.1fs)",
            settings.subwave_api_url,
            settings.poll_interval,
            settings.playback_offset_seconds,
        )

    async def stop(self) -> None:
        for task in (self.listener_task, self.lookup_task, self.poll_task):
            if task:
                task.cancel()
        for task in (self.listener_task, self.lookup_task, self.poll_task):
            if task:
                with suppress(asyncio.CancelledError):
                    await task
        await self.http.aclose()

    def viewer_heartbeat(self) -> None:
        if not settings.keep_station_active:
            return
        self.viewer_active_until = time.monotonic() + settings.viewer_ttl_seconds
        if not self.listener_task or self.listener_task.done():
            self.listener_task = asyncio.create_task(self._hold_stream_listener(), name="viewer-stream-listener")

    async def _hold_stream_listener(self) -> None:
        logger.info("Lyrics viewer connected; holding one internal radio listener")
        try:
            while time.monotonic() < self.viewer_active_until:
                try:
                    timeout = httpx.Timeout(connect=5, read=None, write=5, pool=5)
                    async with self.http.stream("GET", settings.subwave_stream_url, timeout=timeout) as response:
                        response.raise_for_status()
                        async for _ in response.aiter_raw():
                            if time.monotonic() >= self.viewer_active_until:
                                return
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning("Internal radio-listener connection failed: %s", exc)
                    await asyncio.sleep(3)
        finally:
            logger.info("No active lyrics viewers; releasing internal radio listener")

    async def _poll_loop(self) -> None:
        while True:
            started = time.monotonic()
            try:
                track, online, buffer_seconds = await self.subwave.now_playing()
                if self._was_connected is not True:
                    logger.info("Connected to SUB/WAVE controller")
                self._was_connected = True
                await self._apply_track(track, online, buffer_seconds)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self._was_connected is not False:
                    logger.warning("SUB/WAVE controller unavailable: %s", exc)
                self._was_connected = False
                async with self.lock:
                    self.state.connected = False
                    self.state.last_error = "SUB/WAVE unavailable"
                    self.state.updated_at = time.time()
            delay = max(0.1, settings.poll_interval - (time.monotonic() - started))
            await asyncio.sleep(delay)

    async def _apply_track(self, track: Track | None, online: bool, buffer_seconds: float | None) -> None:
        async with self.lock:
            old_identity = self.state.track.play_identity if self.state.track else None
            new_identity = track.play_identity if track else None
            changed = old_identity != new_identity
            self.state.connected = True
            self.state.stream_online = online
            self.state.track = track
            self.state.last_error = None
            self.state.updated_at = time.time()
            self.stream_buffer_seconds = buffer_seconds
            if changed:
                self.state.lyrics = LyricsResult(status="loading" if track else "idle")

        if not changed:
            return
        if self.lookup_task:
            self.lookup_task.cancel()
        if track:
            logger.info("Track changed: %s — %s", track.artist, track.title)
            self.lookup_task = asyncio.create_task(self._resolve_lyrics(track), name="lyrics-lookup")
        else:
            logger.info("Station is off-air or no track is playing")
            self.lookup_task = None

    async def _resolve_lyrics(self, track: Track) -> None:
        identity = track.play_identity
        while True:
            try:
                result = await self.cache.get(track)
                if result is not None:
                    logger.info("Lyrics cache hit: %s — %s (%s)", track.artist, track.title, result.status)
                else:
                    logger.info("Lyrics cache miss: %s — %s", track.artist, track.title)
                    try:
                        result = await self.lrclib.lookup(track)
                        if result.status == "found":
                            logger.info("LRCLIB match found: %s — %s", track.artist, track.title)
                            await self.cache.put(track, result)
                        else:
                            logger.info("LRCLIB has no confident match: %s — %s", track.artist, track.title)
                            retry = time.time() + settings.negative_cache_hours * 3600
                            await self.cache.put(track, result, retry_after=retry)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        logger.warning("LRCLIB lookup failed for %s — %s: %s", track.artist, track.title, exc)
                        result = LyricsResult(status="error", source="lrclib")
                        await self.cache.put(track, result, retry_after=time.time() + 300)

                async with self.lock:
                    if self.state.track and self.state.track.play_identity == identity:
                        self.state.lyrics = result
                        self.state.updated_at = time.time()
                    else:
                        return
                if result.status != "error":
                    return
                await asyncio.sleep(300)
            except asyncio.CancelledError:
                raise

    async def snapshot(self) -> dict[str, Any]:
        async with self.lock:
            connected = self.state.connected
            online = self.state.stream_online
            track = self.state.track
            lyrics = self.state.lyrics
            error = self.state.last_error
            updated_at = self.state.updated_at
            buffer_seconds = self.stream_buffer_seconds
        now = time.time()
        elapsed = None
        line_index = -1
        if track:
            elapsed = adjusted_elapsed(now, track.started_at, settings.playback_offset_seconds, track.duration)
            line_index = current_line_index(lyrics.lines, elapsed)
        return {
            "connected": connected,
            "playing": bool(online and track),
            "stream_online": online,
            "track": track.as_dict() if track else None,
            "playback": {
                "elapsed": elapsed,
                "offset_seconds": settings.playback_offset_seconds,
                "stream_buffer_seconds": buffer_seconds,
                "server_time": now,
                "active_line_index": line_index,
            },
            "lyrics": lyrics.as_dict(),
            "error": error,
            "updated_at": updated_at,
        }


service = ApplicationService()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await service.start()
    try:
        yield
    finally:
        await service.stop()


app = FastAPI(title="SUB/WAVE Lyrics", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(BASE_DIR / "templates" / "index.html")


@app.get("/healthz")
async def healthz() -> JSONResponse:
    try:
        await service.cache.healthcheck()
    except Exception as exc:
        logger.error("Healthcheck failed: %s", exc)
        return JSONResponse({"status": "unhealthy"}, status_code=503)
    return JSONResponse({"status": "ok"})


@app.get("/api/display")
async def display() -> dict[str, Any]:
    return await service.snapshot()


@app.post("/api/viewer-heartbeat", status_code=204)
async def viewer_heartbeat() -> Response:
    service.viewer_heartbeat()
    return Response(status_code=204)


@app.get("/api/status")
async def status() -> dict[str, Any]:
    snapshot = await service.snapshot()
    return {key: snapshot[key] for key in ("connected", "playing", "stream_online", "error", "updated_at")}


@app.get("/api/now-playing")
async def now_playing() -> dict[str, Any]:
    snapshot = await service.snapshot()
    return {"playing": snapshot["playing"], "track": snapshot["track"], "playback": snapshot["playback"]}


@app.get("/api/lyrics")
async def lyrics() -> dict[str, Any]:
    return (await service.snapshot())["lyrics"]


@app.get("/api/artwork/current")
async def current_artwork() -> Response:
    async with service.lock:
        track = service.state.track
    if not track or not track.subsonic_id:
        raise HTTPException(status_code=404, detail="No artwork available")
    try:
        content, media_type = await service.subwave.artwork(track.subsonic_id)
    except httpx.HTTPError as exc:
        logger.warning("Artwork proxy failed: %s", exc)
        raise HTTPException(status_code=502, detail="Artwork unavailable") from exc
    return Response(content, media_type=media_type, headers={"Cache-Control": "private, max-age=30"})
