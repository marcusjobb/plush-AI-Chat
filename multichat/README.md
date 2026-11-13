# multipleAssistant

Webbchatt med fyra AI-assistenter (Ada, Bo, Kalle och Margareta) som pratar allmänt och ger tips och råd. Modellerna nås via 1min.AI:s OpenAI-kompatibla API.

## Om 1min.AI

[1min.AI](https://1min.ai/?referrer_id=9b12faba-f8a3-49ea-bd25-d8343f1fd965) är en tjänst där du kan använda många olika AI-modeller på ett ställe.

- Gratisnivån ger **15 000 tokens per dag**. Tokens som inte används kan sparas.
- För att få dagliga tokens räcker det att logga in varje dag.
- Länken ovan är en referenslänk. Om du registrerar dig via den får både du och upphovsmannen extra tokens.

API-nyckeln skapas i ditt 1min.AI-konto och läggs i `.env`. Endpointen är `https://api.1min.ai/openai/v1`.

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
| `ASSISTANT_4_NAME`, `ASSISTANT_4_MODEL` | Margareta, glm-5.3 | Fjärde assistenten, med språklärarpersonlighet |
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

## Byt leverantör

Appen pratar med vilken OpenAI-kompatibel endpoint som helst. Byt leverantör i `.env` med två variabler: `ONEMIN_BASE_URL` och `ONEMIN_API_KEY`. Variablerna heter `ONEMIN_*` av historiska skäl, men fungerar för alla leverantörer.

| Leverantör | `ONEMIN_BASE_URL` | Exempel på modellnamn |
|---|---|---|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini`, `gpt-4.1-mini` |
| Anthropic | `https://api.anthropic.com/v1/` | `claude-haiku-5-5`, `claude-sonnet-5-5` |
| OpenRouter | `https://openrouter.ai/api/v1` | `openai/gpt-4o-mini`, `anthropic/claude-haiku-5-5` |

Steg:
1. Skapa en API-nyckel hos leverantören.
2. Sätt `ONEMIN_BASE_URL` och `ONEMIN_API_KEY` i `.env`.
3. Sätt modellnamnen enligt leverantörens lista. Namnen varierar mellan leverantörer.
4. Starta om appen och skicka ett kort testmeddelande.

Tänk på att:
- Använd en leverantör i taget. Blanda inte nycklar och endpoints i samma `.env`.
- Kontrollera att modellen klarar verktygsanrop, om du använder verktygen i `multichat`. Anthropics och OpenRouters OpenAI-kompatibla endpoints är inte testade i det här projektet.
- Kostnaden varierar stort mellan modeller. Kontrollera prislistan hos leverantören innan du börjar.
