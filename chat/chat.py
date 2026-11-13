#!/usr/bin/env python3
"""Konsolchatt mot 1min.AI, version 2.

Historiken är en append-only logg (`turns.jsonl`) och det som skickas till
modellen härleds ur loggen. `/compact` skriver en sammanfattning som en egen
händelse — inget skrivs över och inget behöver backuppas.
"""

from __future__ import annotations

import sys

from config import LEGACY_HISTORY, STORE_FILE, budget_state, load_settings
from llm import LLM, LLMError, Reply, summary_counts
from store import Store, import_legacy

BANNER = "{who} ({model}). Skriv ditt meddelande, eller /help för kommandon."

HELP = """\
/compact  sammanfatta historiken och ersätt den med sammanfattningen
/reset    börja om från tom historik (loggen sparas)
/help     visa den här hjälpen
/exit     avsluta

Kommando utan snedstreck fungerar också: compact, reset, help, exit.
Allt annat skickas till modellen.

Personlighet: {persona}
Automatisk komprimering: {auto}
"""

AUTO_COMPACT_RETRY_STEP = 10


def help_text(limit: int, persona: bool = True) -> str:
    if limit > 0:
        auto = f"historiken komprimeras när den når {limit} meddelanden"
    else:
        auto = "avstängd (ONEMIN_AUTO_COMPACT=0)"
    return HELP.format(
        auto=auto,
        persona="Margareta (ONEMIN_PERSONA=0 stänger av)" if persona else "avstängd",
    )


# --------------------------------------------------------------------------- #
#  Kommandon
# --------------------------------------------------------------------------- #

COMMANDS = {
    "exit": "exit",
    "quit": "exit",
    "avsluta": "exit",
    "reset": "reset",
    "nollställ": "reset",
    "rensa": "reset",
    "compact": "compact",
    "help": "help",
    "hjälp": "help",
    "?": "help",
}


def parse_command(line: str) -> tuple[str, str] | None:
    """Tolka en inmatad rad.

    Returnerar ('command', namn), ('unknown', namn) eller ('message', text).
    None betyder tom rad.
    """
    text = line.strip()
    if not text:
        return None

    name = text.lower().lstrip("/").strip()

    if text.startswith("/"):
        if name in COMMANDS:
            return "command", COMMANDS[name]
        return "unknown", name

    if name in COMMANDS:
        return "command", COMMANDS[name]

    return "message", text


# --------------------------------------------------------------------------- #
#  Utskrift
# --------------------------------------------------------------------------- #

def _note(text: str) -> None:
    print(f"({text})")


def _print_error(exc: Exception) -> None:
    text = str(exc)
    if "content policy" in text.lower():
        text += (
            " (1min.AI:s innehållsfilter — formulera om meddelandet "
            "eller byt modell)"
        )
    print(f"Fel: {text}")


def _usage(reply: Reply) -> None:
    if reply.usage_line:
        print(f"  {reply.usage_line}")
    if reply.truncated:
        print("  (svaret klipptes av: finish_reason=length)")


# --------------------------------------------------------------------------- #
#  Kommandon i drift
# --------------------------------------------------------------------------- #

def do_help(limit: int, persona: bool = True) -> None:
    print(help_text(limit, persona))


def do_reset(store: Store) -> list[dict[str, str]]:
    store.reset()
    _note("historiken är rensad — loggen finns kvar i turns.jsonl")
    print()
    return store.context()


def do_compact(
    llm: LLM, store: Store, messages: list[dict[str, str]]
) -> list[dict[str, str]]:
    if not messages:
        _note("inget att komprimera")
        print()
        return messages

    _note(f"sammanfattar {len(messages)} meddelanden med {llm.settings.compact_model} …")
    try:
        summary, rendered, reply = llm.compact(messages)
    except KeyboardInterrupt:
        print("\n(avbrutet — historiken är oförändrad)")
        print()
        return messages
    except LLMError as exc:
        _print_error(exc)
        _note("historiken är oförändrad")
        print()
        return messages

    store.compact(summary, rendered)
    _note(f"komprimerat: {summary_counts(summary)}")
    _usage(reply)
    print()
    print(rendered)
    print()
    return store.context()


def do_turn(
    llm: LLM, store: Store, messages: list[dict[str, str]], text: str
) -> list[dict[str, str]]:
    state = budget_state(messages)
    if state:
        level, warning = state
        if level == "stop":
            print(f"  (historiken är full: {warning})")
            print()
            return messages
        print(f"  (varning: {warning})")

    print("AI: ", end="", flush=True)

    def write(piece: str) -> None:
        print(piece, end="", flush=True)

    try:
        reply = llm.complete(
            messages + [{"role": "user", "content": text}], on_chunk=write
        )
    except KeyboardInterrupt:
        print("\n(avbrutet — turen sparades inte)")
        print()
        return messages
    except LLMError as exc:
        print()
        _print_error(exc)
        print()
        return messages

    if not reply.text:
        print("(tomt svar)")
        print()
        return messages

    print()
    _usage(reply)
    print()

    # Först när svaret är helt sparat blir turen en del av historiken.
    store.add_turn("user", text)
    store.add_turn(
        "assistant",
        reply.text,
        model=reply.model,
        finish_reason=reply.finish_reason,
    )
    return store.context()


# --------------------------------------------------------------------------- #
#  Automatisk komprimering
# --------------------------------------------------------------------------- #

def auto_compact_due(
    messages: list[dict[str, str]], limit: int, retry_floor: int = 0
) -> bool:
    """Ska historiken komprimeras automatiskt nu?

    `limit` 0 betyder avstängt. `retry_floor` hindrar täta omförsök efter ett
    misslyckat anrop — då väntar chatten tills historiken vuxit.
    """
    return limit > 0 and len(messages) >= max(limit, retry_floor)


def auto_compact_if_due(
    llm: LLM,
    store: Store,
    messages: list[dict[str, str]],
    retry_floor: int = 0,
) -> tuple[list[dict[str, str]], int]:
    limit = llm.settings.auto_compact_at
    if not auto_compact_due(messages, limit, retry_floor):
        return messages, retry_floor

    before = len(messages)
    _note(f"{before} meddelanden — automatisk komprimering (gräns {limit})")
    messages = do_compact(llm, store, messages)

    if len(messages) < before:
        return messages, 0

    # Misslyckades: vänta tills historiken vuxit innan nästa försök.
    return messages, before + AUTO_COMPACT_RETRY_STEP


# --------------------------------------------------------------------------- #
#  Huvudloop
# --------------------------------------------------------------------------- #

def main() -> None:
    settings = load_settings()
    llm = LLM(settings)

    try:
        models = llm.models()
    except LLMError as exc:
        if exc.status_code in (401, 403):
            sys.exit(f"Fel: nyckeln avvisades av {settings.base_url} — {exc}")
        print(f"(startkontrollen misslyckades: {exc})")
    else:
        if settings.model not in models:
            print(
                f"(varning: {settings.model} finns inte i modellistan — "
                f"{len(models)} modeller tillgängliga)"
            )

    store = Store(STORE_FILE)
    imported = import_legacy(store, LEGACY_HISTORY)
    if imported:
        _note(f"importerade {imported} meddelanden från history.json till turns.jsonl")
    if store.broken_lines:
        _note(f"{store.broken_lines} trasiga rader i turns.jsonl hoppades över")

    messages = store.context()

    print(
        BANNER.format(
            who="Margareta" if settings.persona else "1min.AI-chatt",
            model=settings.model,
        )
    )
    if settings.auto_compact_at > 0:
        print(f"(komprimerar automatiskt vid {settings.auto_compact_at} meddelanden)")
    print()
    if messages:
        word = "meddelande" if len(messages) == 1 else "meddelanden"
        print(f"(läste in {len(messages)} {word} ur turns.jsonl)")
        print()

    auto_retry_floor = 0

    while True:
        try:
            line = input("Du: ")
        except (EOFError, KeyboardInterrupt):
            print()
            break

        parsed = parse_command(line)
        if parsed is None:
            continue

        kind, value = parsed

        if kind == "unknown":
            print(f"(okänt kommando: /{value} — /help visar kommandona)")
            print()
            continue

        if kind == "command":
            if value == "exit":
                break
            if value == "help":
                do_help(settings.auto_compact_at, settings.persona)
                continue
            if value == "reset":
                messages = do_reset(store)
                auto_retry_floor = 0
                continue
            if value == "compact":
                before = len(messages)
                messages = do_compact(llm, store, messages)
                if len(messages) < before:
                    auto_retry_floor = 0
                continue

        before = len(messages)
        messages = do_turn(llm, store, messages, value)
        if len(messages) > before:
            messages, auto_retry_floor = auto_compact_if_due(
                llm, store, messages, auto_retry_floor
            )


if __name__ == "__main__":
    main()
