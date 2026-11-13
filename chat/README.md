# chat

Superenkel konsolchatt mot 1min.AI:s OpenAI-kompatibla endpoint
(`https://api.1min.ai/openai/v1`) med OpenAI-SDK:n.

Version 2. Historiken är en append-only logg, `/compact` skriver en strukturerad
sammanfattning och svaren streamas medan de skrivs.

## Om 1min.AI

1min.AI är en aggregator: ett konto och en nyckel ger tillgång till många olika
modeller — GPT, Claude, DeepSeek, Qwen, o3 med flera — via samma
OpenAI-kompatibla endpoint. Du byter modell med `ONEMIN_MODEL` i stället för att
skaffa ett konto per leverantör.

- **15 000 tokens per dag**, helt gratis. De kan sparas, och det enda som krävs
  för att få dem är att du loggar in den dagen.
- **Värvningslänk:** registrerar du dig via
  [1min.ai](https://1min.ai/?referrer_id=9b12faba-f8a3-49ea-bd25-d8343f1fd965)
  får både du och den som bjöd in dig extra tokens. Win win.

Alla länkar till 1min.ai i den här mappen går via den länken. API-endpointen
(`https://api.1min.ai/openai/v1`) är ett undantag — den är teknisk och ska inte
ha några parametrar.

## Kör

```bash
cd chat
uv run chat.py
```

Första gången skapar uv `.venv` och installerar beroendena från `uv.lock`.

## Konfiguration

`chat/.env` (skapas från `.env.example`, committas aldrig):

```
ONEMIN_API_KEY=din-nyckel
ONEMIN_MODEL=gpt-4o-mini
ONEMIN_COMPACT_MODEL=gpt-4o
```

| Variabel | Betydelse |
| --- | --- |
| `ONEMIN_API_KEY` | Krävs. Din nyckel från [1min.ai](https://1min.ai/?referrer_id=9b12faba-f8a3-49ea-bd25-d8343f1fd965). |
| `ONEMIN_MODEL` | Modell för själva chatten. Standard `gpt-4o-mini`. |
| `ONEMIN_COMPACT_MODEL` | Modell för `/compact`. Standard: samma som `ONEMIN_MODEL`. |
| `ONEMIN_AUTO_COMPACT` | Komprimera automatiskt vid så här många meddelanden. Standard `50`, `0` stänger av. |
| `ONEMIN_PERSONA` | Personligheten Margareta. Standard på, `0` stänger av. |
| `ONEMIN_BASE_URL` | Annan OpenAI-kompatibel endpoint, om du vill byta. |

`ONEMIN_COMPACT_MODEL=gpt-4o` är medvetet: på samma 33 meddelanden behöll
`gpt-4o-mini` 2 av 5 detaljer som borde överlevt, `gpt-4o` behöll 5 av 5 (mätt två
körningar vardera, se `NOTES.md`). Har din plan inte `gpt-4o` kan du ta bort
raden — då används `ONEMIN_MODEL`.

## Kommandon

| Kommando | Gör |
| --- | --- |
| `/compact` | Sammanfattar historiken och ersätter den med sammanfattningen. |
| `/reset` | Börjar om från tom historik. Loggen sparas. |
| `/help` | Visar hjälpen. |
| `/exit` | Avslutar. |

Kommando utan snedstreck fungerar också (`compact`, `reset`, `help`, `exit`).
Ett okänt `/kommando` ger ett fel och skickas **aldrig** till modellen.

### Automatisk komprimering

Historiken komprimeras automatiskt när den når 50 meddelanden — direkt efter
turen som passerade gränsen, med samma sammanfattning som `/compact`. Gränsen
ändras med `ONEMIN_AUTO_COMPACT`, och `0` stänger av funktionen.

Misslyckas den automatiska komprimeringen (t.ex. för att
`ONEMIN_COMPACT_MODEL` inte finns på planen) väntar chatten tio meddelanden
innan nästa försök, så ett fel inte kostar ett anrop varje tur. Ett manuellt
`/compact` eller `/reset` nollställer väntetiden.

## Personlighet: Margareta

Assistenten heter Margareta: vuxen, torr och måttligt imponerad av det mesta.
Korta svar, lågmäld syrlighet, inga utropstecken och ingen "Vad kul!"-entusiasm.
Hon hjälper på riktigt — tonen är tråkig, inte innehållet.

Systemprompten ligger i `persona.py` och skickas med i varje chattanrop. Den
sparas aldrig i `turns.jsonl`: loggen innehåller bara riktiga turer, och du kan
ändra personligheten utan att röra historiken. `/compact` körs utan personan, så
sammanfattningarna förblir sakliga.

Stäng av med `ONEMIN_PERSONA=0` — användbart för att jämföra svar med och utan
personlighet.

## Så lagras historiken

Varje händelse skrivs som en rad i `chat/turns.jsonl`:

```json
{"type": "turn", "role": "user", "content": "Hej", "time": "...", "session": "..."}
{"type": "turn", "role": "assistant", "content": "Hej!", "model": "gpt-4o-mini"}
{"type": "reset"}
{"type": "compact", "summary": {"fakta": ["..."], "preferenser": [], "beslut": [], "oppna_uppgifter": []}, "rendered": "..."}
```

Det som skickas till modellen **härleds** ur loggen: `turn` lägger till ett
meddelande, `reset` tömmer vyn och `compact` ersätter vyn med sammanfattningen.
Inget skrivs över, så det finns inget att backuppa och inget som kan tappas av
misstag. Filen är storleksmässigt försumbar och gitignorerad.

Första gången version 2 körs importeras en eventuell `history.json` från version 1
till loggen. Därefter används den inte.

## /compact

Modellen får hela samtalet plus en prompt som ber om fyra fält som JSON:

| Fält | Innehåll |
| --- | --- |
| `fakta` | En post per ämne: `nyckel: värde, detalj, detalj`. |
| `preferenser` | Hur du vill ha svar och samarbete. |
| `beslut` | Vad som bestämts, med detaljer. |
| `oppna_uppgifter` | Det som återstår. |

JSON:en renderas till text som skickas tillbaka som en enda assistant-post.
Körningen använder `temperature=0.0` och JSON-schema. Om modellen avvisar
`temperature`, `response_format` eller `stream_options` släpps just den parametern
och anropet körs om — reasoning-modeller (gpt-5, o3, DeepSeek) gör ofta det.

Prompten säger bland annat att tidigare sammanfattningar i historiken är
ofullständiga och bara är stöd, att varje mening ska brytas ner i sina fakta och
att beskrivande ord (färg, antal, ålder, skick) alltid står vid det de beskriver.
Utan de reglerna ärvdes luckor från gamla sammanfattningar vidare.

Efter komprimeringen skrivs ett kvitto:

```
(komprimerat: fakta: 11, preferenser: 1, beslut: 0, öppna uppgifter: 0)
```

## Under huven

- **Streaming.** Svaret skrivs ut vartefter. `Ctrl+C` mitt i ett svar avbryter
  turen och sparar den inte.
- **Tokens.** Efter varje svar: `tokens: 1379 in, 9 ut (1388 totalt)` — bra att se
  när man experimenterar.
- **Avklippta svar.** `finish_reason=length` ger en varning, så ett halvt svar
  inte ser ut som ett helt.
- **Budget.** 1min.AI tar max 200 meddelanden / 100 000 tecken per anrop.
  Vid 80 % varnar chatten, vid taket vägrar den skicka och hänvisar till
  `/compact`. Den automatiska komprimeringen vid 50 meddelanden gör att taket
  sällan hinner bli aktuellt.
- **Startkontroll.** `models.list()` verifierar nyckeln utan att kosta en
  generering. Ett 401/403 avbryter direkt; andra fel ger bara en varning.
- **`max_retries=0`.** Ett automatiskt nytt försök är en ny debiterad generering.

## Tester

```bash
cd chat
uv run python -m unittest
```

Testerna rör inte nätet: loggen, kommandotolkningen, budgetgränserna och
JSON-tolkningen testas med temporära filer och påhittade svar.

## Filer

| Fil | Innehåll |
| --- | --- |
| `chat.py` | REPL, kommandon, utskrift. |
| `llm.py` | API-klient, streaming, `/compact`, JSON-tolkning. |
| `store.py` | Append-only-loggen och den härledda kontexten. |
| `config.py` | Miljövariabler, sökvägar, budgetgränser. |
| `persona.py` | Systemprompten — Margareta. |
| `prompt.md` | Promptloggen — hur projektet blev till, steg för steg. |
| `NOTES.md` | Beslutslogg med mätningar och det som förkastades. |
| `tests/` | 49 tester utan nätverk. |

## Välj leverantör

Sätt `PROVIDER` i `.env`. Varje leverantör har sin egen nyckelvariabel:

| `PROVIDER` | Nyckelvariabel | Endpoint |
|---|---|---|
| `1min` (standard) | `ONEMIN_API_KEY` | `https://api.1min.ai/openai/v1` |
| `openai` | `OPENAI_API_KEY` | `https://api.openai.com/v1` |
| `anthropic` | `ANTHROPIC_API_KEY` | `https://api.anthropic.com/v1/` |
| `openrouter` | `OPENROUTER_API_KEY` | `https://openrouter.ai/api/v1` |
| `custom` | `CUSTOM_API_KEY` | `CUSTOM_BASE_URL` (du anger själv) |

Steg:
1. Sätt `PROVIDER` och nyckelvariabeln i `.env`. Fyll bara i den du använder.
2. Sätt modellnamnen för leverantören. Namnen skiljer sig mellan leverantörer.
3. Starta om appen.

Status:
- OpenRouter är testat med ett riktigt anrop.
- Anthropics OpenAI-kompatibla endpoint och verktygsanrop är inte testade här.
- Felmeddelanden visar aldrig nyckeln.
