"""Tester för dokumentlagret: validering, komprimering, ämnen och kommandon i chatten."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chat import Assistant, ChatRoom  # noqa: E402
from documents import (  # noqa: E402
    MAX_BYTES,
    DocumentError,
    DocumentStore,
    split_topics,
    validate_content,
    validate_name,
)
from store import SessionStore  # noqa: E402

def _all(messages):
    """All text som skickas till modellen, för påståenden om dokumentinnehåll."""
    return " ".join(m["content"] for m in messages)


COMPACT_TEXT = "## Budget\n- Max 500 kr i veckan\n## Resa\n- Resan går till Paris"


class FakeBackend:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls: list[tuple[str, list[dict[str, str]]]] = []

    def complete_with_tools(self, model, messages, tools):
        return self.complete(model, messages), []

    def complete(self, model, messages):
        self.calls.append((model, messages))
        if self.fail:
            raise RuntimeError("API nere")
        if messages[0]["content"].startswith("Gör om dokumentet"):
            return COMPACT_TEXT
        return "svar"


def make_documents(tmp_path, compress_result=COMPACT_TEXT, fail=False):
    def compress(text):
        if fail:
            raise DocumentError("Komprimeringen misslyckades: API nere")
        return compress_result

    return DocumentStore(tmp_path / "uploads", compress)


def make_room(tmp_path, documents=None, backend=None):
    assistants = [Assistant("Ada", "model-a"), Assistant("Bo", "model-b")]
    backend = backend or FakeBackend()
    room = ChatRoom(
        assistants,
        backend,
        SessionStore(tmp_path / "sessions"),
        documents=documents,
    )
    return room, room.store.create(), backend


# ── namn och innehåll ─────────────────────────────────────────

@pytest.mark.parametrize(
    "name",
    [
        "notes.md", "anteckningar.txt", "data.JSON", "Mötes anteckningar.md",
        "kontakter.csv", "kalender.ics", "visitkort.vcf", "rapport.xml",
        "config.yaml", "config.yml", "server.log", "tabell.tsv",
    ],
)
def test_tillatna_filnamn(name):
    assert validate_name(name) == name

@pytest.mark.parametrize("name", ["bild.pdf", "kod.py", "", "fil.compact.md", ".dold.md", "data.exe"])
def test_ogiltiga_filnamn(name):
    with pytest.raises(DocumentError):
        validate_name(name)

def test_sokvag_tas_bort_ur_namnet():
    assert validate_name("../hemligt/notes.md") == "notes.md"

def test_for_stor_fil_avvisas():
    with pytest.raises(DocumentError, match="för stor"):
        validate_content("stor.md", b"a" * (MAX_BYTES + 1))

def test_precis_maxstorlek_godkanns():
    assert validate_content("ok.md", b"a" * MAX_BYTES) == "a" * MAX_BYTES

def test_binarfil_avvisas_aven_med_textfilandelse():
    with pytest.raises(DocumentError, match="binärfil"):
        validate_content("fejk.csv", b"namn,pris\n\x00\x01\x02,10")

def test_csv_och_ics_med_svenska_tecken_godkanns():
    csv_text = "namn,stad\nÅsa,Göteborg\n"
    ics_text = "BEGIN:VCALENDAR\nSUMMARY:Möte\nEND:VCALENDAR\n"
    assert validate_content("a.csv", csv_text.encode()) == csv_text
    assert validate_content("b.ics", ics_text.encode()) == ics_text

def test_icke_utf8_avvisas():
    with pytest.raises(DocumentError, match="UTF-8"):
        validate_content("fel.txt", b"\xff\xfe\xfd")


# ── uppladdning ───────────────────────────────────────────────

def test_add_sparar_original_och_komprimerad_version(tmp_path):
    docs = make_documents(tmp_path)
    result = docs.add("notes.md", "# Hej\nDetta är en test".encode())
    assert result == {"name": "notes.md", "topics": ["Budget", "Resa"]}
    assert (tmp_path / "uploads" / "notes.md").exists()
    assert (tmp_path / "uploads" / "notes.md.compact.md").read_text(encoding="utf-8") == COMPACT_TEXT

def test_add_utan_rubriker_far_en_rubrik(tmp_path):
    docs = make_documents(tmp_path, compress_result="- Bara en punkt")
    docs.add("kort.txt", b"text")
    assert docs.topics("kort.txt") == ["kort"]

def test_for_stor_fil_sparas_inte(tmp_path):
    docs = make_documents(tmp_path)
    with pytest.raises(DocumentError):
        docs.add("stor.md", b"a" * (MAX_BYTES + 1))
    assert not (tmp_path / "uploads" / "stor.md").exists()

def test_misslyckad_komprimering_sparar_ingenting(tmp_path):
    docs = make_documents(tmp_path, fail=True)
    with pytest.raises(DocumentError, match="Komprimeringen"):
        docs.add("notes.md", b"text")
    assert not (tmp_path / "uploads" / "notes.md").exists()
    assert not (tmp_path / "uploads" / "notes.md.compact.md").exists()

def test_list_visar_bara_original(tmp_path):
    docs = make_documents(tmp_path)
    docs.add("a.md", b"text")
    docs.add("b.json", b"{}")
    assert docs.list_documents() == ["a.md", "b.json"]


# ── ämnen ─────────────────────────────────────────────────────

def test_split_topics():
    assert split_topics(COMPACT_TEXT) == {
        "Budget": "- Max 500 kr i veckan",
        "Resa": "- Resan går till Paris",
    }

def test_topic_text_returnerar_avsnittet(tmp_path):
    docs = make_documents(tmp_path)
    docs.add("notes.md", b"text")
    assert docs.topic_text("notes.md", "resa") == "## Resa\n- Resan går till Paris"

def test_okant_amne_ger_fel(tmp_path):
    docs = make_documents(tmp_path)
    docs.add("notes.md", b"text")
    with pytest.raises(DocumentError, match="finns inte"):
        docs.topic_text("notes.md", "Sport")

def test_okant_dokument_ger_fel(tmp_path):
    docs = make_documents(tmp_path)
    with pytest.raises(DocumentError, match="finns inte"):
        docs.topics("saknas.md")


# ── kommandon i chatten ───────────────────────────────────────

@pytest.fixture
def docs_room(tmp_path):
    docs = make_documents(tmp_path)
    docs.add("notes.md", b"text")
    return make_room(tmp_path, documents=docs)

def test_dokument_listar_uppladdade(docs_room):
    room, sid, _ = docs_room
    new = room.send(sid, "/dokument")
    assert "notes.md" in new[0]["content"]

def test_dokument_utan_uppladdningar(tmp_path):
    docs = make_documents(tmp_path)
    room, sid, _ = make_room(tmp_path, documents=docs)
    assert "Inga dokument" in room.send(sid, "/dokument")[0]["content"]

def test_amnen_listar_rubriker(docs_room):
    room, sid, _ = docs_room
    content = room.send(sid, "/ämnen notes.md")[0]["content"]
    assert "- Budget" in content and "- Resa" in content

def test_prata_skickar_bara_valt_amne_till_modellen(docs_room):
    room, sid, backend = docs_room
    room.send(sid, "/prata notes.md Resa")
    assert backend.calls == []  # själva valet kallar inte modellen
    room.send(sid, "@Ada vart går resan?")
    _, messages = backend.calls[-1]
    system = _all(messages)
    assert "Resan går till Paris" in system
    assert "500 kr" not in system

def test_valt_amne_sparas_inte_i_samtalet(docs_room):
    room, sid, _ = docs_room
    room.send(sid, "/prata notes.md Resa")
    room.send(sid, "@Ada vart går resan?")
    texts = " ".join(m["content"] for m in room.history(sid))
    assert "Paris" not in texts

def test_dokument_lases_inte_utan_begaran(docs_room):
    room, sid, backend = docs_room
    room.send(sid, "@Ada hej, hur mår du?")
    for _, messages in backend.calls:
        assert "Paris" not in _all(messages)
        assert "500 kr" not in _all(messages)

def test_prata_av_slapper_amnet(docs_room):
    room, sid, backend = docs_room
    room.send(sid, "/prata notes.md Resa")
    room.send(sid, "/prata av")
    room.send(sid, "@Ada hej")
    _, messages = backend.calls[-1]
    assert "Paris" not in _all(messages)

def test_prata_med_okant_amne_ger_fel(docs_room):
    room, sid, _ = docs_room
    result = room.send(sid, "/prata notes.md Sport")
    assert "finns inte" in result[0]["content"]
    assert room.store.active_topic(sid) is None

def test_okant_kommando_ger_hjalp(docs_room):
    room, sid, _ = docs_room
    assert "Kommandon" in room.send(sid, "/hjälp")[0]["content"]

def test_kommando_utan_dokument_aktiverade_ger_fel(tmp_path):
    room, sid, _ = make_room(tmp_path, documents=None)
    assert "inte aktiverade" in room.send(sid, "/dokument")[0]["content"]

def test_vanlig_text_fungerar_utan_dokument(tmp_path):
    room, sid, _ = make_room(tmp_path, documents=None)
    new = room.send(sid, "@Ada hej")
    assert [m["speaker"] for m in new] == ["Du", "Ada"]


# ── fråga om ett dokument med vanlig text ─────────────────────

def test_nämnt_filnamn_laser_dokumentet_for_meddelandet(docs_room):
    room, sid, backend = docs_room
    room.send(sid, "vad står det i notes.md om resan?")
    _, messages = backend.calls[-1]
    assert "Resan går till Paris" in _all(messages)

def test_filen_med_en_enda_uppladdning_laser_den(docs_room):
    room, sid, backend = docs_room
    room.send(sid, "vad är det för projekt i filen?")
    _, messages = backend.calls[-1]
    assert "Resan går till Paris" in _all(messages)

def test_dokumentet_sparas_inte_i_samtalet(docs_room):
    room, sid, _ = docs_room
    room.send(sid, "vad står det i notes.md om resan?")
    texts = " ".join(m["content"] for m in room.history(sid))
    assert "Paris" not in texts

def test_filen_med_flera_uppladdningar_laser_ingen(tmp_path):
    docs = make_documents(tmp_path)
    docs.add("a.md", b"text")
    docs.add("b.md", b"text")
    room, sid, backend = make_room(tmp_path, documents=docs)
    room.send(sid, "vad är det för projekt i filen?")
    _, messages = backend.calls[-1]
    assert "Resan går till Paris" not in _all(messages)

def test_vanligt_meddelande_utan_filnamn_laser_inget(docs_room):
    room, sid, backend = docs_room
    room.send(sid, "@Ada vad tycker du om resor?")
    _, messages = backend.calls[-1]
    assert "Resan går till Paris" not in _all(messages)

def test_utan_dokument_forklarar_assistenten_hur_man_gor(tmp_path):
    room, sid, backend = make_room(tmp_path, documents=None)
    room.send(sid, "@Ada hej")
    _, messages = backend.calls[-1]
    assert "/prata" in messages[0]["content"]


# ── aktuell fil efter uppladdning ─────────────────────────────

def test_aktuell_fil_las_nar_anvandaren_sager_filen(tmp_path):
    docs = make_documents(tmp_path)
    docs.add("a.md", b"text")
    docs.add("b.md", b"text")
    room, sid, backend = make_room(tmp_path, documents=docs)
    room.load_document(sid, "b.md")
    room.send(sid, "vad är det för projekt i filen?")
    _, messages = backend.calls[-1]
    assert "Resan går till Paris" in _all(messages)

def test_uppladdning_ger_systemrad_till_assistenterna(tmp_path):
    docs = make_documents(tmp_path)
    docs.add("a.md", b"text")
    docs.add("b.md", b"text")
    room, sid, backend = make_room(tmp_path, documents=docs)
    room.store.add_document(sid, "b.md")
    room.send(sid, "@Ada hej")
    _, messages = backend.calls[-1]
    assert "laddade senast upp b.md" in messages[0]["content"]
    assert "a.md, b.md" in messages[0]["content"]

def test_prompten_pastar_inte_att_filer_ar_otillgangliga(tmp_path):
    room, sid, backend = make_room(tmp_path, documents=None)
    room.send(sid, "@Ada vad står i filen?")
    _, messages = backend.calls[-1]
    assert "Du kan inte se" not in messages[0]["content"]
    assert "Hitta aldrig på innehåll" in messages[0]["content"]

def test_verktygen_finns_i_systemprompten(tmp_path):
    room, sid, backend = make_room(tmp_path, documents=None)
    room.send(sid, "@Ada hej")
    _, messages = backend.calls[-1]
    prompt = messages[0]["content"]
    for command in ("/dokument", "/ämnen <fil>", "/prata <fil> <ämne>", "/prata av"):
        assert command in prompt

def test_uppladdning_visas_inte_i_chatten(tmp_path):
    docs = make_documents(tmp_path)
    docs.add("a.md", b"text")
    room, sid, _ = make_room(tmp_path, documents=docs)
    room.store.add_document(sid, "a.md")
    assert room.history(sid) == []

def test_utan_uppladdning_ingen_systemrad(tmp_path):
    docs = make_documents(tmp_path)
    docs.add("a.md", b"text")
    room, sid, backend = make_room(tmp_path, documents=docs)
    room.send(sid, "@Ada hej")
    _, messages = backend.calls[-1]
    assert "laddade upp" not in messages[0]["content"]


# ── dokument i historiken ─────────────────────────────────────

def test_dokument_kommando_laddar_filen_i_historiken(docs_room):
    room, sid, backend = docs_room
    result = room.send(sid, "/dokument notes.md")
    assert "ligger nu i historiken" in result[0]["content"]
    room.send(sid, "@Ada vart går resan?")
    _, messages = backend.calls[-1]
    system_entries = [m for m in messages if m["role"] == "system" and "---dokument notes.md---" in m["content"]]
    assert system_entries
    assert "Resan går till Paris" in system_entries[0]["content"]

def test_dokumentet_galler_tills_nasta_fil_laddas(tmp_path):
    docs = make_documents(tmp_path)
    docs.add("a.md", b"text")
    docs.add("b.md", b"text")
    room, sid, backend = make_room(tmp_path, documents=docs)
    room.send(sid, "/dokument a.md")
    room.send(sid, "/dokument b.md")
    room.send(sid, "@Ada hej")
    _, messages = backend.calls[-1]
    contents = _all(messages)
    assert "---dokument b.md---" in contents
    assert "---dokument a.md---" not in contents

def test_dokument_av_tar_bort_filen(docs_room):
    room, sid, backend = docs_room
    room.send(sid, "/dokument notes.md")
    room.send(sid, "/dokument av")
    room.send(sid, "@Ada hej")
    _, messages = backend.calls[-1]
    assert "---dokument" not in _all(messages)

def test_laddat_dokument_visas_inte_i_chatten(docs_room):
    room, sid, _ = docs_room
    room.send(sid, "/dokument notes.md")
    texts = " ".join(m["content"] for m in room.history(sid))
    assert "Paris" not in texts

def test_dokumentet_ingar_inte_i_komprimeringen(docs_room):
    room, sid, backend = docs_room
    room.send(sid, "/dokument notes.md")
    room.send(sid, "@Ada hej")
    room.send(sid, "@Bo hej igen")
    room.compact(sid)
    compact_call = backend.calls[-1]
    assert "Resan går till Paris" not in _all(compact_call[1])


# ── granskningsfixar: filer med samma stam, dubbla rubriker, gamla filnamn ──

def test_filer_med_samma_stam_far_egna_komprimerade_versioner(tmp_path):
    docs = DocumentStore(tmp_path / "uploads", lambda text: f"## Innehåll\n{text}")
    docs.add("notes.md", b"fran md")
    docs.add("notes.txt", b"fran txt")
    assert docs.document_text("notes.md") == "## Innehåll\nfran md"
    assert docs.document_text("notes.txt") == "## Innehåll\nfran txt"

def test_dubbla_rubriker_slas_ihop_utan_att_forlora_avsnitt():
    topics = split_topics("## Budget\n- A\n## Resa\n- X\n## Budget\n- B")
    assert topics["Budget"] == "- A\n- B"
    assert topics["Resa"] == "- X"

def test_gammal_komprimerad_fil_lases_nar_filen_ar_ensam_med_sin_stam(tmp_path):
    folder = tmp_path / "uploads"
    folder.mkdir()
    (folder / "2026-07.md").write_bytes(b"original")
    (folder / "2026-07.compact.md").write_text("## Gammalt\n- fakta", encoding="utf-8")
    docs = DocumentStore(folder, lambda text: text)
    assert docs.topics("2026-07.md") == ["Gammalt"]

def test_gammal_komprimerad_fil_lases_inte_nar_stammen_ar_delad(tmp_path):
    folder = tmp_path / "uploads"
    folder.mkdir()
    (folder / "notes.md").write_bytes(b"a")
    (folder / "notes.txt").write_bytes(b"b")
    (folder / "notes.compact.md").write_text("## Oklart\n- vems?", encoding="utf-8")
    docs = DocumentStore(folder, lambda text: text)
    with pytest.raises(DocumentError, match="finns inte"):
        docs.topics("notes.md")

def test_mention_matchar_inte_del_av_annat_filnamn(tmp_path):
    docs = make_documents(tmp_path)
    docs.add("notes.md", b"text")
    docs.add("old-notes.md", b"text")
    room, sid, _ = make_room(tmp_path, documents=docs)
    room.send(sid, "vad står det i old-notes.md?")
    assert room.store.current_document(sid) == "old-notes.md"

def test_kommando_med_mellanslag_i_filnamn(tmp_path):
    docs = make_documents(tmp_path)
    docs.add("Min budget.md", b"text")
    room, sid, _ = make_room(tmp_path, documents=docs)
    result = room.send(sid, "/dokument Min budget.md")
    assert "ligger nu i historiken" in result[0]["content"]
    assert room.store.current_document(sid) == "Min budget.md"

def test_amnen_med_mellanslag_i_filnamn(tmp_path):
    docs = make_documents(tmp_path)
    docs.add("Min budget.md", b"text")
    room, sid, _ = make_room(tmp_path, documents=docs)
    assert "- Budget" in room.send(sid, "/ämnen Min budget.md")[0]["content"]

def test_prata_med_mellanslag_i_filnamn(tmp_path):
    docs = make_documents(tmp_path)
    docs.add("Min budget.md", b"text")
    room, sid, _ = make_room(tmp_path, documents=docs)
    room.send(sid, "/prata Min budget.md Resa")
    active = room.store.active_topic(sid)
    assert active == {"document": "Min budget.md", "topic": "Resa"}

def test_prata_med_ämne_med_mellanslag(docs_room):
    room, sid, _ = docs_room
    room.send(sid, "/prata notes.md Resa")
    assert room.store.active_topic(sid) == {"document": "notes.md", "topic": "Resa"}


def test_original_laddas_in_i_historiken(docs_room):
    room, sid, backend = docs_room
    result = room.send(sid, "/original notes.md")
    assert "originalet" in result[0]["content"]
    room.send(sid, "@Ada hej")
    _, messages = backend.calls[-1]
    contents = _all(messages)
    assert "---dokument notes.md---\ntext" in contents
    assert "Budget" not in contents

def test_original_okant_dokument_ger_fel(docs_room):
    room, sid, _ = docs_room
    result = room.send(sid, "/original saknas.md")
    assert "finns inte" in result[0]["content"]
