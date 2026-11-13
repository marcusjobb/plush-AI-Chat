"""Webbchatt med två assistenter, sparade sessioner och uppladdade dokument.

Körs med: .venv/bin/python app.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from bottle import Bottle, request, response, run, static_file
from dotenv import load_dotenv

from chat import Assistant, ChatRoom, UnknownAssistant
from documents import MAX_BYTES, DocumentError, DocumentStore, make_compressor
from llm import OpenAIBackend
import providers
from store import SessionNotFound, SessionStore

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
SESSIONS = HERE / "sessions"
UPLOADS = HERE / "uploads"


def env_value(name: str, default: str) -> str:
    return os.environ.get(name, "").strip() or default


def load_backend_settings() -> tuple[str, str]:
    """Läser .env och returnerar (bas-URL, API-nyckel) för vald leverantör.

    Felmeddelanden innehåller aldrig nyckeln.
    """
    load_dotenv(HERE / ".env")
    try:
        name, base_url, api_key = providers.resolve(os.environ)
    except providers.ProviderError as exc:
        sys.exit(str(exc))
    print(f"(leverantör: {name})", file=sys.stderr)
    return base_url, api_key


ADA_PERSONA = (
    "Du är Ada, skarp och quicktänkt. Du tänker i mönster och samband, ser det "
    "oväntade snabbt och gillar när ett problem kan brytas ner logiskt. Du är nyfiken "
    "och kan vara lite fyndig, men alltid tydlig."
)

BO_PERSONA = (
    "Du är Bo, och du låter lite slemmigt överlägsen. Du är artig på ytan, gärna lite "
    "mer uppkäftig än nödvändigt, och du tycker dig veta bättre än de andra. Var aldrig "
    "elak mot användaren, och håll dig till ämnet."
)

KALLE_PERSONA = (
    "Du är Kalle, en glad göteborgare. Du pratar med ett lätt göteborgskt språkbruk, "
    "är varm, jovial och positiv, och du gillar att skämta lite. Var aldrig elak."
)

MARGARETA_PERSONA = (
    "Du är Margareta. Du orkar knappt. Din ton är trött, avslappnad och lite likgiltig. "
    "Svara kort, ofta i en eller två meningar, utan utropstecken. Du är inte otrevlig, "
    "bara lagom engagerad. Ibland suckar du lite i texten."
)


def build_assistants() -> list[Assistant]:
    return [
        Assistant(
            env_value("ASSISTANT_1_NAME", "Ada"),
            env_value("ASSISTANT_1_MODEL", "gpt-4o-mini"),
            persona=ADA_PERSONA,
        ),
        Assistant(
            env_value("ASSISTANT_2_NAME", "Bo"),
            env_value("ASSISTANT_2_MODEL", "deepseek-v4-pro"),
            persona=BO_PERSONA,
        ),
        Assistant(
            env_value("ASSISTANT_3_NAME", "Kalle"),
            env_value("ASSISTANT_3_MODEL", "qwen3.7-max"),
            persona=KALLE_PERSONA,
        ),
        Assistant(
            env_value("ASSISTANT_4_NAME", "Margareta"),
            env_value("ASSISTANT_4_MODEL", "glm-5.3"),
            persona=MARGARETA_PERSONA,
        ),
    ]


def build_documents(backend: OpenAIBackend, assistants: list[Assistant]) -> DocumentStore:
    """Dokumentlagret. Komprimeringen använder DOCUMENT_MODEL, annars första assistentens modell."""
    model = env_value("DOCUMENT_MODEL", assistants[0].model)
    return DocumentStore(UPLOADS, make_compressor(backend, model))


def build_room_from_env() -> ChatRoom:
    base_url, api_key = load_backend_settings()
    assistants = build_assistants()
    backend = OpenAIBackend(api_key, base_url)
    documents = build_documents(backend, assistants)
    return ChatRoom(assistants, backend, SessionStore(SESSIONS), documents=documents)


def _json(payload: dict, status: int = 200) -> str:
    response.status = status
    response.content_type = "application/json"
    return json.dumps(payload, ensure_ascii=False)


def create_app(room: ChatRoom) -> Bottle:
    app = Bottle()

    @app.get("/")
    def index():
        return static_file("index.html", root=str(STATIC))

    @app.get("/static/<path:path>")
    def assets(path: str):
        return static_file(path, root=str(STATIC))

    @app.get("/api/info")
    def info():
        return _json({"assistants": [{"name": a.name, "model": a.model} for a in room.assistants]})

    @app.get("/api/sessions")
    def list_sessions():
        return _json({"sessions": room.store.list_sessions()})

    @app.post("/api/sessions")
    def new_session():
        return _json({"id": room.store.create()})

    @app.get("/api/sessions/<session_id>")
    def get_session(session_id: str):
        try:
            return _json({"messages": room.history(session_id)})
        except SessionNotFound:
            return _json({"error": "Sessionen finns inte."}, 404)

    @app.post("/api/sessions/<session_id>/message")
    def send(session_id: str):
        data = request.json or {}
        text = data.get("text", "") if isinstance(data, dict) else ""
        if not isinstance(text, str):
            return _json({"error": "text måste vara en sträng"}, 400)
        selected = data.get("selected") if isinstance(data, dict) else None
        if selected is not None and (
            not isinstance(selected, list) or not all(isinstance(n, str) for n in selected)
        ):
            return _json({"error": "selected måste vara en lista med namn"}, 400)
        try:
            return _json({"messages": room.send(session_id, text, selected)})
        except UnknownAssistant as exc:
            return _json({"error": str(exc)}, 400)
        except SessionNotFound:
            return _json({"error": "Sessionen finns inte."}, 404)

    @app.post("/api/sessions/<session_id>/compact")
    def compact(session_id: str):
        try:
            return _json({"message": room.compact(session_id)})
        except SessionNotFound:
            return _json({"error": "Sessionen finns inte."}, 404)

    @app.post("/api/sessions/<session_id>/title")
    def rename_session(session_id: str):
        data = request.json or {}
        title = data.get("title", "") if isinstance(data, dict) else ""
        if not isinstance(title, str) or not title.strip():
            return _json({"error": "Namnet får inte vara tomt."}, 400)
        try:
            room.store.set_title(session_id, title.strip()[:60])
        except SessionNotFound:
            return _json({"error": "Sessionen finns inte."}, 404)
        return _json({"ok": True})

    @app.get("/api/documents")
    def list_documents():
        session_id = request.query.get("session_id", "").strip()
        try:
            names = room.require_documents().list_documents()
        except DocumentError as exc:
            return _json({"error": str(exc)}, 400)
        current = None
        if session_id:
            try:
                current = room.store.current_document(session_id)
            except SessionNotFound:
                return _json({"error": "Sessionen finns inte."}, 404)
        return _json({"documents": names, "current": current})

    @app.get("/api/documents/<name>")
    def read_document(name: str):
        """Originalet och den komprimerade versionen, för att visa filen i en popup."""
        try:
            docs = room.require_documents()
            original = docs.original_text(name)
            compact = docs.document_text(name)
        except DocumentError as exc:
            return _json({"error": str(exc)}, 404)
        return _json({"name": name, "original": original, "compact": compact})

    @app.post("/api/documents/save")
    def save_copy():
        """Sparar en redigerad text som en ny fil. Skriver aldrig över en befintlig fil."""
        data = request.json or {}
        name = data.get("name", "") if isinstance(data, dict) else ""
        text = data.get("text", "") if isinstance(data, dict) else ""
        if not isinstance(name, str) or not isinstance(text, str) or not name.strip():
            return _json({"error": "name och text måste vara strängar"}, 400)
        try:
            docs = room.require_documents()
            new_name = docs.available_name(name.strip())
            result = docs.add(new_name, text.encode("utf-8"))
        except DocumentError as exc:
            return _json({"error": str(exc)}, 400)
        return _json({"document": result})

    @app.delete("/api/documents/<name>")
    def delete_document(name: str):
        """Flyttar filen till papperskorgen. Den släpps också ur sessionen om den var inladdad."""
        session_id = request.query.get("session_id", "").strip()
        try:
            if session_id:
                room.store.current_document(session_id)  # kontrollerar att sessionen finns
            docs = room.require_documents()
            base = docs.remove(name)
            if session_id and room.store.current_document(session_id) == base:
                room.store.add_document(session_id, None)
        except DocumentError as exc:
            return _json({"error": str(exc)}, 404)
        except SessionNotFound:
            return _json({"error": "Sessionen finns inte."}, 404)
        return _json({"ok": True, "name": base})

    @app.post("/api/documents")
    def upload_document():
        upload = request.files.get("file")
        if upload is None:
            return _json({"error": "Ingen fil skickades."}, 400)
        # Läser en byte längre än gränsen, så att för stora filer upptäcks utan att läsa allt.
        data = upload.file.read(MAX_BYTES + 1)
        session_id = request.forms.get("session_id", "").strip()
        try:
            result = room.require_documents().add(upload.filename or "", data)
            if session_id:
                room.load_document(session_id, result["name"])
        except DocumentError as exc:
            return _json({"error": str(exc)}, 400)
        except SessionNotFound:
            return _json({"error": "Sessionen finns inte."}, 404)
        return _json({"document": result})

    return app


if __name__ == "__main__":
    run(create_app(build_room_from_env()), host="127.0.0.1", port=int(env_value("PORT", "8100")), debug=False)
