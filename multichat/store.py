"""Sessioner sparade som append-only JSONL, en fil per session.

Varje rad är en händelse: en tur (`turn`) eller en komprimering (`compact`).
Det modellen ser härleds ur loggen och skrivs aldrig över.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

SUMMARY = "Sammanfattning"
SYSTEM = "system"
TURN = "turn"
COMPACT = "compact"
TOPIC = "topic"
TITLE = "title"
DOCUMENT = "document"
DOCUMENT_SPEAKER = "Dokument"
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class SessionNotFound(KeyError):
    """Sessionen finns inte, eller id:t är ogiltigt."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SessionStore:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.folder.mkdir(parents=True, exist_ok=True)

    # -- sökvägar och existens --------------------------------------------
    def _path(self, session_id: str) -> Path:
        if not _SAFE_ID.match(session_id):
            raise SessionNotFound(session_id)
        path = self.folder / f"{session_id}.jsonl"
        if not path.exists():
            raise SessionNotFound(session_id)
        return path

    # -- skrivning ----------------------------------------------------------
    def create(self) -> str:
        session_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:4]
        (self.folder / f"{session_id}.jsonl").touch()
        return session_id

    def _append(self, session_id: str, event: dict) -> None:
        path = self._path(session_id)
        event["time"] = _now()
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def add(self, session_id: str, speaker: str, content: str) -> None:
        self._append(session_id, {"type": TURN, "speaker": speaker, "content": content})

    def compact(self, session_id: str, summary: str) -> None:
        self._append(session_id, {"type": COMPACT, "summary": summary})

    # -- läsning ------------------------------------------------------------
    def _events(self, session_id: str) -> list[dict]:
        events: list[dict] = []
        for line in self._path(session_id).read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
        return events

    def transcript(self, session_id: str) -> list[dict[str, str]]:
        """Allt som ska visas i chatten, med komprimeringar markerade."""
        shown: list[dict[str, str]] = []
        for event in self._events(session_id):
            if event.get("type") == TURN:
                shown.append({"speaker": event["speaker"], "content": event["content"]})
            elif event.get("type") == COMPACT:
                shown.append({"speaker": SYSTEM, "content": "Samtalet komprimerades."})
        return shown

    def context(self, session_id: str) -> list[dict[str, str]]:
        """Det modellen ska se.

        Först den aktiva filen (om någon), sedan senaste sammanfattningen (om någon)
        och turerna efter den.
        """
        context: list[dict[str, str]] = []
        document: dict[str, str] | None = None
        for event in self._events(session_id):
            if event.get("type") == TURN:
                context.append({"speaker": event["speaker"], "content": event["content"]})
            elif event.get("type") == COMPACT:
                context = [{"speaker": SUMMARY, "content": event["summary"]}]
            elif event.get("type") == DOCUMENT:
                document = None
                if event.get("name") and event.get("content"):
                    document = {
                        "speaker": DOCUMENT_SPEAKER,
                        "content": f"---dokument {event['name']}---\n{event['content']}",
                    }
        return ([document] if document else []) + context

    def set_topic(self, session_id: str, document: str | None, topic: str | None) -> None:
        """Väljer ett ämne ur ett dokument för sessionen. None betyder att ämnet släpps."""
        self._append(session_id, {"type": TOPIC, "document": document, "topic": topic})

    def active_topic(self, session_id: str) -> dict[str, str] | None:
        """Det senast valda ämnet, eller None om inget är valt."""
        active = None
        for event in self._events(session_id):
            if event.get("type") == TOPIC:
                active = (
                    {"document": event["document"], "topic": event["topic"]}
                    if event.get("topic")
                    else None
                )
        return active

    def turns_since_compact(self, session_id: str) -> int:
        """Antal meddelanden sedan senaste komprimering (eller sedan start)."""
        count = 0
        for event in self._events(session_id):
            if event.get("type") == TURN:
                count += 1
            elif event.get("type") == COMPACT:
                count = 0
        return count

    def add_document(self, session_id: str, name: str | None, content: str | None = None) -> None:
        """Laddar in ett dokument i historiken, eller tar bort det om name är None.

        Det gäller tills nästa dokument laddas. Visas inte i chatten.
        """
        self._append(session_id, {"type": DOCUMENT, "name": name, "content": content})

    def current_document(self, session_id: str) -> str | None:
        """Namnet på den senast uppladdade filen i sessionen, om någon."""
        current = None
        for event in self._events(session_id):
            if event.get("type") == DOCUMENT:
                current = event["name"]
        return current

    def set_title(self, session_id: str, title: str) -> None:
        """Byter namn på sessionen. Det senaste namnet gäller."""
        self._append(session_id, {"type": TITLE, "title": title})

    def list_sessions(self) -> list[dict[str, str]]:
        """Nyaste sessionen först. Titeln är början på användarens första meddelande."""
        sessions = []
        for path in sorted(self.folder.glob("*.jsonl"), reverse=True):
            events = self._events(path.stem)
            first = next(
                (e["content"] for e in events if e.get("type") == TURN and e.get("speaker") == "Du"),
                None,
            )
            custom = [e["title"] for e in events if e.get("type") == TITLE]
            title = custom[-1] if custom else (first or "Tom session")[:50]
            sessions.append({"id": path.stem, "title": title})
        return sessions
