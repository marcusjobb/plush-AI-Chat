# multipleAssistant

Webbchatt med fyra AI-assistenter (Ada, Bo, Kalle och Margareta) som pratar allmänt och ger tips och råd. Modellerna nås via 1min.AI:s OpenAI-kompatibla API.

## Om 1min.AI

1min.AI är en tjänst där ett konto och en nyckel ger tillgång till många olika AI-modeller.

- **15 000 credits gratis varje dag.** Du får dem genom att besöka webbappen. Dagen börjar 00:00 PST.
- **Referenslänken** är https://1min.ai?referrer_id=9b12faba-f8a3-49ea-bd25-d8343f1fd965. Den är en referenslänk, och upphovsmannen får en del av det som den som registrerar sig köper.
- Enligt 1min.AI:s sida just nu får den som registrerar sig via länken 5 000 credits när de går med, och 35 000 credits när de kör en AI-funktion första gången. Upphovsmannen får 5 % av köp i framtiden, och 50 % provision på prenumerationer.
- Villkoren kan ändras. Kontrollera dem på 1min.AI innan du räknar med något.

## Kom igång

```bash
cd multipleAssistant
cp .env.example .env        # fyll i ONEMIN_API_KEY
.venv/bin/python app.py     # http://127.0.0.1:8100
```

## Så chattar du

- Välj vem som ska svara ovanför inmatningsrutan: **Alla**, eller en enskild assistent. Assistenterna svarar i ordning, och varje svar ser de föregående.
- Skriv `@Kalle hej` och bara den namngivna svarar, oavsett vad som är valt. Svaret innehåller inget `@`.

## Konfiguration (`.env`)

| Variabel | Standard | Vad |
|---|---|---|
| `ONEMIN_API_KEY` | (krävs) | Din nyckel |
| `ONEMIN_BASE_URL` | 1min.AI:s endpoint | Byt om du använder ett annat OpenAI-kompatibelt API |
| `ASSISTANT_1_NAME`, `ASSISTANT_1_MODEL` | Ada, gpt-4o-mini | Första assistenten |
| `ASSISTANT_2_NAME`, `ASSISTANT_2_MODEL` | Bo, deepseek-v4-pro | Andra assistenten |
| `ASSISTANT_3_NAME`, `ASSISTANT_3_MODEL` | Kalle, qwen3.7-max | Tredje assistenten |
| `ASSISTANT_4_NAME`, `ASSISTANT_4_MODEL` | Margareta, glm-5.3 | Fjärde assistenten, trött, torr och ärlig |
| `DOCUMENT_MODEL` | Ada:s modell | Modellen som komprimerar dokument |
| `PORT` | 8100 | Porten servern lyssnar på |

## Tester

```bash
.venv/bin/python -m pytest -q
```

Testerna använder en falsk backend och kräver ingen nyckel.

## Sessioner och komprimering

- Varje session sparas i `sessions/<id>.jsonl`, en fil per session. Välj den i listrutan uppe till vänster, eller börja en ny med **Ny session**.
- **Komprimera** sammanfattar det modellen ser just nu och sparar sammanfattningen i loggen. Alla tidigare meddelanden finns kvar i filen, men modellen får bara sammanfattningen och de turer som kommit efter den.
- Efter 50 meddelanden sedan senaste komprimering körs komprimeringen automatiskt innan nästa meddelande skickas. Det syns i chatten som "Samtalet komprimerades."
- Modellen ser alltid de senaste 20 turerna efter sammanfattningen.

## Dokument

Ladda upp `.md`, `.txt` eller `.json` (max 100 KB) med knappen **Ladda upp** i webben, eller från terminalen:

```bash
.venv/bin/python upload.py mina-anteckningar.md
```

Varje fil sparas i `uploads/` två gånger: originalet och en komprimerad version (`<namn>.compact.md`) uppdelad i ämnen. Modellen för komprimeringen väljs med `DOCUMENT_MODEL` i `.env`, och faller tillbaka på Ada:s modell.

Kommandon i chatten:

| Kommando | Vad det gör |
|---|---|
| `/dokument` | Listar uppladdade dokument |
| `/ämnen <fil>` | Listar ämnena i ett dokument |
| `/prata <fil> <ämne>` | Väljer ett ämne. Assistenterna håller sig till det tills du skriver `/prata av` |
| `/prata av` | Släpper det valda ämnet |

Dokumentet läses bara när du ber om det. Ämnestexten skickas med varje meddelande medan ämnet är valt, men den sparas inte i samtalet.

## Begränsningar

- Svaren visas när hela svaret är klart, inte ord för ord.
- Modellnamnen är inte verifierade mot 1min.AI:s lista. Kontrollera dem innan du kör.
- Sessionsfilerna ligger lokalt i `sessions/` och committas aldrig.

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
