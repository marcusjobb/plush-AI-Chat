"""Val av leverantör. Välj med PROVIDER i .env. Varje leverantör har sin egen nyckelvariabel.

Alla leverantörer nås via en OpenAI-kompatibel endpoint. Modellnamnen i .env måste passa
den leverantör som valts.
"""

from __future__ import annotations

from collections.abc import Mapping

# namn: (bas-URL, nyckelvariabel)
PRESETS: dict[str, tuple[str, str]] = {
    "1min": ("https://api.1min.ai/openai/v1", "ONEMIN_API_KEY"),
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
    "anthropic": ("https://api.anthropic.com/v1/", "ANTHROPIC_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
}
CUSTOM = "custom"  # egen endpoint: CUSTOM_BASE_URL och CUSTOM_API_KEY


class ProviderError(ValueError):
    """Fel i leverantörsinställningen. Meddelandet innehåller aldrig nyckeln."""


def resolve(env: Mapping[str, str]) -> tuple[str, str, str]:
    """Returnerar (leverantör, bas-URL, API-nyckel) utifrån miljön."""
    name = (env.get("PROVIDER") or "1min").strip().lower()

    if name == CUSTOM:
        base_url = (env.get("CUSTOM_BASE_URL") or "").strip()
        key_var = "CUSTOM_API_KEY"
        if not base_url:
            raise ProviderError("CUSTOM_BASE_URL saknas för PROVIDER=custom.")
    elif name in PRESETS:
        base_url, key_var = PRESETS[name]
    else:
        choices = ", ".join([*PRESETS, CUSTOM])
        raise ProviderError(f"Okänd PROVIDER '{name}'. Välj en av: {choices}.")

    api_key = (env.get(key_var) or "").strip()
    if not api_key:
        raise ProviderError(f"{key_var} saknas för PROVIDER={name} (se .env.example).")
    return name, base_url, api_key
