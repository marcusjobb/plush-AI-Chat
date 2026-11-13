"""Miljö, sökvägar och gränser för chatten."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

HOME = Path(__file__).resolve().parent
STORE_FILE = HOME / "turns.jsonl"
LEGACY_HISTORY = HOME / "history.json"
ENV_FILE = HOME / ".env"

DEFAULT_BASE_URL = "https://api.1min.ai/openai/v1"
DEFAULT_MODEL = "gpt-4o-mini"

# Automatisk komprimering när historiken når så här många meddelanden (0 = av).
AUTO_COMPACT_AT = 50

# 1min.AI:s tak per anrop.
MAX_MESSAGES = 200
MAX_CHARS = 100_000
WARN_AT = 0.8


@dataclass(frozen=True)
class Settings:
    api_key: str
    model: str
    compact_model: str
    base_url: str
    auto_compact_at: int = AUTO_COMPACT_AT
    persona: bool = True


def persona_enabled(raw: str | None) -> bool:
    """Personan är på om variabeln saknas eller inte är en nej-variant."""
    if raw is None:
        return True
    return raw.strip().lower() not in {"0", "off", "nej", "false", "no"}


def _auto_compact_at() -> int:
    raw = os.environ.get("ONEMIN_AUTO_COMPACT", "").strip()
    if not raw:
        return AUTO_COMPACT_AT
    try:
        value = int(raw)
    except ValueError:
        print(
            f"(varning: ONEMIN_AUTO_COMPACT={raw!r} är inte ett tal "
            f"— använder {AUTO_COMPACT_AT})"
        )
        return AUTO_COMPACT_AT
    if value < 0:
        print(
            "(varning: ONEMIN_AUTO_COMPACT är negativt "
            "— automatisk komprimering avstängd)"
        )
        return 0
    return value


def load_settings() -> Settings:
    load_dotenv(ENV_FILE)

    api_key = os.environ.get("ONEMIN_API_KEY", "").strip()
    if not api_key:
        sys.exit(
            "ONEMIN_API_KEY saknas — lägg den i chat/.env (se .env.example) "
            "eller exportera den i skalet."
        )

    model = os.environ.get("ONEMIN_MODEL", "").strip() or DEFAULT_MODEL
    return Settings(
        api_key=api_key,
        model=model,
        compact_model=os.environ.get("ONEMIN_COMPACT_MODEL", "").strip() or model,
        base_url=os.environ.get("ONEMIN_BASE_URL", "").strip() or DEFAULT_BASE_URL,
        auto_compact_at=_auto_compact_at(),
        persona=persona_enabled(os.environ.get("ONEMIN_PERSONA")),
    )


def budget_state(messages: list[dict[str, str]]) -> tuple[str, str] | None:
    """Varna innan historiken slår i 1min.AI:s tak (200 meddelanden / 100 000 tecken).

    Returnerar ("stop" | "warn", meddelande) eller None.
    """
    count = len(messages)
    chars = sum(len(m.get("content", "")) for m in messages)

    if count >= MAX_MESSAGES or chars >= MAX_CHARS:
        return (
            "stop",
            f"historiken är för stor ({count} meddelanden, {chars} tecken) "
            "— /compact krävs innan nästa anrop",
        )
    if count >= MAX_MESSAGES * WARN_AT or chars >= MAX_CHARS * WARN_AT:
        return (
            "warn",
            f"historiken börjar bli stor ({count} meddelanden, {chars} tecken) "
            "— överväg /compact",
        )
    return None
