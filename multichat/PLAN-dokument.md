# Plan: Dokumentuppladdning i multipleAssistant

## Mål
Användaren ska kunna ladda upp egna dokument, och assistenterna ska kunna prata om dem med fakta som utgångspunkt. Dokumenten ska bara läsas när användaren ber om det.

## Kontext
- Projekt: `Modul05/multipleAssistant/` (Bottle, OpenAI-SDK mot 1min.AI, sessioner i `sessions/*.jsonl`, komprimering via `ChatRoom.compact`).
- Uppladdning ska gå att göra både i webbchatten och med ett terminalkommando.
- Originalfiler sparas i `uploads/`. Den komprimerade versionen sparas bredvid originalet.

## Krav och avgränsningar
- Måste:
  - Filtyper: `.md` och `.txt`. Andra filtyper avvisas med ett tydligt felmeddelande.
  - Max 100 KB text per fil. Större filer avvisas och sparas inte.
  - Varje fil komprimeras vid uppladdning. Det är inget valfritt steg.
  - Assistenterna läser dokumenten endast när användaren uttryckligen ber om det.
  - Användaren kan välja ett ämne från dokumentet och få assistenterna att prata om det.
  - Dokumenten ska innehålla fakta, och assistenterna ska hålla sig till dem när de svarar om dokumentet.
- Får inte hända:
  - Hela dokumentet skickas inte med i vanliga meddelanden.
  - Filer utanför `uploads/` läses aldrig.
  - Inga personuppgifter eller studerandeuppgifter i filerna.
- Utanför scope:
  - PDF och andra format.
  - Streaming.

## Antaganden (ändra om du vill)
- Uppladdade dokument delas mellan alla sessioner, inte per session. Det är inte bekräftat.
- Radering av dokument ingår inte i första versionen. Det är inte bekräftat.
- Befintlig chatt ändras inte: sessioner, `/compact`, `@namn`-routing och automatisk komprimering fungerar som idag.
- Komprimeringen görs med samma modell som `ChatRoom` använder för sammanfattningar.
- Den här planen gäller bara dokumentfunktionen. Övriga uppgraderingsmål är inte med ännu.

## Klart när
- [ ] En `.md`-fil som laddas upp i webben hamnar i `uploads/` och får en komprimerad version bredvid sig.
- [ ] Samma sak fungerar med ett terminalkommando.
- [ ] En fil över 100 KB avvisas med ett felmeddelande och sparas inte.
- [ ] En fil med annan filtyp än `.md` eller `.txt` avvisas.
- [ ] Ett vanligt meddelande som inte ber om dokument leder inte till att dokumentet läses. Testas med en falsk backend som kontrollerar att dokumentinnehållet inte skickas.
- [ ] Användaren kan be assistenten lista ämnen från ett dokument, välja ett och få svar om det.
- [ ] Tester går igenom för storleksgräns, filtyp och att dokument inte läses när de inte begärts.
