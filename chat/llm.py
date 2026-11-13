"""LLM-lagret: ett tunt lager ovanpå OpenAI-SDK:n.

Här bor allt som har med API:t att göra: klienten, streaming, nedgradering när
en modell avvisar parametrar, och /compact-sammanfattningen som JSON.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable

from openai import BadRequestError, OpenAI

from config import Settings
from persona import SYSTEM_PROMPT

COMPACT_PREFIX = "Sammanfattning av tidigare samtal (komprimerad historik):"

SUMMARY_FIELDS = ("fakta", "preferenser", "beslut", "oppna_uppgifter")

SUMMARY_SCHEMA = {
    "name": "anteckning",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "fakta": {
                "type": "array",
                "description": "En post per ämne: 'nyckel: värde, detalj, detalj'.",
                "items": {"type": "string"},
            },
            "preferenser": {
                "type": "array",
                "description": "Hur användaren vill ha svar och samarbete.",
                "items": {"type": "string"},
            },
            "beslut": {
                "type": "array",
                "description": "Vad som bestämts, med detaljer.",
                "items": {"type": "string"},
            },
            "oppna_uppgifter": {
                "type": "array",
                "description": "Det som återstår. Tom lista om inget.",
                "items": {"type": "string"},
            },
        },
        "required": list(SUMMARY_FIELDS),
        "additionalProperties": False,
    },
}

COMPACT_PROMPT = (
    "Sammanfatta samtalet ovan som anteckning till dig själv, på samtalets språk. "
    "Gå igenom samtalet uppifrån och ner: en post per ämne, med alla detaljer som "
    "nämndes där — namn, färg, siffra, datum, plats, titel, låt, film, åsikt och "
    "varför. "
    "Fyra fält: fakta, preferenser, beslut, oppna_uppgifter. "
    "fakta: posterna ovan, 'nyckel: värde, detalj, detalj'. "
    "preferenser: hur användaren vill ha svar och samarbete. "
    "beslut: vad som bestämts, med detaljer. oppna_uppgifter: det som återstår. "
    "Allt som inte passar i de andra fälten hör i fakta. "
    "Tappa en detalj är ett fel, en för lång post är inget fel. Beskrivande ord — "
    "färg, antal, ålder, skick — står alltid vid det de beskriver. "
    "Slå inte ihop två ämnen till en post. Bryt ner varje mening i sina fakta. "
    "Hellre en post för mycket än en för lite. Stryk bara småprat och upprepningar. "
    "Skriv inte om saker som inte nämndes. "
    "Tidigare sammanfattningar i samtalet är ofullständiga — bygg anteckningen från "
    "de riktiga meddelandena och använd sammanfattningarna bara som stöd. "
    "Grunt speak: fragment, inga hela meningar, ingen punkt i slutet, inga citattecken."
)

COMPACT_TEMPERATURE = 0.0

# Parametrar som en del modeller avvisar. Vi släpper dem bara om servern själv
# pekar på dem, aldrig i förebyggande syfte.
_DROP_KEYS = {
    "temperature": ("temperature",),
    "response_format": ("response_format", "json_schema"),
    "stream_options": ("stream_options", "include_usage"),
}


class LLMError(RuntimeError):
    """Fel som redan är formulerat för att visas i konsolen."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class Reply:
    text: str
    finish_reason: str | None = None
    usage: dict[str, int] | None = None
    model: str | None = None

    @property
    def truncated(self) -> bool:
        return self.finish_reason == "length"

    @property
    def usage_line(self) -> str:
        if not self.usage:
            return ""
        prompt = self.usage.get("prompt", 0)
        completion = self.usage.get("completion", 0)
        total = self.usage.get("total", prompt + completion)
        return f"tokens: {prompt} in, {completion} ut ({total} totalt)"


def _usage(obj: object | None) -> dict[str, int] | None:
    if obj is None:
        return None
    return {
        "prompt": getattr(obj, "prompt_tokens", 0) or 0,
        "completion": getattr(obj, "completion_tokens", 0) or 0,
        "total": getattr(obj, "total_tokens", 0) or 0,
    }


class LLM:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.system = (
            [{"role": "system", "content": SYSTEM_PROMPT}] if settings.persona else []
        )
        # max_retries=0: ett automatiskt nytt försök är en ny debiterad generering.
        self.client = OpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
            max_retries=0,
        )

    # -- hälsokontroll -----------------------------------------------------
    def models(self) -> list[str]:
        """Lista modeller. Kostar ingen generering och fångar en felaktig nyckel."""
        try:
            response = self.client.models.list()
        except Exception as exc:  # noqa: BLE001 - allt blir ett LLMError
            raise LLMError(str(exc).strip(), getattr(exc, "status_code", None)) from exc
        return [item.id for item in response.data]

    # -- anrop -------------------------------------------------------------
    def _create(self, params: dict) -> object:
        while True:
            try:
                return self.client.chat.completions.create(**params)
            except BadRequestError as exc:
                message = str(exc).lower()
                removable = [
                    key
                    for key, needles in _DROP_KEYS.items()
                    if key in params and any(needle in message for needle in needles)
                ]
                if not removable:
                    raise LLMError(
                        str(exc).strip(), getattr(exc, "status_code", None)
                    ) from exc
                for key in removable:
                    params.pop(key, None)
            except Exception as exc:  # noqa: BLE001
                raise LLMError(
                    str(exc).strip(), getattr(exc, "status_code", None)
                ) from exc

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        response_format: dict | None = None,
        stream: bool = True,
        on_chunk: Callable[[str], None] | None = None,
        use_persona: bool = True,
    ) -> Reply:
        payload = list(messages)
        if use_persona and self.system:
            payload = self.system + payload

        params: dict = {"model": model or self.settings.model, "messages": payload}
        if temperature is not None:
            params["temperature"] = temperature
        if response_format is not None:
            params["response_format"] = response_format
        if stream:
            params["stream"] = True
            params["stream_options"] = {"include_usage": True}

        result = self._create(params)

        if not stream:
            choice = result.choices[0]
            return Reply(
                text=(choice.message.content or "").strip(),
                finish_reason=choice.finish_reason,
                usage=_usage(getattr(result, "usage", None)),
                model=getattr(result, "model", None),
            )

        parts: list[str] = []
        finish_reason: str | None = None
        usage: dict[str, int] | None = None
        model_id: str | None = None

        try:
            for chunk in result:
                model_id = getattr(chunk, "model", None) or model_id
                usage = _usage(getattr(chunk, "usage", None)) or usage
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                piece = choice.delta.content or ""
                if piece:
                    parts.append(piece)
                    if on_chunk is not None:
                        on_chunk(piece)
                finish_reason = choice.finish_reason or finish_reason
        except Exception as exc:  # noqa: BLE001
            raise LLMError(
                str(exc).strip(), getattr(exc, "status_code", None)
            ) from exc

        return Reply(
            text="".join(parts).strip(),
            finish_reason=finish_reason,
            usage=usage,
            model=model_id,
        )

    # -- komprimering ------------------------------------------------------
    def compact(self, messages: list[dict[str, str]]) -> tuple[dict, str, Reply]:
        """Sammanfatta historiken till fyra fält och rendera den som text."""
        reply = self.complete(
            list(messages) + [{"role": "user", "content": COMPACT_PROMPT}],
            model=self.settings.compact_model,
            temperature=COMPACT_TEMPERATURE,
            response_format={"type": "json_schema", "json_schema": SUMMARY_SCHEMA},
            stream=False,
            use_persona=False,
        )
        summary = parse_summary(reply.text)
        return summary, render_summary(summary), reply


# --------------------------------------------------------------------------- #
#  Sammanfattning:tolkning och rendering
# --------------------------------------------------------------------------- #

def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _as_items(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []

    items: list[str] = []
    for item in value:
        if isinstance(item, str):
            cleaned = item.strip().strip("-*• ").strip()
            if cleaned:
                items.append(cleaned)
        elif isinstance(item, dict):
            parts = [f"{key}: {val}" for key, val in item.items() if val]
            if parts:
                items.append(", ".join(parts))
    return items


def _summary_from_text(text: str) -> dict[str, list[str]]:
    lines = [line.strip().strip("-*• ").strip() for line in text.splitlines()]
    summary = {field: [] for field in SUMMARY_FIELDS}
    summary["fakta"] = [line for line in lines if line]
    return summary


def parse_summary(raw: str) -> dict[str, list[str]]:
    """Tolka modellens JSON. Går det inte, räddas texten som fakta."""
    text = _strip_fence(raw)

    data: object = None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match is not None:
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                data = None

    if not isinstance(data, dict):
        return _summary_from_text(text)

    summary = {field: _as_items(data.get(field)) for field in SUMMARY_FIELDS}
    return summary


def render_summary(summary: dict[str, list[str]]) -> str:
    """Gör om fälten till den text som skickas tillbaka till modellen."""
    lines = [COMPACT_PREFIX]
    for field in SUMMARY_FIELDS:
        items = [item.rstrip(" .") for item in summary.get(field, []) if item.strip()]
        if items:
            lines.append(f"{field}: " + "; ".join(items))
    if len(lines) == 1:
        lines.append("fakta: -")
    return "\n".join(lines)


def summary_counts(summary: dict[str, list[str]]) -> str:
    """Kort kvitto på vad komprimeringen innehöll."""
    labels = {"fakta": "fakta", "preferenser": "preferenser", "beslut": "beslut",
              "oppna_uppgifter": "öppna uppgifter"}
    return ", ".join(
        f"{labels[field]}: {len(summary.get(field, []))}" for field in SUMMARY_FIELDS
    )
