"""Chattrummet: routing, assistenter, komprimering, dokumentkommandon och det gemensamma samtalet."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol

from documents import DocumentError, DocumentStore, mentions, validate_name
from store import DOCUMENT_SPEAKER, SUMMARY, SessionStore
from tools import TOOL_SPECS, FileTools

MENTION = re.compile(r"^@(\S+)\s*(.*)$", re.DOTALL)

AUTO_COMPACT_AT = 50
AUTO_COMPACT_RETRY_STEP = 10
MAX_TOOL_ROUNDS = 4

COMMAND_HELP = (
    "Kommandon: /dokument, /ämnen <fil>, /prata <fil> <ämne>, /prata av"
)

TOOLS = (
    "Du kan använda verktyg för att arbeta med uppladdade filer. Använd dem när användaren "
    "ber om något som kräver det, och nämn aldrig verktygens namn för användaren. "
    "Filer ändras aldrig på egen hand: redigera och radera gör du bara när användaren "
    "nämner filnamnet. Hitta aldrig på innehåll i en fil. Om en fil inte är läst, läs den "
    "först med ett verktyg.\n"
    "Användaren kan också skriva: /dokument <fil>, /ämnen <fil>, /prata <fil> <ämne> "
    "och /prata av."
)

COMPACT_PROMPT = (
    "Sammanfatta samtalet nedan till en kort anteckning på samtalets språk, i punktform. "
    "Behåll fakta, namn, siffror, beslut och användarens önskemål. "
    "Skriv inte om saker som inte nämndes. Stryk småprat och upprepningar. "
    "Om en tidigare sammanfattning finns i samtalet är den ofullständig: "
    "bygg anteckningen från de riktiga meddelandena."
)


class UnknownAssistant(ValueError):
    """Användaren skrev @namn för en assistent som inte finns."""


class ChatBackend(Protocol):
    """Allt ChatRoom behöver från LLM-lagret."""

    def complete(self, model: str, messages: list[dict[str, str]]) -> str: ...

    def complete_with_tools(
        self, model: str, messages: list[dict], tools: list[dict]
    ) -> tuple[str, list[dict[str, str]]]: ...


def parse_message(text: str, names: list[str]) -> tuple[list[str], str]:
    """Returnerar (mottagare, innehåll).

    Börjar meddelandet med @namn går det bara till den assistenten, och @namn
    tas bort ur innehållet. Annars går det till alla assistenter.
    """
    text = text.strip()
    match = MENTION.match(text)
    if match is None:
        return list(names), text

    wanted = match.group(1).lower()
    for name in names:
        if name.lower() == wanted:
            return [name], match.group(2).strip()
    raise UnknownAssistant(f"Det finns ingen assistent som heter '{match.group(1)}'.")


@dataclass(frozen=True)
class Assistant:
    name: str
    model: str
    persona: str = ""

    def system_prompt(self, others: list[str], hint: str | None = None) -> str:
        """Instruktionen som beskriver vem assistenten är, och verktygen i chatten."""
        prompt = (
            f"Du heter {self.name}. Du chattar med användaren och med "
            f"{', '.join(others)}. Ge allmänna tips och råd, pladdra gärna lite, "
            "och håll svaren korta. Du kan nämna en annan assistent med @namn, men skriv "
            "aldrig '@' framför något annat."
        )
        if self.persona:
            prompt = f"{self.persona}\n\n{prompt}"
        prompt += "\n\n" + TOOLS
        if hint:
            prompt += f"\n\n{hint}"
        return prompt


SPEAKER_PREFIX = re.compile(r"^\s*(?:[A-ZÅÄÖ][\wÅÄÖåäö]*|Du)\s*:\s+")


def strip_speaker(reply: str, names: list[str]) -> str:
    """Tar bort ett 'Namn:'-prefix som modellen kan skriva efter historikens format."""
    known = {n.lower() for n in names} | {"du"}
    while True:
        match = SPEAKER_PREFIX.match(reply)
        if match is None or match.group(0).strip().rstrip(":").lower() not in known:
            return reply
        reply = reply[match.end():]


def sanitize(reply: str, names: list[str]) -> str:
    """Behåller '@' bara framför namnen på assistenterna. Andra '@' tas bort.

    Så kan en assistent nämna en annan, utan att ett svar kan se ut som en adressering av användaren.
    """
    if not names:
        return reply.replace("@", "").strip()
    known = "|".join(re.escape(n) for n in names)
    return re.sub(rf"@(?!(?:{known})\b)", "", reply, flags=re.IGNORECASE).strip()


class ChatRoom:
    def __init__(
        self,
        assistants: list[Assistant],
        backend: ChatBackend,
        store: SessionStore,
        window: int = 20,
        compact_model: str | None = None,
        auto_compact_at: int = AUTO_COMPACT_AT,
        documents: DocumentStore | None = None,
    ) -> None:
        if len({a.name.lower() for a in assistants}) != len(assistants):
            raise ValueError("assistenterna måste ha unika namn")
        self.assistants = assistants
        self.backend = backend
        self.store = store
        self.window = window
        self.compact_model = compact_model or assistants[0].model
        self.auto_compact_at = auto_compact_at
        self.documents = documents
        # Efter ett misslyckat automatiskt försök väntar vi några meddelanden innan nästa.
        self._retry_at: dict[str, int] = {}
        self.tools = FileTools(self)

    @property
    def names(self) -> list[str]:
        return [a.name for a in self.assistants]

    # -- samtal -------------------------------------------------------------
    def send(
        self, session_id: str, text: str, selected: list[str] | None = None
    ) -> list[dict[str, str]]:
        """Tar emot meddelandet och returnerar de nya meddelandena i sessionen.

        Text som börjar med '/' är ett kommando. Övrig text går till assistenterna.
        Har sessionen nått auto_compact_at meddelanden sedan senaste komprimering
        körs en komprimering först. Vid fel i ett anrop läggs ett felmeddelande
        med speaker "system" till.
        """
        stripped = text.strip()
        if stripped.startswith("/"):
            return self._command(session_id, stripped)

        targets, content = parse_message(stripped, self.names)
        if not content:
            return []
        if selected is not None and not MENTION.match(stripped):
            # Utan @namn gäller användarens val av assistenter.
            targets = [n for n in self.names if n in selected]
            if not targets:
                return [{"speaker": "system", "content": "Välj minst en assistent att prata med."}]

        try:
            self._load_mentioned(session_id, content)
            section = self._active_section(session_id)
        except DocumentError as exc:
            return [{"speaker": "system", "content": str(exc)}]
        hint = self._current_file_hint(session_id)

        new: list[dict[str, str]] = []
        turns = self.store.turns_since_compact(session_id)
        if turns >= self.auto_compact_at and turns >= self._retry_at.get(session_id, 0):
            ok, notice = self._compact(session_id)
            if ok:
                self._retry_at.pop(session_id, None)
            else:
                self._retry_at[session_id] = turns + AUTO_COMPACT_RETRY_STEP
            new.append(notice)

        # Användaren ser det hen skrev, inklusive @namn. Routingen använde den rensade texten.
        self.store.add(session_id, "Du", stripped)
        new.append({"speaker": "Du", "content": stripped})
        for assistant in self.assistants:
            if assistant.name in targets:
                new.extend(self._reply(session_id, assistant, section, hint, content))
        return new

    def _reply(
        self,
        session_id: str,
        assistant: Assistant,
        section: str | None = None,
        hint: str | None = None,
        user_text: str = "",
    ) -> list[dict[str, str]]:
        others = [n for n in self.names if n != assistant.name]
        prompt = assistant.system_prompt(others, hint)
        messages = [{"role": "system", "content": prompt}]
        messages += [
            self._as_message(m, assistant.name)
            for m in self._window(self.store.context(session_id))
        ]
        if section and len(messages) > 1:
            # Dokumentet läggs precis före den senaste repliken, så att modellen ser det nära frågan.
            messages.insert(
                -1,
                {"role": "user", "content": f"Dokument att använda för att svara:\n\n{section}"},
            )
        try:
            answer, rows = self._answer_with_tools(session_id, assistant, messages, user_text)
        except Exception as exc:  # noqa: BLE001 - felet visas i chatten
            return [{"speaker": "system", "content": f"{assistant.name} kunde inte svara: {exc}"}]
        for row in rows:
            self.store.add(session_id, "system", row["content"])  # systemraderna sparas i historiken
        if not answer:
            return rows + [{"speaker": "system", "content": f"{assistant.name} gav ett tomt svar."}]
        self.store.add(session_id, assistant.name, answer)
        return rows + [{"speaker": assistant.name, "content": answer}]

    def _answer_with_tools(
        self,
        session_id: str,
        assistant: Assistant,
        messages: list[dict],
        user_text: str,
    ) -> tuple[str, list[dict[str, str]]]:
        """Låter modellen anropa verktyg tills den svarar med text. Returnerar (svar, systemrader)."""
        rows: list[dict[str, str]] = []
        for _ in range(MAX_TOOL_ROUNDS):
            text, calls = self.backend.complete_with_tools(assistant.model, messages, TOOL_SPECS)
            if not calls:
                return sanitize(strip_speaker(text, self.names), self.names), rows
            messages.append({
                "role": "assistant",
                "content": text or None,
                "tool_calls": [
                    {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}}
                    for c in calls
                ],
            })
            for call in calls:
                try:
                    args = json.loads(call["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                result, row = self.tools.run(call["name"], args, user_text, session_id)
                rows.append({"speaker": "system", "content": row})
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
        return "", rows

    def _window(self, context: list[dict[str, str]]) -> list[dict[str, str]]:
        """Dokumentet och sammanfattningen behålls alltid, men bara de senaste turerna efter dem."""
        fixed: list[dict[str, str]] = []
        rest = context
        while rest and rest[0]["speaker"] in (SUMMARY, DOCUMENT_SPEAKER):
            fixed.append(rest[0])
            rest = rest[1:]
        return fixed + rest[-self.window :]

    @staticmethod
    def _as_message(entry: dict[str, str], me: str) -> dict[str, str]:
        """Egna svar är 'assistant', dokument är 'system', allt annat är 'user'."""
        if entry["speaker"] == DOCUMENT_SPEAKER:
            return {"role": "system", "content": entry["content"]}
        if entry["speaker"] == me:
            return {"role": "assistant", "content": entry["content"]}
        return {"role": "user", "content": f"{entry['speaker']}: {entry['content']}"}

    # -- dokument -----------------------------------------------------------
    def require_documents(self) -> DocumentStore:
        """Dokumentlagret, eller DocumentError om dokument inte är aktiverade."""
        if self.documents is None:
            raise DocumentError("Dokument är inte aktiverade i den här chatten.")
        return self.documents

    def _current_file_hint(self, session_id: str) -> str | None:
        """Systemrad med de uppladdade filerna, och vilken som senast laddades upp."""
        if self.documents is None:
            return None
        names = self.documents.list_documents()
        if not names:
            return None
        lines = ["Uppladdade filer: " + ", ".join(names) + "."]
        current = self.store.current_document(session_id)
        if current:
            lines.append(
                f"Användaren laddade senast upp {current}. "
                "Om användaren säger 'filen' eller 'dokumentet' menar hen den filen."
            )
        lines.append("Du kan läsa en fil när användaren ber om det, till exempel genom att nämna filnamnet.")
        return " ".join(lines)

    def load_document(self, session_id: str, name: str) -> str:
        """Laddar in en fil i historiken. Den gäller tills nästa fil laddas.

        Returnerar det filnamn som laddades, så som det står i dokumentlagret.
        """
        docs = self.require_documents()
        text = docs.document_text(name)
        self.store.add_document(session_id, name, text)
        return name

    def _load_mentioned(self, session_id: str, text: str) -> None:
        """Laddar filen om användaren nämner den i meddelandet.

        Säger användaren "filen" eller "dokumentet" och det finns bara en uppladdad fil,
        laddas den filen.
        """
        if self.documents is None:
            return
        names = self.documents.list_documents()
        mentioned = mentions(names, text)
        if not mentioned and len(names) == 1 and re.search(r"\b(filen|dokumentet|fil|dokument)\b", text.lower()):
            mentioned = names
        current = self.store.current_document(session_id)
        for name in mentioned:
            if name != current:
                self.load_document(session_id, name)
                current = name

    def _active_section(self, session_id: str) -> str | None:
        """Ämnestexten för valt ämne. Läses bara om användaren valt ett ämne."""
        active = self.store.active_topic(session_id)
        if active is None:
            return None
        docs = self.require_documents()
        return docs.topic_text(active["document"], active["topic"])

    def _command(self, session_id: str, text: str) -> list[dict[str, str]]:
        """Kör ett /kommando. Kommandon och deras svar sparas inte i samtalet."""
        cmd, _, rest = text.partition(" ")
        try:
            return [{"speaker": "system", "content": self._run_command(session_id, cmd.lower(), rest.strip())}]
        except DocumentError as exc:
            return [{"speaker": "system", "content": str(exc)}]

    def _split_document_and_topic(self, rest: str) -> tuple[str, str]:
        """Delar '<fil> <ämne>' där filnamnet kan innehålla mellanslag.

        Börjar texten med ett känt filnamn följt av mellanslag är det filen. Annars är
        första ordet filen.
        """
        names = self.require_documents().list_documents()
        for name in sorted(names, key=len, reverse=True):
            if rest.lower().startswith(name.lower() + " "):
                return name, rest[len(name) :].strip()
            if rest.lower() == name.lower():
                return name, ""
        document, _, topic = rest.partition(" ")
        return document, topic.strip()

    def _run_command(self, session_id: str, cmd: str, rest: str) -> str:
        if cmd == "/dokument":
            if rest.lower() == "av":
                self.store.add_document(session_id, None)
                return "Dokumentet är borttaget ur historiken."
            if rest:
                name = self.load_document(session_id, rest)
                return f"{name} ligger nu i historiken. Assistenterna kan läsa den tills du laddar en annan fil."
            names = self.require_documents().list_documents()
            if not names:
                return "Inga dokument är uppladdade ännu."
            return "Uppladdade dokument:\n" + "\n".join(f"- {n}" for n in names)

        if cmd == "/original":
            if not rest:
                return "Ange ett dokument, t.ex. /original fil.md"
            name = validate_name(rest)
            text = self.require_documents().original_text(name)
            self.store.add_document(session_id, name, text)
            return f"{name} (originalet) ligger nu i historiken. Assistenterna kan läsa den tills du laddar en annan fil."

        if cmd == "/ämnen":
            if not rest:
                return "Ange ett dokument, t.ex. /ämnen fil.md"
            topics = self.require_documents().topics(rest)
            return f"Ämnen i {rest}:\n" + "\n".join(f"- {t}" for t in topics)

        if cmd == "/prata":
            if rest.lower() == "av":
                self.store.set_topic(session_id, None, None)
                return "Ämnet är släppt. Vi pratar fritt igen."
            document, topic = self._split_document_and_topic(rest)
            if not document or not topic:
                return "Ange dokument och ämne, t.ex. /prata fil.md Budget"
            self.require_documents().topic_text(document, topic)  # kontrollerar att ämnet finns
            self.store.set_topic(session_id, document, topic)
            return f"Nu pratar vi om '{topic}' ur {document}. Skriv /prata av när du vill släppa ämnet."

        return f"Okänt kommando. {COMMAND_HELP}"

    # -- sessioner och komprimering -----------------------------------------
    def history(self, session_id: str) -> list[dict[str, str]]:
        """Chatten som den visas. Gamla svar rensas på namnprefix på samma sätt som nya."""
        shown = []
        for entry in self.store.transcript(session_id):
            if entry["speaker"] in self.names:
                entry = {**entry, "content": strip_speaker(entry["content"], self.names)}
            shown.append(entry)
        return shown

    def compact(self, session_id: str) -> dict[str, str]:
        """Komprimerar sessionen på begäran och returnerar ett systemmeddelande."""
        _, notice = self._compact(session_id)
        return notice

    def _compact(self, session_id: str) -> tuple[bool, dict[str, str]]:
        """Sammanfattar det modellen ser just nu. Returnerar (lyckades, meddelande)."""
        context = [m for m in self.store.context(session_id) if m["speaker"] != DOCUMENT_SPEAKER]
        if len(context) < 2:
            return False, {"speaker": "system", "content": "Det finns inget att komprimera ännu."}

        transcript = "\n".join(f"{m['speaker']}: {m['content']}" for m in context)
        messages = [
            {"role": "system", "content": COMPACT_PROMPT},
            {"role": "user", "content": transcript},
        ]
        try:
            summary = self.backend.complete(self.compact_model, messages).strip()
        except Exception as exc:  # noqa: BLE001
            return False, {"speaker": "system", "content": f"Komprimeringen misslyckades: {exc}"}
        if not summary:
            return False, {"speaker": "system", "content": "Komprimeringen gav ett tomt svar."}

        self.store.compact(session_id, summary)
        return True, {"speaker": "system", "content": "Samtalet komprimerades."}
