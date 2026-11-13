"""Uppladdade dokument: validering, komprimering och ämnen.

Varje uppladdad fil sparas två gånger i uploads/: originalet och en komprimerad
version (<namn>.compact.md) som är uppdelad i ämnen med rubriker '## Ämne'.
Assistenterna läser bara den komprimerade versionen, och bara när användaren
uttryckligen ber om det.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Callable

ALLOWED_EXTENSIONS = {
    ".md",
    ".txt",
    ".json",
    ".csv",
    ".tsv",
    ".ics",
    ".vcf",
    ".xml",
    ".yaml",
    ".yml",
    ".log",
}
MAX_BYTES = 100 * 1024
COMPACT_SUFFIX = ".compact.md"
TRASH_DIR = ".papperskorg"
_SAFE_NAME = re.compile(r"^[\w][\w \-.()]{0,99}$")
_HEADING = re.compile(r"^## (.+)$", re.MULTILINE)

COMPRESS_PROMPT = (
    "Gör om dokumentet nedan till en faktasammanfattning som är lätt att ställa frågor mot. "
    "Dela upp innehållet i ämnen. Varje ämne börjar med en rubrik på formen '## Ämne'. "
    "Under rubriken: korta punkter med fakta, namn, siffror och datum. "
    "Skriv inga egna påståenden som inte finns i dokumentet. "
    "Skriv på dokumentets språk och svara bara med sammanfattningen."
)

Compressor = Callable[[str], str]


class DocumentError(ValueError):
    """Dokumentet kan inte laddas upp, eller det efterfrågade finns inte."""


def make_compressor(backend, model: str) -> Compressor:
    """Bygger en komprimerare som använder en modell via backend."""

    def compress(text: str) -> str:
        messages = [
            {"role": "system", "content": COMPRESS_PROMPT},
            {"role": "user", "content": text},
        ]
        try:
            return backend.complete(model, messages).strip()
        except Exception as exc:  # noqa: BLE001
            raise DocumentError(f"Komprimeringen misslyckades: {exc}") from exc

    return compress


def validate_name(name: str) -> str:
    """Returnerar det rena filnamnet, eller kastar DocumentError."""
    base = Path(name).name
    if not _SAFE_NAME.match(base) or COMPACT_SUFFIX in base:
        raise DocumentError(f"Ogiltigt filnamn: '{name}'.")
    if Path(base).suffix.lower() not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise DocumentError(f"Filtypen stöds inte: '{base}'. Tillåtna är {allowed}.")
    return base


def validate_content(name: str, data: bytes) -> str:
    """Kontrollerar storlek och kodning. Returnerar texten."""
    if len(data) > MAX_BYTES:
        raise DocumentError(
            f"'{name}' är för stor: {len(data) // 1024} KB. Maxgränsen är {MAX_BYTES // 1024} KB."
        )
    if b"\x00" in data:
        raise DocumentError(f"'{name}' ser ut som en binärfil, inte text.")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DocumentError(f"'{name}' är inte UTF-8-text.") from exc


def mentions(names: list[str], text: str) -> list[str]:
    """Filnamn som står som egna ord i texten. 'notes.md' matchar inte 'old-notes.md'."""
    return [
        name
        for name in names
        if re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text, re.IGNORECASE)
    ]


def split_topics(compact: str) -> dict[str, str]:
    """Delar den komprimerade texten i {ämne: innehåll} utifrån '## '-rubriker."""
    matches = list(_HEADING.finditer(compact))
    topics: dict[str, str] = {}
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(compact)
        body = compact[match.end() : end].strip()
        title = match.group(1).strip()
        # Samma rubrik två gånger slås ihop, så att inget avsnitt försvinner.
        topics[title] = f"{topics[title]}\n{body}".strip() if title in topics else body
    return topics


class DocumentStore:
    def __init__(self, folder: Path, compress: Compressor) -> None:
        self.folder = folder
        self.folder.mkdir(parents=True, exist_ok=True)
        self._compress = compress

    # -- uppladdning --------------------------------------------------------
    def add(self, name: str, data: bytes) -> dict[str, object]:
        """Validerar, komprimerar och sparar. Sparar ingenting om något steg misslyckas."""
        base = validate_name(name)
        text = validate_content(base, data)
        compact = self._compress(text)
        if not compact:
            raise DocumentError(f"Komprimeringen av '{base}' gav ett tomt resultat.")
        if "## " not in compact:
            compact = f"## {Path(base).stem}\n{compact}"

        self._original(base).write_text(text, encoding="utf-8")
        self._compact_path(base).write_text(compact, encoding="utf-8")
        return {"name": base, "topics": list(split_topics(compact))}

    # -- läsning ------------------------------------------------------------
    def list_documents(self) -> list[str]:
        return sorted(
            p.name
            for p in self.folder.iterdir()
            if p.is_file() and not p.name.endswith(COMPACT_SUFFIX)
            and p.suffix.lower() in ALLOWED_EXTENSIONS
        )

    def topics(self, name: str) -> list[str]:
        return list(split_topics(self._read_compact(name)))

    def document_text(self, name: str) -> str:
        """Hela den komprimerade versionen. Läses bara när användaren nämner dokumentet."""
        return self._read_compact(name)

    def topic_text(self, name: str, topic: str) -> str:
        """Innehållet under ett ämne. Läses bara när användaren har valt det."""
        topics = split_topics(self._read_compact(name))
        for title, body in topics.items():
            if title.lower() == topic.strip().lower():
                return f"## {title}\n{body}"
        raise DocumentError(f"Ämnet '{topic}' finns inte i '{name}'.")

    # -- verktygens filoperationer ------------------------------------------
    def original_text(self, name: str) -> str:
        """Originalets text. Används av editera, så att kopior kan göras från den."""
        base = validate_name(name)
        path = self._original(base)
        if not path.exists():
            raise DocumentError(f"Filen '{base}' finns inte.")
        return path.read_text(encoding="utf-8")

    def available_name(self, name: str) -> str:
        """Ett filnamn som inte redan används. 'a.md' blir 'a (2).md' om det behövs."""
        base = validate_name(name)
        stem, suffix = Path(base).stem, Path(base).suffix
        candidate, counter = base, 2
        while self._original(candidate).exists() or self._compact_path(candidate).exists():
            candidate = f"{stem} ({counter}){suffix}"
            counter += 1
        return candidate

    def remove(self, name: str) -> str:
        """Flyttar originalet och dess komprimerade version till papperskorgen. Inget raderas."""
        base = validate_name(name)
        original = self._original(base)
        if not original.exists():
            raise DocumentError(f"Filen '{base}' finns inte.")
        trash = self.folder / TRASH_DIR
        trash.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        original.rename(trash / f"{stamp}-{base}")
        compact = self._compact_path(base)
        if compact.exists():
            compact.rename(trash / f"{stamp}-{compact.name}")
        return base

    def list_all_files(self) -> list[str]:
        """Alla dokument i uploads/, också i undermappar. Papperskorgen och komprimerade versioner ingår inte."""
        names = []
        for path in sorted(self.folder.rglob("*")):
            if not path.is_file() or path.name.endswith(COMPACT_SUFFIX):
                continue
            if TRASH_DIR in path.relative_to(self.folder).parts:
                continue
            names.append(path.relative_to(self.folder).as_posix())
        return names

    # -- hjälpare -----------------------------------------------------------
    def _original(self, base: str) -> Path:
        return self.folder / base

    def _compact_path(self, base: str) -> Path:
        """Varje fil får sin egen komprimerade version: notes.md -> notes.md.compact.md."""
        return self.folder / (base + COMPACT_SUFFIX)

    def _legacy_compact_path(self, base: str) -> Path | None:
        """Äldre uppladdningar delade komprimerad fil per stam (notes.md -> notes.compact.md).

        Används bara när ingen annan fil har samma stam, eftersom den filen annars kan
        tillhöra en annan uppladdning.
        """
        if not (self.folder / base).exists():
            return None
        stem = Path(base).stem
        siblings = [
            p
            for p in self.folder.iterdir()
            if p.is_file()
            and not p.name.endswith(COMPACT_SUFFIX)
            and Path(p.name).stem == stem
            and p.name != base
        ]
        legacy = self.folder / (stem + COMPACT_SUFFIX)
        if siblings or not legacy.exists():
            return None
        return legacy

    def _read_compact(self, name: str) -> str:
        base = validate_name(name)
        path = self._compact_path(base)
        if not path.exists():
            legacy = self._legacy_compact_path(base)
            if legacy is None:
                raise DocumentError(f"Dokumentet '{base}' finns inte.")
            path = legacy
        return path.read_text(encoding="utf-8")
