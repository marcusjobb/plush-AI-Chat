"""Laddar upp ett dokument från terminalen. Exempel: .venv/bin/python upload.py notes.md

Samma kontroller och komprimering som i webbchatten.
"""

from __future__ import annotations

import sys
from pathlib import Path

from app import build_assistants, build_documents, env_value, load_env
from documents import MAX_BYTES, DocumentError
from llm import DEFAULT_BASE_URL, OpenAIBackend


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

    api_key = load_env()
    assistants = build_assistants()
    backend = OpenAIBackend(api_key, env_value("ONEMIN_BASE_URL", DEFAULT_BASE_URL))
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
