"""Runtime configuration loaded from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent

# A .env in the project root or in /backend is picked up for local development.
# Real environment variables (e.g. on Cloud Run) always take precedence.
load_dotenv(PROJECT_ROOT / ".env", override=False)
load_dotenv(BACKEND_DIR / ".env", override=False)

VALID_AI_MODES = {"auto", "gemini", "offline"}


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be a number, got {raw!r}") from exc


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str | None
    gemini_model: str
    ai_mode: str
    gemini_timeout_seconds: float
    cors_origins: list[str] = field(default_factory=list)
    frontend_dir: Path = PROJECT_ROOT / "frontend"
    log_level: str = "INFO"

    @property
    def gemini_enabled(self) -> bool:
        return self.ai_mode != "offline" and bool(self.gemini_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    ai_mode = os.getenv("AI_MODE", "auto").strip().lower()
    if ai_mode not in VALID_AI_MODES:
        raise ValueError(f"AI_MODE must be one of {sorted(VALID_AI_MODES)}, got {ai_mode!r}")

    api_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip() or None

    return Settings(
        gemini_api_key=api_key,
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip(),
        ai_mode=ai_mode,
        gemini_timeout_seconds=_float_env("GEMINI_TIMEOUT_SECONDS", 30.0),
        cors_origins=_split_csv(os.getenv("CORS_ORIGINS", "*")),
        frontend_dir=Path(os.getenv("FRONTEND_DIR", str(PROJECT_ROOT / "frontend"))).resolve(),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )
