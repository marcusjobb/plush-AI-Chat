"""Tunt lager ovanpå OpenAI-SDK:n mot 1min.AI:s OpenAI-kompatibla API."""

from __future__ import annotations

from openai import OpenAI

DEFAULT_BASE_URL = "https://api.1min.ai/openai/v1"


class LLMError(RuntimeError):
    """Fel från API:t, formulerat så att det kan visas för användaren."""


class OpenAIBackend:
    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL) -> None:
        # max_retries=0: ett automatiskt nytt försök är en ny, debiterad generering.
        self._client = OpenAI(api_key=api_key, base_url=base_url, max_retries=0)

    def complete(self, model: str, messages: list[dict[str, str]]) -> str:
        try:
            response = self._client.chat.completions.create(model=model, messages=messages)
        except Exception as exc:  # noqa: BLE001 - allt blir ett LLMError
            raise LLMError(str(exc).strip() or type(exc).__name__) from exc
        return (response.choices[0].message.content or "").strip()

    def complete_with_tools(
        self, model: str, messages: list[dict], tools: list[dict]
    ) -> tuple[str, list[dict[str, str]]]:
        """Returnerar (text, verktygsanrop). Varje anrop är {id, name, arguments}."""
        try:
            response = self._client.chat.completions.create(
                model=model, messages=messages, tools=tools
            )
        except Exception as exc:  # noqa: BLE001 - allt blir ett LLMError
            raise LLMError(str(exc).strip() or type(exc).__name__) from exc
        message = response.choices[0].message
        calls = [
            {"id": call.id, "name": call.function.name, "arguments": call.function.arguments}
            for call in (message.tool_calls or [])
        ]
        return (message.content or "").strip(), calls
