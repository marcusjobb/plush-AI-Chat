"""Tester för att byta namn på sessioner."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from test_chat import call, make_room  # noqa: E402


def test_nytt_namn_visas_i_listan(tmp_path):
    room, sid = make_room(tmp_path)
    room.send(sid, "@Ada hej")
    room.store.set_title(sid, "Resplanering")
    titles = {s["id"]: s["title"] for s in room.store.list_sessions()}
    assert titles[sid] == "Resplanering"

def test_senaste_namnet_galler(tmp_path):
    room, sid = make_room(tmp_path)
    room.store.set_title(sid, "Först")
    room.store.set_title(sid, "Sen")
    titles = {s["id"]: s["title"] for s in room.store.list_sessions()}
    assert titles[sid] == "Sen"

def test_utan_eget_namn_visas_forsta_meddelandet(tmp_path):
    room, sid = make_room(tmp_path)
    room.send(sid, "hur sparar jag?")
    titles = {s["id"]: s["title"] for s in room.store.list_sessions()}
    assert titles[sid] == "hur sparar jag?"

def test_namnbyte_visas_inte_i_samtalet(tmp_path):
    room, sid = make_room(tmp_path)
    room.store.set_title(sid, "Resplanering")
    assert room.history(sid) == []

def test_api_byter_namn(tmp_path):
    room, sid = make_room(tmp_path)
    app = create_app(room)
    code, _ = call(app, "POST", f"/api/sessions/{sid}/title", {"title": "Ny titel"})
    assert code == 200
    titles = {s["id"]: s["title"] for s in room.store.list_sessions()}
    assert titles[sid] == "Ny titel"

def test_api_tomt_namn_avvisas(tmp_path):
    room, sid = make_room(tmp_path)
    code, out = call(create_app(room), "POST", f"/api/sessions/{sid}/title", {"title": "   "})
    assert code == 400
    assert "tomt" in json.loads(out)["error"]

def test_api_okand_session_ger_404(tmp_path):
    room, _ = make_room(tmp_path)
    code, _ = call(create_app(room), "POST", "/api/sessions/finns-inte/title", {"title": "X"})
    assert code == 404
