"""Append-only logg över samtalet.

Varje rad i turns.jsonl är en händelse: `turn`, `reset` eller `compact`.
Kontexten som skickas till modellen härleds ur loggen och skrivs aldrig över,
så inget behöver backuppas och inget kan tappas av misstag.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

TURN = "turn"
RESET = "reset"
COMPACT = "compact"
ROLES = {"user", "assistant", "system"}


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path, session: str | None = None) -> None:
        self.path = path
        self.session = session or uuid4().hex[:8]
        self.broken_lines = 0

    # -- skrivning ---------------------------------------------------------
    def _append(self, event: dict) -> None:
        event.setdefault("time", timestamp())
        event.setdefault("session", self.session)
        line = json.dumps(event, ensure_ascii=False)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def add_turn(self, role: str, content: str, **meta: object) -> None:
        if role not in ROLES:
            raise ValueError(f"okänd roll: {role}")
        self._append({"type": TURN, "role": role, "content": content, **meta})

    def reset(self) -> None:
        self._append({"type": RESET})

    def compact(self, summary: dict[str, list[str]], rendered: str) -> None:
        self._append({"type": COMPACT, "summary": summary, "rendered": rendered})

    # -- läsning -----------------------------------------------------------
    def events(self) -> list[dict]:
        if not self.path.exists():
            return []

        events: list[dict] = []
        broken = 0
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                broken += 1
                continue
            if isinstance(event, dict):
                events.append(event)
            else:
                broken += 1

        self.broken_lines = broken
        return events

    def context(self) -> list[dict[str, str]]:
        """Härledd vy: det som skickas till modellen just nu."""
        messages: list[dict[str, str]] = []

        for event in self.events():
            kind = event.get("type")

            if kind == TURN:
                role = event.get("role")
                content = event.get("content")
                if role in ROLES and isinstance(content, str):
                    messages.append({"role": role, "content": content})

            elif kind == RESET:
                messages = []

            elif kind == COMPACT:
                rendered = event.get("rendered")
                if isinstance(rendered, str) and rendered:
                    messages = [{"role": "assistant", "content": rendered}]

        return messages


def import_legacy(store: Store, legacy: Path) -> int:
    """Engångsimport av version 1:s history.json, om loggen är tom."""
    if store.path.exists() or not legacy.exists():
        return 0

    try:
        data = json.loads(legacy.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"(kunde inte läsa {legacy.name}: {exc})")
        return 0

    if not isinstance(data, list):
        return 0

    imported = 0
    for post in data:
        if not isinstance(post, dict):
            continue
        role = post.get("role")
        content = post.get("content")
        if role in ROLES and isinstance(content, str):
            store.add_turn(role, content, imported=True)
            imported += 1
    return imported
