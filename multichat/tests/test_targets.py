"""Användaren väljer vilka assistenter som ska svara. @namn går alltid före valet."""

import json
import sys
from io import BytesIO
from pathlib import Path
from wsgiref.util import setup_testing_defaults

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from test_chat import call, make_room  # noqa: E402


def speakers(messages):
    return [m["speaker"] for m in messages]


def test_utan_val_svarar_bada(tmp_path):
    room, sid = make_room(tmp_path)
    assert speakers(room.send(sid, "hej", None)) == ["Du", "Ada", "Bo"]

def test_valt_bo_ger_bara_bo(tmp_path):
    room, sid = make_room(tmp_path)
    assert speakers(room.send(sid, "hej", ["Bo"])) == ["Du", "Bo"]

def test_mention_gar_fore_valet(tmp_path):
    room, sid = make_room(tmp_path)
    assert speakers(room.send(sid, "@Ada hej", ["Bo"])) == ["Du", "Ada"]

def test_tomt_val_ger_besked(tmp_path):
    room, sid = make_room(tmp_path)
    new = room.send(sid, "hej", [])
    assert new == [{"speaker": "system", "content": "Välj minst en assistent att prata med."}]

def test_okanda_namn_i_valet_ignoreras(tmp_path):
    room, sid = make_room(tmp_path)
    assert speakers(room.send(sid, "hej", ["Zed", "Ada"])) == ["Du", "Ada"]

def test_api_skickar_valet_vidare(tmp_path):
    room, sid = make_room(tmp_path)
    code, out = call(create_app(room), "POST", f"/api/sessions/{sid}/message", {"text": "hej", "selected": ["Bo"]})
    assert code == 200
    assert speakers(json.loads(out)["messages"]) == ["Du", "Bo"]

def test_api_avvisar_val_som_inte_ar_en_lista(tmp_path):
    room, sid = make_room(tmp_path)
    code, out = call(create_app(room), "POST", f"/api/sessions/{sid}/message", {"text": "hej", "selected": "Bo"})
    assert code == 400
    assert "lista" in json.loads(out)["error"]


# ── fyra assistenter och personligheter ───────────────────────

from app import MARGARETA_PERSONA, build_assistants  # noqa: E402
from chat import Assistant, ChatRoom  # noqa: E402
from store import SessionStore  # noqa: E402
from test_chat import FakeBackend  # noqa: E402


def make_four(tmp_path):
    assistants = [
        Assistant("Ada", "a"),
        Assistant("Bo", "b"),
        Assistant("Kalle", "c"),
        Assistant("Margareta", "d", persona=MARGARETA_PERSONA),
    ]
    backend = FakeBackend()
    room = ChatRoom(assistants, backend, SessionStore(tmp_path / "sessions"))
    return room, room.store.create(), backend

def test_standardval_har_fyra_assistenter():
    names = [a.name for a in build_assistants()]
    assert names == ["Ada", "Bo", "Kalle", "Margareta"]

def test_alla_svarar_alla_fyra(tmp_path):
    room, sid, _ = make_four(tmp_path)
    assert speakers(room.send(sid, "hej", None)) == ["Du", "Ada", "Bo", "Kalle", "Margareta"]

def test_personligheten_ligger_i_systemprompten(tmp_path):
    room, sid, backend = make_four(tmp_path)
    room.send(sid, "@Margareta hej", None)
    model, messages = backend.calls[-1]
    assert messages[0]["content"].startswith(MARGARETA_PERSONA)

def test_utan_personlighet_borjar_prompten_med_namnet(tmp_path):
    room, sid, backend = make_four(tmp_path)
    room.send(sid, "@Kalle hej", None)
    _, messages = backend.calls[-1]
    assert messages[0]["content"].startswith("Du heter Kalle.")


def test_alla_fyra_har_egna_personligheter():
    from app import ADA_PERSONA, BO_PERSONA, KALLE_PERSONA

    personas = {a.name: a.persona for a in build_assistants()}
    assert personas == {
        "Ada": ADA_PERSONA,
        "Bo": BO_PERSONA,
        "Kalle": KALLE_PERSONA,
        "Margareta": MARGARETA_PERSONA,
    }
    assert len(set(personas.values())) == 4
