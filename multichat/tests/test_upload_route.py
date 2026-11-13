"""Testar uppladdningen via webbappen med en riktig multipart-förfrågan."""

import json
import sys
from io import BytesIO
from pathlib import Path
from wsgiref.util import setup_testing_defaults

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from chat import Assistant, ChatRoom  # noqa: E402
from documents import MAX_BYTES, DocumentStore  # noqa: E402
from store import SessionStore  # noqa: E402

BOUNDARY = "GRÄNS123"


class NoBackend:
    def complete_with_tools(self, model, messages, tools):
        return self.complete(model, messages), []

    def complete(self, model, messages):
        return "## Test\n- fakta"


def make_app(tmp_path):
    documents = DocumentStore(tmp_path / "uploads", lambda text: "## Test\n- fakta")
    room = ChatRoom(
        [Assistant("Ada", "a"), Assistant("Bo", "b")],
        NoBackend(),
        SessionStore(tmp_path / "sessions"),
        documents=documents,
    )
    return create_app(room), tmp_path / "uploads"


def multipart(filename: str, content: bytes) -> bytes:
    head = (
        f"--{BOUNDARY}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8")
    tail = f"\r\n--{BOUNDARY}--\r\n".encode("utf-8")
    return head + content + tail


def post_file(app, filename: str, content: bytes):
    body = multipart(filename, content)
    environ = {}
    setup_testing_defaults(environ)
    environ.update(
        REQUEST_METHOD="POST",
        PATH_INFO="/api/documents",
        CONTENT_TYPE=f"multipart/form-data; boundary={BOUNDARY}",
        CONTENT_LENGTH=str(len(body)),
        **{"wsgi.input": BytesIO(body)},
    )
    status: list[str] = []

    def start_response(s, headers, exc_info=None):
        status.append(s)

    out = b"".join(app(environ, start_response))
    return int(status[0].split()[0]), json.loads(out)


def test_uppladdning_sparas_och_komprimeras(tmp_path):
    app, uploads = make_app(tmp_path)
    code, data = post_file(app, "notes.md", "# Hej\nText".encode("utf-8"))
    assert code == 200
    assert data["document"]["name"] == "notes.md"
    assert (uploads / "notes.md").exists()
    assert (uploads / "notes.md.compact.md").exists()

def test_for_stor_uppladdning_avvisas(tmp_path):
    app, uploads = make_app(tmp_path)
    code, data = post_file(app, "stor.md", b"a" * (MAX_BYTES + 10))
    assert code == 400
    assert "för stor" in data["error"]
    assert not (uploads / "stor.md").exists()

def test_fel_filtyp_avvisas(tmp_path):
    app, _ = make_app(tmp_path)
    code, data = post_file(app, "bild.pdf", b"%PDF")
    assert code == 400
    assert "stöds inte" in data["error"]
