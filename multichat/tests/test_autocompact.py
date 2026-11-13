"""Omförsök för automatisk komprimering: ett misslyckat försök ska inte upprepas vid varje meddelande."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from test_chat import make_room  # noqa: E402


class FailingCompactBackend:
    """Svarar vanligt, men alla sammanfattningsanrop misslyckas. Räknar dem."""

    def __init__(self):
        self.compact_calls = 0

    def complete_with_tools(self, model, messages, tools):
        return self.complete(model, messages), []

    def complete(self, model, messages):
        if messages[0]["content"].startswith("Sammanfatta"):
            self.compact_calls += 1
            raise RuntimeError("API nere")
        return "svar"


def test_misslyckad_komprimering_upprepas_inte_vid_varje_meddelande(tmp_path):
    backend = FailingCompactBackend()
    room, sid = make_room(tmp_path, backend, auto_compact_at=6)
    for _ in range(8):
        room.send(sid, "@Ada hej")
    assert backend.compact_calls == 1  # första försöket efter 6 meddelanden, sedan väntar vi

def test_nytt_forsok_efter_tio_meddelanden_till(tmp_path):
    backend = FailingCompactBackend()
    room, sid = make_room(tmp_path, backend, auto_compact_at=6)
    for _ in range(9):
        room.send(sid, "@Ada hej")
    assert backend.compact_calls == 2

def test_lyckad_komprimering_efter_omforsok_rensar_spärren(tmp_path):
    class FailsOnce(FailingCompactBackend):
        def complete(self, model, messages):
            if messages[0]["content"].startswith("Sammanfatta"):
                self.compact_calls += 1
                if self.compact_calls == 1:
                    raise RuntimeError("tillfälligt fel")
                return "- sammanfattning"
            return "svar"

    backend = FailsOnce()
    room, sid = make_room(tmp_path, backend, auto_compact_at=6)
    for _ in range(9):
        room.send(sid, "@Ada hej")  # försök 1 misslyckas vid 6, försök 2 lyckas vid 16
    assert backend.compact_calls == 2
    assert room.store.context(sid)[0]["speaker"] == "Sammanfattning"
    assert sid not in room._retry_at
