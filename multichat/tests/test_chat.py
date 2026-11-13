"""Tester för routing, sessioner, komprimering och webbappen. Ingen nätverkskontakt krävs."""

import json
import sys
from io import BytesIO
from pathlib import Path
from wsgiref.util import setup_testing_defaults

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from chat import Assistant, ChatRoom, UnknownAssistant, parse_message, sanitize  # noqa: E402
from store import SUMMARY, SessionNotFound, SessionStore  # noqa: E402

NAMES = ["Ada", "Bo"]


class FakeBackend:
    """Svarar med ett fast svar per modell och sparar alla anrop."""

    def __init__(self, replies=None, fail_for=(), summary="- kort sammanfattning"):
        self.replies = replies or {}
        self.fail_for = set(fail_for)
        self.summary = summary
        self.calls: list[tuple[str, list[dict[str, str]]]] = []

    def complete_with_tools(self, model, messages, tools):
        return self.complete(model, messages), []

    def complete(self, model, messages):
        self.calls.append((model, messages))
        if model in self.fail_for:
            raise RuntimeError("nyckeln är ogiltig")
        if messages and messages[0]["content"].startswith("Sammanfatta"):
            return self.summary
        return self.replies.get(model, f"svar från {model}")


def make_room(tmp_path, backend=None, window=20, auto_compact_at=50):
    assistants = [Assistant("Ada", "model-a"), Assistant("Bo", "model-b")]
    store = SessionStore(tmp_path / "sessions")
    room = ChatRoom(
        assistants,
        backend or FakeBackend(),
        store,
        window=window,
        auto_compact_at=auto_compact_at,
    )
    return room, store.create()


# ── parse_message ─────────────────────────────────────────────

def test_utan_mention_gar_till_alla():
    assert parse_message("hej alla", NAMES) == (["Ada", "Bo"], "hej alla")

def test_mention_gar_bara_till_en_och_tas_bort_ur_texten():
    assert parse_message("@Bo vad tycker du?", NAMES) == (["Bo"], "vad tycker du?")

def test_mention_ar_skiftlageskansligt():
    assert parse_message("@ada hej", NAMES) == (["Ada"], "hej")

def test_okant_namn_kastar_fel():
    with pytest.raises(UnknownAssistant, match="Zed"):
        parse_message("@Zed hej", NAMES)

def test_at_mitt_i_texten_raknas_inte_som_mention():
    assert parse_message("mejla mig @ jobbet", NAMES) == (["Ada", "Bo"], "mejla mig @ jobbet")


# ── sanitize ──────────────────────────────────────────────────

def test_sanitize_tar_bort_at_tecken():
    assert sanitize("@Ada tycker att @Bo har rätt", ["Ada", "Bo"]) == "@Ada tycker att @Bo har rätt"


# ── samtalsflöde ──────────────────────────────────────────────

def test_utan_mention_svarar_bada_i_ordning(tmp_path):
    room, sid = make_room(tmp_path)
    new = room.send(sid, "hej")
    assert [m["speaker"] for m in new] == ["Du", "Ada", "Bo"]

def test_med_mention_svarar_bara_den_namngda(tmp_path):
    room, sid = make_room(tmp_path)
    new = room.send(sid, "@Bo hej")
    assert [m["speaker"] for m in new] == ["Du", "Bo"]
    assert new[0]["content"] == "@Bo hej"

def test_andra_assistenten_ser_forsta_svaret(tmp_path):
    backend = FakeBackend(replies={"model-a": "Ada säger hej"})
    room, sid = make_room(tmp_path, backend)
    room.send(sid, "hej")
    model, messages = backend.calls[-1]
    assert model == "model-b"
    assert {"role": "user", "content": "Ada: Ada säger hej"} in messages

def test_svar_med_at_tecken_saneras(tmp_path):
    backend = FakeBackend(replies={"model-a": "@Du bör sova mer"})
    room, sid = make_room(tmp_path, backend)
    new = room.send(sid, "@Ada tips?")
    assert new[-1]["content"] == "Du bör sova mer"

def test_fel_i_ett_anrop_visas_som_systemmeddelande(tmp_path):
    room, sid = make_room(tmp_path, FakeBackend(fail_for={"model-a"}))
    new = room.send(sid, "hej")
    assert new[1]["speaker"] == "system"
    assert "Ada kunde inte svara" in new[1]["content"]
    assert new[2]["speaker"] == "Bo"

def test_tomt_meddelande_ger_inget_svar(tmp_path):
    backend = FakeBackend()
    room, sid = make_room(tmp_path, backend)
    assert room.send(sid, "   ") == []
    assert backend.calls == []

def test_bara_senaste_fonstret_skickas(tmp_path):
    backend = FakeBackend()
    room, sid = make_room(tmp_path, backend, window=4)
    for i in range(10):
        room.send(sid, f"@Ada meddelande {i}")
    _, messages = backend.calls[-1]
    assert len(messages) == 1 + 4  # systemprompt + fönstret

def test_unika_namn_kravs(tmp_path):
    with pytest.raises(ValueError):
        ChatRoom([Assistant("Ada", "a"), Assistant("ada", "b")], FakeBackend(), SessionStore(tmp_path))


# ── sessioner ─────────────────────────────────────────────────

def test_sessioner_hålls_isär(tmp_path):
    room, first = make_room(tmp_path)
    second = room.store.create()
    room.send(first, "@Ada i första")
    room.send(second, "@Bo i andra")
    assert [m["content"] for m in room.history(first) if m["speaker"] == "Du"] == ["@Ada i första"]
    assert [m["content"] for m in room.history(second) if m["speaker"] == "Du"] == ["@Bo i andra"]

def test_historiken_finns_kvar_efter_ny_instans(tmp_path):
    room, sid = make_room(tmp_path)
    room.send(sid, "@Ada hej")
    reloaded = ChatRoom(room.assistants, FakeBackend(), SessionStore(tmp_path / "sessions"))
    assert [m["speaker"] for m in reloaded.history(sid)] == ["Du", "Ada"]

def test_okand_session_ger_fel(tmp_path):
    room, _ = make_room(tmp_path)
    with pytest.raises(SessionNotFound):
        room.send("finns-inte", "hej")

def test_ogiltigt_sessionsid_ger_fel(tmp_path):
    room, _ = make_room(tmp_path)
    with pytest.raises(SessionNotFound):
        room.history("../hemligt")

def test_list_sessions_visar_forsta_meddelandet_som_titel(tmp_path):
    room, sid = make_room(tmp_path)
    room.send(sid, "hur sparar jag pengar?")
    titles = {s["id"]: s["title"] for s in room.store.list_sessions()}
    assert titles[sid] == "hur sparar jag pengar?"


# ── komprimering ──────────────────────────────────────────────

def test_manuell_compact_sparar_sammanfattning(tmp_path):
    backend = FakeBackend(summary="- Användaren sparar till resa")
    room, sid = make_room(tmp_path, backend)
    room.send(sid, "@Ada jag vill spara till en resa")
    result = room.compact(sid)
    assert result["content"] == "Samtalet komprimerades."
    assert room.store.context(sid)[0] == {"speaker": SUMMARY, "content": "- Användaren sparar till resa"}

def test_efter_compact_skickas_sammanfattningen_och_inte_de_gamla_turerna(tmp_path):
    backend = FakeBackend(summary="- sammanfattning")
    room, sid = make_room(tmp_path, backend)
    room.send(sid, "@Ada gammalt meddelande")
    room.compact(sid)
    room.send(sid, "@Ada nytt meddelande")
    _, messages = backend.calls[-1]
    contents = [m["content"] for m in messages]
    assert any("sammanfattning" in c for c in contents)
    assert not any("gammalt meddelande" in c for c in contents)

def test_compact_utan_innehall_ger_besked(tmp_path):
    backend = FakeBackend()
    room, sid = make_room(tmp_path, backend)
    result = room.compact(sid)
    assert "inget att komprimera" in result["content"]
    assert backend.calls == []

def test_compact_fel_sparas_inte(tmp_path):
    backend = FakeBackend(summary="")
    room, sid = make_room(tmp_path, backend)
    room.send(sid, "@Ada hej")
    result = room.compact(sid)
    assert "tomt svar" in result["content"]
    assert room.store.context(sid)[0]["speaker"] != SUMMARY

def test_automatisk_compact_efter_50_meddelanden(tmp_path):
    backend = FakeBackend(summary="- auto")
    room, sid = make_room(tmp_path, backend, auto_compact_at=6)
    for _ in range(3):
        room.send(sid, "@Ada hej")  # varje tur ger 2 meddelanden: 6 totalt
    assert room.store.context(sid)[0]["speaker"] != SUMMARY
    room.send(sid, "@Ada hej igen")  # fjärde turen startar med komprimering
    assert room.store.context(sid)[0]["speaker"] == SUMMARY

def test_automatisk_compact_meddelas_i_chatten(tmp_path):
    room, sid = make_room(tmp_path, auto_compact_at=2)
    room.send(sid, "@Ada hej")
    new = room.send(sid, "@Ada igen")
    assert new[0] == {"speaker": "system", "content": "Samtalet komprimerades."}

def test_turns_since_compact_nollstalls(tmp_path):
    room, sid = make_room(tmp_path)
    room.send(sid, "@Ada hej")
    assert room.store.turns_since_compact(sid) == 2
    room.compact(sid)
    assert room.store.turns_since_compact(sid) == 0


# ── webbappen ─────────────────────────────────────────────────

def call(app, method, path, body=None):
    environ = {}
    setup_testing_defaults(environ)
    data = json.dumps(body).encode() if body is not None else b""
    environ.update(
        REQUEST_METHOD=method,
        PATH_INFO=path,
        CONTENT_TYPE="application/json",
        CONTENT_LENGTH=str(len(data)),
        **{"wsgi.input": BytesIO(data)},
    )
    status: list[str] = []

    def start_response(s, headers, exc_info=None):
        status.append(s)

    out = b"".join(app(environ, start_response))
    return int(status[0].split()[0]), out

def test_api_skapa_och_lista_session(tmp_path):
    app = create_app(make_room(tmp_path)[0])
    code, out = call(app, "POST", "/api/sessions")
    assert code == 200
    sid = json.loads(out)["id"]
    code, out = call(app, "GET", "/api/sessions")
    assert sid in [s["id"] for s in json.loads(out)["sessions"]]

def test_api_meddelande_i_session(tmp_path):
    room, sid = make_room(tmp_path)
    app = create_app(room)
    code, out = call(app, "POST", f"/api/sessions/{sid}/message", {"text": "@Ada hej"})
    assert code == 200
    assert [m["speaker"] for m in json.loads(out)["messages"]] == ["Du", "Ada"]

def test_api_okand_session_ger_404(tmp_path):
    app = create_app(make_room(tmp_path)[0])
    code, _ = call(app, "GET", "/api/sessions/finns-inte")
    assert code == 404

def test_api_okant_namn_ger_400(tmp_path):
    room, sid = make_room(tmp_path)
    code, out = call(create_app(room), "POST", f"/api/sessions/{sid}/message", {"text": "@Zed hej"})
    assert code == 400
    assert "Zed" in json.loads(out)["error"]

def test_api_compact(tmp_path):
    room, sid = make_room(tmp_path)
    room.send(sid, "@Ada hej")
    code, out = call(create_app(room), "POST", f"/api/sessions/{sid}/compact")
    assert code == 200
    assert json.loads(out)["message"]["content"] == "Samtalet komprimerades."

def test_api_info(tmp_path):
    app = create_app(make_room(tmp_path)[0])
    code, out = call(app, "GET", "/api/info")
    assert [a["name"] for a in json.loads(out)["assistants"]] == ["Ada", "Bo"]

def test_startsida_finns(tmp_path):
    app = create_app(make_room(tmp_path)[0])
    code, out = call(app, "GET", "/")
    assert code == 200
    assert b"<select" in out


def test_namnprefix_i_svaret_tas_bort(tmp_path):
    backend = FakeBackend(replies={"model-a": "Ada: hej där"})
    room, sid = make_room(tmp_path, backend)
    new = room.send(sid, "@Ada hej")
    assert new[-1]["content"] == "hej där"

def test_andra_namn_som_prefix_tas_bort(tmp_path):
    backend = FakeBackend(replies={"model-b": "Ada: Bo svarar"})
    room, sid = make_room(tmp_path, backend)
    new = room.send(sid, "@Bo hej")
    assert new[-1]["content"] == "Bo svarar"


def test_gamla_svar_med_namnprefix_visas_utan_prefix(tmp_path):
    room, sid = make_room(tmp_path)
    room.store.add(sid, "Ada", "Bo: Tack så mycket!")
    assert room.history(sid)[-1]["content"] == "Tack så mycket!"
