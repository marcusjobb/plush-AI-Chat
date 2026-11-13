"""Tester för verktygen som assistenterna kan anropa. Modellen simuleras med ett manus."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chat import MAX_TOOL_ROUNDS, Assistant, ChatRoom  # noqa: E402
from documents import DocumentStore  # noqa: E402
from store import SessionStore  # noqa: E402
from tools import TOOL_SPECS  # noqa: E402


class ScriptedBackend:
    """Svarar med verktygsanrop enligt ett manus. Efter manuset svarar den med text."""

    def __init__(self, script=()):
        self.script = list(script)
        self.tool_calls_seen = []

    def complete(self, model, messages):
        return "svar"

    def complete_with_tools(self, model, messages, tools):
        self.tool_calls_seen.append(tools)
        if self.script:
            return self.script.pop(0)
        return ("klart", [])


def call(name, **arguments):
    import json

    return {"id": f"id-{name}-{len(arguments)}", "name": name, "arguments": json.dumps(arguments, ensure_ascii=False)}


def make_room(tmp_path, script=(), files=("katt.md", "hund.md")):
    docs = DocumentStore(tmp_path / "uploads", lambda text: "## Ämne\n- fakta")
    for name in files:
        docs.add(name, f"text om {name}".encode())
    backend = ScriptedBackend(script)
    room = ChatRoom(
        [Assistant("Ada", "a"), Assistant("Bo", "b")],
        backend,
        SessionStore(tmp_path / "sessions"),
        documents=docs,
    )
    return room, room.store.create(), backend


def uploads(tmp_path):
    return tmp_path / "uploads"


# ── specifikationen ───────────────────────────────────────────

def test_verktygsnamnen_ar_ascii():
    for spec in TOOL_SPECS:
        assert spec["function"]["name"].isascii(), spec["function"]["name"]

def test_alla_tio_verktyg_finns():
    names = {spec["function"]["name"] for spec in TOOL_SPECS}
    assert names == {"ladda_dokument", "las_amne", "dokument", "amnen", "prata",
                     "sok", "editera", "spara", "radera", "list_files"}


# ── sök och läsning ───────────────────────────────────────────

def test_sok_hittar_filer_med_stjarnmonster(tmp_path):
    script = [("", [call("sok", monster="*katt*")]), ("Det finns en katt-fil.", [])]
    room, sid, _ = make_room(tmp_path, script)
    new = room.send(sid, "@Ada vad står det i filen katt?")
    assert any("Sökte efter *katt*: 1 träffar" in m["content"] for m in new if m["speaker"] == "system")
    assert new[-1]["content"] == "Det finns en katt-fil."

def test_ladda_dokument_lagger_filen_i_historiken(tmp_path):
    script = [("", [call("ladda_dokument", namn="katt.md")]), ("Klart.", [])]
    room, sid, _ = make_room(tmp_path, script)
    room.send(sid, "ladda katt.md")
    assert room.store.current_document(sid) == "katt.md"

def test_las_amne_returnerar_texten_till_modellen(tmp_path):
    script = [("", [call("las_amne", fil="katt.md", amne="Ämne")]), ("Svar.", [])]
    room, sid, backend = make_room(tmp_path, script)
    room.tools.run("las_amne", {"fil": "katt.md", "amne": "Ämne"}, "", sid)
    result, row = room.tools.run("las_amne", {"fil": "katt.md", "amne": "Ämne"}, "", sid)
    assert "- fakta" in result
    assert "Läste ämnet Ämne ur katt.md" == row

def test_okant_verktyg_ger_fel_och_inget_hander(tmp_path):
    room, sid, _ = make_room(tmp_path)
    result, _ = room.tools.run("finns_inte", {}, "", sid)
    assert result.startswith("FEL")


# ── skrivning och radering kräver att filen nämns ─────────────

def test_editera_utan_filnamn_i_meddelandet_nekas(tmp_path):
    room, sid, _ = make_room(tmp_path)
    result, _ = room.tools.run("editera", {"namn": "katt.md", "fran": "text", "till": "ny"}, "fixa den", sid)
    assert "måste nämna filnamnet" in result
    assert not (uploads(tmp_path) / "katt-redigerad.md").exists()

def test_editera_med_filnamn_skapar_kopia_och_ror_inte_originalet(tmp_path):
    room, sid, _ = make_room(tmp_path)
    room.tools.run("editera", {"namn": "katt.md", "fran": "text", "till": "ny"}, "ändra katt.md", sid)
    assert (uploads(tmp_path) / "katt-redigerad.md").read_text(encoding="utf-8") == "ny om katt.md"
    assert (uploads(tmp_path) / "katt.md").read_text(encoding="utf-8") == "text om katt.md"

def test_editera_med_text_som_inte_finns_ger_fel(tmp_path):
    room, sid, _ = make_room(tmp_path)
    result, _ = room.tools.run("editera", {"namn": "katt.md", "fran": "finns inte", "till": "x"}, "katt.md", sid)
    assert "finns inte i katt.md" in result

def test_spara_skriver_aldrig_over_befintlig_fil(tmp_path):
    room, sid, _ = make_room(tmp_path)
    result, _ = room.tools.run("spara", {"namn": "katt.md", "innehall": "nytt"}, "", sid)
    assert "katt (2).md" in result
    assert (uploads(tmp_path) / "katt.md").read_text(encoding="utf-8") == "text om katt.md"
    assert (uploads(tmp_path) / "katt (2).md").exists()

def test_radera_utan_filnamn_i_meddelandet_nekas(tmp_path):
    room, sid, _ = make_room(tmp_path)
    result, _ = room.tools.run("radera", {"namn": "katt.md"}, "ta bort den", sid)
    assert "måste nämna filnamnet" in result
    assert (uploads(tmp_path) / "katt.md").exists()

def test_radera_med_filnamn_flyttar_till_papperskorgen(tmp_path):
    room, sid, _ = make_room(tmp_path)
    room.load_document(sid, "katt.md")
    room.tools.run("radera", {"namn": "katt.md"}, "radera katt.md", sid)
    assert not (uploads(tmp_path) / "katt.md").exists()
    assert list((uploads(tmp_path) / ".papperskorg").glob("*katt.md"))
    assert room.store.current_document(sid) is None

def test_radera_tar_inte_bort_nagot_permanent(tmp_path):
    room, sid, _ = make_room(tmp_path)
    room.tools.run("radera", {"namn": "katt.md"}, "radera katt.md", sid)
    trashed = list((uploads(tmp_path) / ".papperskorg").iterdir())
    assert any(p.read_text(encoding="utf-8") == "text om katt.md" for p in trashed)


# ── filsystemet stannar i uploads/ ────────────────────────────

def test_list_files_visar_undermappar_men_inte_papperskorgen(tmp_path):
    room, sid, _ = make_room(tmp_path)
    (uploads(tmp_path) / "arkiv").mkdir()
    (uploads(tmp_path) / "arkiv" / "gammal.txt").write_text("x", encoding="utf-8")
    room.tools.run("radera", {"namn": "hund.md"}, "radera hund.md", sid)
    result, _ = room.tools.run("list_files", {}, "", sid)
    assert "arkiv/gammal.txt" in result
    assert "katt.md" in result
    assert "hund.md" not in result
    assert ".papperskorg" not in result

def test_sokvagar_kan_inte_lamna_uploads(tmp_path):
    room, sid, _ = make_room(tmp_path)
    (tmp_path / "hemligt.md").write_text("hemligt", encoding="utf-8")
    result, _ = room.tools.run("ladda_dokument", {"namn": "../hemligt.md"}, "", sid)
    assert result.startswith("FEL")
    assert "hemligt" not in room.store.context(sid).__repr__()

def test_spara_med_sokvag_hamnar_i_uploads(tmp_path):
    room, sid, _ = make_room(tmp_path)
    room.tools.run("spara", {"namn": "../utanfor.md", "innehall": "x"}, "", sid)
    assert (uploads(tmp_path) / "utanfor.md").exists()
    assert not (tmp_path / "utanfor.md").exists()


# ── slingan och systemraderna ─────────────────────────────────

def test_verktygsanrop_blir_systemrader_i_chatten(tmp_path):
    script = [("", [call("sok", monster="*hund*")]), ("Svar.", [])]
    room, sid, _ = make_room(tmp_path, script)
    room.send(sid, "@Ada vilka filer finns?")
    rows = [m for m in room.history(sid) if m["speaker"] == "system"]
    assert any("Sökte efter *hund*" in m["content"] for m in rows)

def test_modellen_som_aldrig_slutar_avbryts(tmp_path):
    endless = [("", [call("list_files")])] * (MAX_TOOL_ROUNDS + 5)
    room, sid, backend = make_room(tmp_path, endless)
    new = room.send(sid, "@Ada lista")
    assert len(backend.tool_calls_seen) == MAX_TOOL_ROUNDS
    assert any("gav ett tomt svar" in m["content"] for m in new)

def test_verktygen_skickas_med_till_modellen(tmp_path):
    room, sid, backend = make_room(tmp_path)
    room.send(sid, "hej")
    assert backend.tool_calls_seen[0] == TOOL_SPECS
