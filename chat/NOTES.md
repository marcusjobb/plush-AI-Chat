# NOTES — varför version 2 ser ut som den gör

Beslutslogg. Mätningarna är gjorda mot 1min.AI med `gpt-4o-mini` om inget annat
sägs, på den importerade historiken med 33 meddelanden.

## Loggen i stället för filen som skrivs över

Version 1 hade `history.json` som både körtidstillstånd och det som skickades
till modellen. Varje ny funktion tvingade fram en ny sorts backup, och till slut
fanns åtta nästan identiska filer där tidsstämpeln var enda ledtråden om varför
filen fanns.

Version 2 har en append-only-logg (`turns.jsonl`) och härleder kontexten ur den.
`reset` och `/compact` är vanliga händelser i loggen, inte operationer som
förstör något. En backupfil är ett symptom på förstörande primärlagring — nu
behövs ingen.

## Sammanfattningen är JSON med fyra fält

En fri textrad gav nyckeldrift: `intresse:`, `intressen:`, `musik:`, `musik av:`
— samma sak i fyra skepnader. Fyra fasta fält (`fakta`, `preferenser`, `beslut`,
`oppna_uppgifter`) ger ett kvitto som går att läsa och räkna:

```
(komprimerat: fakta: 11, preferenser: 1, beslut: 0, öppna uppgifter: 0)
```

Fälten renderas till text innan de skickas tillbaka, så modellen ser samma sorts
anteckning som förut.

## Modellvalet var den stora vinsten

Samma historik, samma prompt, samma `temperature=0.0`. Kontrollen var fem
detaljer som borde överleva: kattfärg, Evil Dead-åsikten, yrket, Taylor Swift som
intresse och låttitlarna.

| Uppsättning | Träffar | Körningar |
| --- | --- | --- |
| `gpt-4o-mini`, JSON-schema | 2/5 | 3 |
| `gpt-4o-mini`, ingen `response_format` | 3/5 | 3 |
| `gpt-4o-mini`, gamla sammanfattningar bortplockade | 2/5 | 3 |
| `gpt-4.1-mini`, JSON-schema | 4/5 | 2 |
| `gpt-4o`, JSON-schema | **5/5** | 2 |

Slutsats: promptjustering mot en för liten modell gav brus. `gpt-4o` för
`/compact` löste på två rader det som fem promptvarv inte klarade. Därför är
`ONEMIN_COMPACT_MODEL=gpt-4o` med i `.env.example`, med en kommentar om att raden
kan tas bort.

Att plocka bort gamla sammanfattningar ur indata hjälpte inte i den här mätningen.
Däremot var det avgörande i version 1, där anti-anchoring-raden tog Evil Dead från
0/6 till att förekomma i majoriteten av körningarna. Raden är kvar:
tidigare sammanfattningar behandlas som ofullständigt stöd, aldrig som sanning.

## Förkastat efter mätning

| Försök | Utfall |
| --- | --- |
| Kontrollpass: "lista vad som saknas i anteckningen" | svarade `OK.` trots att två av fem detaljer saknades |
| Revisionspass: "komplettera anteckningen" | returnerade exakt samma text som första passet |
| Välj längsta av fyra kandidater | ingen korrelation — längst var inte mest komplett |
| Flera rader i stället för en rad | 0/3 full täckning, samma som en rad |
| Heuristik som varnar för tappade egennamn | för mycket brus: `Bruce Campbell`, `Användare`, `Favoritlåtar` |

Kontrollpasset kostade ett extra anrop per `/compact` utan att tillföra något.
Det finns inte i version 2. Inte heller någon automatisk "täckningskontroll" —
den enda kontroll som visade sig fungera var att byta till en starkare modell.

## Temperaturen

`/compact` kör med `temperature=0.0`. 1min.AI varierar ändå mellan anrop — samma
prompt och samma historik kan ge olika sammanfattningar. Parametern skickas bara
med på kompakteringen, och om servern avvisar den (`BadRequestError` som nämner
`temperature`) körs anropet om utan den. Samma mekanism släpper
`response_format` och `stream_options`, så `/compact` fungerar även på
reasoning-modeller.

## Automatisk komprimering vid 50 meddelanden

50 är valt för att ligga klart under 1min.AI:s tak på 200 meddelanden, men över
den importerade historiken på 33 — alltså komprimeras det gamla samtalet inte
direkt vid uppstart. Det ger också ungefär 25 turer mellan varje komprimering.

Komprimeringen körs efter turen som passerade gränsen, så svaret användaren just
fick är med i sammanfattningen. Den använder samma kodväg som `/compact`, vilket
innebär samma modell, samma JSON-fält och samma kvitto.

Två detaljer som inte syns i README:

- **Bara efter en lyckad tur.** Om anropet misslyckas (nätfel, tomt svar) triggas
  ingen komprimering — annars hade ett fel kostat två anrop.
- **Tio meddelandens väntetid efter ett misslyckat försök.** Ett fel som beror på
  fel modellnamn eller avsaknad av `gpt-4o` skulle annars upprepas varje tur.
  Väntetiden nollställs av ett lyckat manuellt `/compact` eller `/reset`.

## Personligheten och 1min.AI:s innehållsfilter

Första versionen av personaprompten innehöll raden "Du suckar inombords men
hjälper till. Du är inte svår, bara omotiverad." Med den fick korta hälsningar
som `hej`, `Hej där` och `Tja` ett deterministiskt
`400 Messages violate the content policy` — medan `Hej ` (släpande mellanslag)
och `Hej!` gick igenom. Utan persona gick samma fråga alltid igenom.

Bisectning pekade ut just den raden. Att byta till "Du är inte svår, bara
omotiverad, men du hjälper till" gav 8/8 lyckade anrop över fyra hälsningar.
Slutsatsen är inte att ordet "suckar" är förbjudet — raden ensam gick igenom —
utan att aggregatorns filter är känsligt för kombinationen. Formuleringen står
kvar här i NOTES i stället för i prompten.

Chatten lägger till en ledtråd när felet innehåller "content policy", så nästa
gång går det snabbare att förstå vad som hände.

## Det som inte är löst

- **Full täckning är inte garanterad.** Även `gpt-4o` kan tappa en detalj. Vill
  man ha garanti är chunkad komprimering rätt verktyg: sammanfatta ~10 meddelanden
  i taget och slå ihop. Priset är flera anrop och att formatet inte längre blir en
  enda anteckning. Inte byggt.
- **Ingen kostnadsräkning i kronor.** `usage` visas per tur, men 1min.AI:s
  prissättning är per modell och kan ändras.
- **`/compact` kan inte avbrytas halvvägs** eftersom det inte streamas. Ett
  avbrott ger ett `LLMError` och historiken är oförändrad — men anropet är redan
  debiterat.
