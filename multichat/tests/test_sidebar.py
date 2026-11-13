"""Tester för dokumentlistan i sidopanelen (GET /api/documents)."""

import json
import sys
from io import BytesIO
from pathlib import Path
from wsgiref.util import setup_testing_defaults

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from chat import Assistant, ChatRoom  # noqa: E402
from documents import DocumentStore  # noqa: E402
from store import SessionStore  # noqa: E402
from test_chat import FakeBackend  # noqa: E402

COMPACT = "## Budget\n- 500 kr i veckan"


def make_room(tmp_path):
    docs = DocumentStore(tmp_path / "uploads", lambda text: COMPACT)
    docs.add("b.md", b"text")
    docs.add("a.md", b"text")
    room = ChatRoom(
        [Assistant("Ada", "a"), Assistant("Bo", "b")],
        FakeBackend(),
        SessionStore(tmp_path / "sessions"),
        documents=docs,
    )
    return room, room.store.create()


def get_documents(app, query=""):
    environ = {}
    setup_testing_defaults(environ)
    environ.update(
        REQUEST_METHOD="GET",
        PATH_INFO="/api/documents",
        QUERY_STRING=query.lstrip("?"),
        CONTENT_LENGTH="0",
        **{"wsgi.input": BytesIO(b"")},
    )
    status: list[str] = []

    def start_response(s, headers, exc_info=None):
        status.append(s)

    out = b"".join(app(environ, start_response))
    return int(status[0].split()[0]), json.loads(out)


def test_listar_alla_dokument_sorterade(tmp_path):
    room, _ = make_room(tmp_path)
    code, data = get_documents(create_app(room))
    assert code == 200
    assert data["documents"] == ["a.md", "b.md"]
    assert data["current"] is None

def test_aktivt_dokument_visas_for_sessionen(tmp_path):
    room, sid = make_room(tmp_path)
    room.load_document(sid, "b.md")
    code, data = get_documents(create_app(room), f"?session_id={sid}")
    assert code == 200
    assert data["current"] == "b.md"

def test_aktivt_dokument_ar_per_session(tmp_path):
    room, sid = make_room(tmp_path)
    other = room.store.create()
    room.load_document(sid, "b.md")
    _, data = get_documents(create_app(room), f"?session_id={other}")
    assert data["current"] is None

def test_borttaget_dokument_ar_inte_aktivt(tmp_path):
    room, sid = make_room(tmp_path)
    room.load_document(sid, "b.md")
    room.store.add_document(sid, None)
    _, data = get_documents(create_app(room), f"?session_id={sid}")
    assert data["current"] is None

def test_okand_session_ger_404(tmp_path):
    room, _ = make_room(tmp_path)
    code, _ = get_documents(create_app(room), "?session_id=finns-inte")
    assert code == 404


def get_path(app, path):
    environ = {}
    setup_testing_defaults(environ)
    environ.update(REQUEST_METHOD="GET", PATH_INFO=path, CONTENT_LENGTH="0", **{"wsgi.input": BytesIO(b"")})
    status: list[str] = []

    def start_response(s, headers, exc_info=None):
        status.append(s)

    out = b"".join(app(environ, start_response))
    return int(status[0].split()[0]), json.loads(out)


def test_dokument_visas_i_original_och_komprimerad_version(tmp_path):
    room, _ = make_room(tmp_path)
    code, data = get_path(create_app(room), "/api/documents/a.md")
    assert code == 200
    assert data["name"] == "a.md"
    assert data["original"] == "text"
    assert data["compact"] == COMPACT

def test_okant_dokument_ger_404(tmp_path):
    room, _ = make_room(tmp_path)
    code, data = get_path(create_app(room), "/api/documents/finns-inte.md")
    assert code == 404
    assert "finns inte" in data["error"]


def delete_path(app, path):
    route, _, query = path.partition("?")
    environ = {}
    setup_testing_defaults(environ)
    environ.update(REQUEST_METHOD="DELETE", PATH_INFO=route, QUERY_STRING=query, CONTENT_LENGTH="0", **{"wsgi.input": BytesIO(b"")})
    status: list[str] = []

    def start_response(s, headers, exc_info=None):
        status.append(s)

    out = b"".join(app(environ, start_response))
    return int(status[0].split()[0]), json.loads(out)


def test_radera_flyttar_till_papperskorgen_och_slapper_fran_sessionen(tmp_path):
    room, sid = make_room(tmp_path)
    room.load_document(sid, "b.md")
    code, data = delete_path(create_app(room), f"/api/documents/b.md?session_id={sid}")
    assert code == 200
    assert not (tmp_path / "uploads" / "b.md").exists()
    assert list((tmp_path / "uploads" / ".papperskorg").glob("*b.md"))
    assert room.store.current_document(sid) is None

def test_radera_okand_fil_ger_404(tmp_path):
    room, _ = make_room(tmp_path)
    code, data = delete_path(create_app(room), "/api/documents/finns-inte.md")
    assert code == 404

def test_radera_med_okand_session_ger_404(tmp_path):
    room, _ = make_room(tmp_path)
    code, _ = delete_path(create_app(room), "/api/documents/a.md?session_id=finns-inte")
    assert code == 404
    assert (tmp_path / "uploads" / "a.md").exists()


def post_json(app, path, body):
    data = json.dumps(body).encode("utf-8")
    environ = {}
    setup_testing_defaults(environ)
    environ.update(REQUEST_METHOD="POST", PATH_INFO=path, CONTENT_TYPE="application/json", CONTENT_LENGTH=str(len(data)), **{"wsgi.input": BytesIO(data)})
    status: list[str] = []

    def start_response(s, headers, exc_info=None):
        status.append(s)

    out = b"".join(app(environ, start_response))
    return int(status[0].split()[0]), json.loads(out)


def test_spara_kopia_skapar_ny_fil_och_ror_inte_originalet(tmp_path):
    room, _ = make_room(tmp_path)
    code, data = post_json(create_app(room), "/api/documents/save", {"name": "a-redigerad.md", "text": "ny text"})
    assert code == 200
    assert data["document"]["name"] == "a-redigerad.md"
    assert (tmp_path / "uploads" / "a.md").read_text(encoding="utf-8") == "text"
    assert (tmp_path / "uploads" / "a-redigerad.md").read_text(encoding="utf-8") == "ny text"

def test_spara_kopia_med_befintligt_namn_far_nytt_namn(tmp_path):
    room, _ = make_room(tmp_path)
    code, data = post_json(create_app(room), "/api/documents/save", {"name": "a.md", "text": "ny"})
    assert code == 200
    assert data["document"]["name"] == "a (2).md"
    assert (tmp_path / "uploads" / "a.md").read_text(encoding="utf-8") == "text"

def test_spara_kopia_utan_namn_ger_400(tmp_path):
    room, _ = make_room(tmp_path)
    code, _ = post_json(create_app(room), "/api/documents/save", {"name": "  ", "text": "x"})
    assert code == 400
