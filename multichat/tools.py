"""Verktyg som assistenterna kan anropa. Alla filoperationer stannar i uploads/.

Varje verktyg returnerar (resultat, systemrad). Resultatet går tillbaka till modellen,
systemraden visas i chatten. Fel returneras som text så att modellen kan försöka igen.

Verktygsnamnen är ASCII, eftersom OpenAI inte godkänner å, ä och ö i funktionsnamn.
"""

from __future__ import annotations

import fnmatch
from typing import TYPE_CHECKING, Callable

from documents import DocumentError, mentions

if TYPE_CHECKING:
    from chat import ChatRoom


def _function(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required or [],
            },
        },
    }


def _text(description: str) -> dict:
    return {"type": "string", "description": description}


TOOL_SPECS: list[dict] = [
    _function(
        "ladda_dokument",
        "Laddar in ett dokument i samtalet så att du kan läsa det.",
        {"namn": _text("Filnamnet, t.ex. notes.md")},
        ["namn"],
    ),
    _function(
        "las_amne",
        "Hämtar texten under ett ämne i ett dokument.",
        {"fil": _text("Filnamnet"), "amne": _text("Ämnets rubrik")},
        ["fil", "amne"],
    ),
    _function("dokument", "Listar de uppladdade dokumenten.", {}),
    _function(
        "amnen",
        "Listar ämnena i ett dokument.",
        {"fil": _text("Filnamnet")},
        ["fil"],
    ),
    _function(
        "prata",
        "Väljer ett ämne i ett dokument att prata om. Gäller tills användaren släpper det.",
        {"fil": _text("Filnamnet"), "amne": _text("Ämnets rubrik")},
        ["fil", "amne"],
    ),
    _function(
        "sok",
        "Söker efter filer vars namn matchar. Använd *mönster* för delsträng, t.ex. *katt*.",
        {"monster": _text("Mönstret, t.ex. *katt*")},
        ["monster"],
    ),
    _function(
        "editera",
        "Skapar en redigerad kopia av en fil. Originalet ändras aldrig. "
        "Kräver att användaren nämner filnamnet i sitt meddelande.",
        {
            "namn": _text("Filen att redigera"),
            "fran": _text("Texten som ska bytas ut"),
            "till": _text("Den nya texten"),
        },
        ["namn", "fran", "till"],
    ),
    _function(
        "spara",
        "Sparar ny text som en ny fil. Skriver aldrig över en befintlig fil.",
        {"namn": _text("Det nya filnamnet"), "innehall": _text("Filens text")},
        ["namn", "innehall"],
    ),
    _function(
        "radera",
        "Flyttar en fil till papperskorgen. Kräver att användaren nämner filnamnet i sitt meddelande.",
        {"namn": _text("Filnamnet")},
        ["namn"],
    ),
    _function("list_files", "Listar alla filer i uploads/, också i undermappar.", {}),
]

# Verktyg som ändrar eller tar bort filer. De kräver att användaren nämner filen.
NEEDS_NAMED_FILE = {"editera", "radera"}


class FileTools:
    def __init__(self, room: ChatRoom) -> None:
        self._room = room
        self._handlers: dict[str, Callable[[dict, str, str], tuple[str, str]]] = {
            "ladda_dokument": self._ladda_dokument,
            "las_amne": self._las_amne,
            "dokument": self._dokument,
            "amnen": self._amnen,
            "prata": self._prata,
            "sok": self._sok,
            "editera": self._editera,
            "spara": self._spara,
            "radera": self._radera,
            "list_files": self._list_files,
        }

    def run(self, name: str, args: dict, user_text: str, session_id: str) -> tuple[str, str]:
        """Kör ett verktyg. Returnerar (resultat till modellen, systemrad till chatten)."""
        handler = self._handlers.get(name)
        if handler is None:
            return f"FEL: okänt verktyg {name}.", f"Okänt verktyg: {name}"
        if name in NEEDS_NAMED_FILE and not isinstance(args.get("namn"), str):
            return "FEL: filnamn saknas.", f"Verktyget {name} saknar filnamn"
        try:
            return handler(args, user_text, session_id)
        except (DocumentError, KeyError, TypeError, ValueError) as exc:
            message = str(exc).strip("'\"")
            return f"FEL: {message}", f"Verktyget {name} misslyckades: {message}"

    # -- hjälpare -----------------------------------------------------------
    def _docs(self):
        return self._room.require_documents()

    def _require_named(self, name: str, user_text: str) -> None:
        if not mentions([name], user_text):
            raise DocumentError(f"Användaren måste nämna filnamnet '{name}' i sitt meddelande.")

    # -- läsning ------------------------------------------------------------
    def _ladda_dokument(self, args: dict, user_text: str, session_id: str) -> tuple[str, str]:
        name = self._room.load_document(session_id, args["namn"])
        return f"{name} är laddat i historiken.", f"Laddade {name}"

    def _las_amne(self, args: dict, user_text: str, session_id: str) -> tuple[str, str]:
        text = self._docs().topic_text(args["fil"], args["amne"])
        return text, f"Läste ämnet {args['amne']} ur {args['fil']}"

    def _dokument(self, args: dict, user_text: str, session_id: str) -> tuple[str, str]:
        names = self._docs().list_documents()
        return "\n".join(names) or "Inga dokument är uppladdade.", "Listade dokumenten"

    def _amnen(self, args: dict, user_text: str, session_id: str) -> tuple[str, str]:
        topics = self._docs().topics(args["fil"])
        return "\n".join(topics), f"Listade ämnena i {args['fil']}"

    def _sok(self, args: dict, user_text: str, session_id: str) -> tuple[str, str]:
        monster = args["monster"].strip()
        pattern = monster if "*" in monster or "?" in monster else f"*{monster}*"
        matches = [n for n in self._docs().list_all_files() if fnmatch.fnmatch(n.lower(), pattern.lower())]
        return "\n".join(matches) or "Inga träffar.", f"Sökte efter {monster}: {len(matches)} träffar"

    def _list_files(self, args: dict, user_text: str, session_id: str) -> tuple[str, str]:
        names = self._docs().list_all_files()
        return "\n".join(names) or "Inga filer.", f"Listade {len(names)} filer"

    # -- sessionen ----------------------------------------------------------
    def _prata(self, args: dict, user_text: str, session_id: str) -> tuple[str, str]:
        self._docs().topic_text(args["fil"], args["amne"])  # kontrollerar att ämnet finns
        self._room.store.set_topic(session_id, args["fil"], args["amne"])
        return f"Pratar nu om {args['amne']} ur {args['fil']}.", f"Valde ämnet {args['amne']} ur {args['fil']}"

    # -- skrivning: aldrig över en befintlig fil ----------------------------
    def _editera(self, args: dict, user_text: str, session_id: str) -> tuple[str, str]:
        source = args["namn"]
        self._require_named(source, user_text)
        original = self._docs().original_text(source)
        if args["fran"] not in original:
            raise DocumentError(f"Texten '{args['fran']}' finns inte i {source}.")
        edited = original.replace(args["fran"], args["till"])
        stem, suffix = source.rsplit(".", 1) if "." in source else (source, "")
        new_name = self._docs().available_name(f"{stem}-redigerad.{suffix}" if suffix else f"{stem}-redigerad")
        self._docs().add(new_name, edited.encode("utf-8"))
        return f"Sparade en redigerad kopia: {new_name}", f"Redigerade {source} till {new_name}"

    def _spara(self, args: dict, user_text: str, session_id: str) -> tuple[str, str]:
        new_name = self._docs().available_name(args["namn"])
        self._docs().add(new_name, args["innehall"].encode("utf-8"))
        return f"Sparade {new_name}.", f"Sparade ny fil {new_name}"

    def _radera(self, args: dict, user_text: str, session_id: str) -> tuple[str, str]:
        self._require_named(args["namn"], user_text)
        name = self._docs().remove(args["namn"])
        if self._room.store.current_document(session_id) == name:
            self._room.store.add_document(session_id, None)
        return f"{name} är flyttad till papperskorgen.", f"Raderade {name} (papperskorgen)"
