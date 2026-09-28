from __future__ import annotations

from dataclasses import dataclass
import os


def _float_env(name: str, default: float, *, minimum: float | None = None) -> float:
    raw = os.getenv(name, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number") from exc
    if minimum is not None and value < minimum:
        raise RuntimeError(f"{name} must be at least {minimum}")
    return value


def _int_env(name: str, default: int, *, minimum: int | None = None) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if minimum is not None and value < minimum:
        raise RuntimeError(f"{name} must be at least {minimum}")
    return value


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().casefold()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be true or false")


@dataclass(frozen=True, slots=True)
class Settings:
    subwave_api_url: str
    subwave_stream_url: str
    keep_station_active: bool
    poll_interval: float
    viewer_ttl_seconds: int
    lrclib_base_url: str
    negative_cache_hours: int
    playback_offset_seconds: float
    database_path: str
    app_host: str
    app_port: int
    log_level: str

    @classmethod
    def from_env(cls) -> "Settings":
        station_url = os.getenv("SUBWAVE_STATION_URL", "").rstrip("/")
        legacy_url = os.getenv("SUBWAVE_URL", "").rstrip("/")
        api_url = os.getenv("SUBWAVE_API_URL", "").rstrip("/")
        stream_url = os.getenv("SUBWAVE_STREAM_URL", "")
        if not api_url:
            api_url = legacy_url or (f"{station_url}/api" if station_url else "http://controller:7701")
        if not stream_url:
            stream_url = f"{station_url}/stream.mp3" if station_url else "http://broadcast:7702/stream.mp3"
        return cls(
            subwave_api_url=api_url,
            subwave_stream_url=stream_url,
            keep_station_active=_bool_env("KEEP_STATION_ACTIVE", True),
            poll_interval=_float_env("SUBWAVE_POLL_INTERVAL", 2, minimum=0.5),
            viewer_ttl_seconds=_int_env("VIEWER_TTL_SECONDS", 45, minimum=20),
            lrclib_base_url=os.getenv("LRCLIB_BASE_URL", "https://lrclib.net").rstrip("/"),
            negative_cache_hours=_int_env("LRCLIB_NEGATIVE_CACHE_HOURS", 12, minimum=1),
            playback_offset_seconds=_float_env("PLAYBACK_OFFSET_SECONDS", 22, minimum=0),
            database_path=os.getenv("DATABASE_PATH", "/data/lyrics.db"),
            app_host=os.getenv("APP_HOST", "0.0.0.0"),
            app_port=_int_env("APP_PORT", 8095, minimum=1),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )
