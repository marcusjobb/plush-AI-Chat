"""Laddar upp ett dokument från terminalen. Exempel: .venv/bin/python upload.py notes.md

Samma kontroller och komprimering som i webbchatten.
"""

from __future__ import annotations

import sys
from pathlib import Path

from app import build_assistants, build_documents, load_backend_settings
from documents import MAX_BYTES, DocumentError
from llm import OpenAIBackend


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Användning: upload.py <fil>", file=sys.stderr)
        return 2

    path = Path(argv[1])
    if not path.is_file():
        print(f"Filen finns inte: {path}", file=sys.stderr)
        return 1

    # Läser en byte längre än gränsen, så att för stora filer upptäcks utan att läsa allt.
    with path.open("rb") as fh:
        data = fh.read(MAX_BYTES + 1)

    base_url, api_key = load_backend_settings()
    assistants = build_assistants()
    backend = OpenAIBackend(api_key, base_url)
    documents = build_documents(backend, assistants)

    try:
        result = documents.add(path.name, data)
    except DocumentError as exc:
        print(f"Fel: {exc}", file=sys.stderr)
        return 1

    topics = result["topics"]
    print(f"Uppladdad: {result['name']} ({len(topics)} ämnen)")
    for topic in topics:
        print(f"- {topic}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
