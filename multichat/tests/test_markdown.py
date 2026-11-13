"""Markdown i chatten: renderaren måste escapa allt och bara släppa igenom godkända taggar."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parent.parent / "static" / "markdown.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node saknas")


def render(text):
    code = f"const m = require({json.dumps(str(JS))}); process.stdout.write(m.render({json.dumps(text)}));"
    return subprocess.run([NODE, "-e", code], capture_output=True, text=True, check=True).stdout


def test_html_escapas():
    out = render("<script>alert(1)</script>")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out

def test_fet_och_kursiv():
    out = render("**hej** och *där*")
    assert "<strong>hej</strong>" in out
    assert "<em>där</em>" in out

def test_kod_och_kodblock():
    assert "<code>kod</code>" in render("`kod`")
    out = render("```\n<b>x</b>\n```")
    assert "<pre><code>&lt;b&gt;x&lt;/b&gt;</code></pre>" in out

def test_listor():
    out = render("- ett\n- två")
    assert "<ul><li>ett</li><li>två</li></ul>" in out
    assert "<ol><li>första</li></ol>" in render("1. första")

def test_rubriker():
    assert "<h3>Titel</h3>" in render("# Titel")

def test_bara_http_lankar():
    assert 'href="https://x.se"' in render("[länk](https://x.se)")
    assert "<a" not in render("[klicka](javascript:alert(1))")

def test_attribut_kan_inte_brytas():
    out = render('[x](https://x.se" onmouseover="alert(1))')
    assert "onmouseover" not in out or "&quot;" in out


def test_tabell():
    out = render("| 1 | 2 |\n|---|---|\n| 3 | 4 |")
    assert "<table>" in out
    assert "<th>1</th><th>2</th>" in out
    assert "<td>3</td><td>4</td>" in out


def test_kombinerad_formatering():
    assert "<strong><em>coolt</em></strong>" in render("***coolt***")
    assert "<strong><em>najs</em></strong>" in render("_**najs**_")
    assert "<em>kursiv</em>" in render("_kursiv_")


def test_namn_med_snabel_ar_fet():
    assert "<strong>@Margareta</strong>" in render("Fråga @Margareta om det")
    assert "<strong>" not in render("mejla mig@exempel.se")


def test_ra_url_blir_lank():
    out = render("besök https://www.expressen.se/ nu")
    assert 'href="https://www.expressen.se/"' in out

def test_url_i_markdownlank_dubbellankas_inte():
    out = render("[https://x.se](https://x.se)")
    assert out.count("<a ") == 1


def test_namn_med_liten_bokstav_ar_fet():
    assert "<strong>@margareta</strong> hej" in render("@margareta hej")
