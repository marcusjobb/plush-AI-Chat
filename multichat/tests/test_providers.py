"""Val av leverantör: rätt bas-URL och nyckel, och tydliga fel utan att läcka nyckeln."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from providers import PRESETS, ProviderError, resolve  # noqa: E402


def test_standard_ar_1min():
    name, url, key = resolve({"ONEMIN_API_KEY": "k1"})
    assert (name, url, key) == ("1min", "https://api.1min.ai/openai/v1", "k1")

@pytest.mark.parametrize("name", ["openai", "anthropic", "openrouter"])
def test_varje_forval_anvander_sin_nyckel(name):
    base, key_var = PRESETS[name]
    got_name, got_url, got_key = resolve({"PROVIDER": name, key_var: "hemlig", "ONEMIN_API_KEY": "fel"})
    assert (got_name, got_url, got_key) == (name, base, "hemlig")

def test_namnet_ar_skiftlageskansligt():
    assert resolve({"PROVIDER": "OpenRouter", "OPENROUTER_API_KEY": "k"})[0] == "openrouter"

def test_custom_anvander_egen_url_och_nyckel():
    name, url, key = resolve({"PROVIDER": "custom", "CUSTOM_BASE_URL": "https://ex.se/v1", "CUSTOM_API_KEY": "k"})
    assert (name, url, key) == ("custom", "https://ex.se/v1", "k")

def test_saknad_nyckel_nämner_variabeln_men_inte_nagot_varde():
    with pytest.raises(ProviderError) as info:
        resolve({"PROVIDER": "openai"})
    assert "OPENAI_API_KEY" in str(info.value)

def test_okand_leverantor_ger_fel():
    with pytest.raises(ProviderError, match="Okänd PROVIDER"):
        resolve({"PROVIDER": "gemini", "ONEMIN_API_KEY": "k"})

def test_custom_utan_url_ger_fel():
    with pytest.raises(ProviderError, match="CUSTOM_BASE_URL"):
        resolve({"PROVIDER": "custom", "CUSTOM_API_KEY": "k"})

def test_felmeddelanden_innehaller_aldrig_nyckeln():
    with pytest.raises(ProviderError) as info:
        resolve({"PROVIDER": "okand", "OPENAI_API_KEY": "superhemlig"})
    assert "superhemlig" not in str(info.value)
