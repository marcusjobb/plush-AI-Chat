---
name: planner
description: Ställ fyra frågor innan ett nytt projekt startar (mål, kontext, krav och avgränsningar, klart när) och skriv ner svaren som en grund för projektet. Använd när användaren skriver /planner, vill skapa ett nytt projekt, starta något från början, eller säger att de vill ha en bra grund innan de börjar koda.
---

# Planner

Innan något byggs ställer du fyra frågor. Svaren blir en kort plan som projektet kan utgå från.

**Grundregler:**
- Ställ frågor tills du har tillräckligt för att göra uppgiften bra.
- Börja inte koda och föreslå ingen lösning än.

## Steg 1: Ställ frågorna

Ställ de fyra frågorna i den här ordningen.

**Använd TUI-frågedialogen (AskUserQuestion) när svaret kan väljas bland ett fåtal alternativ.** Exempel: vilket projekt eller vilken mapp det gäller, ja eller nej på en avgränsning, vilket ramverk eller språk, eller vilken av två varianter som gäller. Regler:
- Max 4 frågor per anrop, och 2–4 alternativ per fråga.
- Det rekommenderade alternativet står först och får "(Recommended)" i etiketten.
- Alternativen ska vara ömsesidigt uteslutande, eller använd `multiSelect` när flera kan gälla.
- Lägg ingen "Annat"-option, den läggs till automatiskt.

**Använd fri text när svaret är öppet.** Mål, klart när och detaljer i krav ställs som vanliga frågor. Be användaren svara i egna ord, gärna punktform.

Förslag på uppdelning: ställ de kategoriska frågorna (vilken del, ja/nej, vilket ramverk) i TUI, och de öppna (mål, klart när) i text.

1. **Mål:** Vad ska uppnås, och varför?
2. **Kontext:** Vilka filer, vilket ramverk, vad finns redan?
3. **Krav och avgränsningar:** Vad måste gälla, och vad får inte hända?
4. **Klart när:** Hur vet vi att vi är klara?

Om användaren redan har gett svar på någon fråga i sitt meddelande, bekräfta den och fråga bara om det som saknas.

Om ett svar är för vagt för att planen ska bli bra, ställ en följdfråga om just det. Fortsätt tills du kan skriva en plan som någon annan kan bygga utifrån utan att gissa. Ställ följdfrågor i små omgångar, inte alla på en gång, och stanna när svaren räcker.

## Steg 1b: Lösningsfri fas

Under hela frågefasen gäller:
- Skriv ingen kod, skapa inga filer och kör inga kommandon för att bygga något. Läsning av befintliga filer för kontext är tillåten.
- Föreslå ingen lösning, arkitektur, ramverk eller modell innan användaren har svarat på frågorna. Om användaren själv nämner en lösning, notera den som en önskan och fråga varför den valts, i stället för att gå vidare med den.

## Steg 2: Kontrollera svaren

Innan du skriver planen, granska svaren:

- Är målet konkret, eller bara en önskan? Om det är vagt, föreslå en formulering och be om bekräftelse.
- Finns det motsägelser mellan mål, krav och avgränsningar?
- Är "klart när" mätbart eller observerbart? "Det fungerar" räcker inte. Föreslå ett kriterium som kan testas.
- Finns kontexten i en befintlig mapp? Om ja, läs den innan planen skrivs.

Om något är otydligt, fråga en gång till. Annars fortsätt.

## Steg 3: Skriv planen

Skriv filen `PLAN.md` i projektets rotmapp, eller i den mapp användaren anger. Använd den här strukturen:

```markdown
# Plan: <projektnamn>

## Mål
<mål och varför>

## Kontext
<filer, ramverk, befintligt material>

## Krav och avgränsningar
- Måste: ...
- Får inte: ...
- Utanför scope: ...

## Klart när
- [ ] <mätbart kriterium>
- [ ] ...
```

Skriv svaren så kort och konkret som möjligt. Ändra inte användarens formuleringar utan att säga det.

## Steg 4: Avsluta

Visa planen för användaren och fråga om något ska ändras innan projektet startar. Skriv inte kod i det här steget.

Om användaren vill köra något annat i samma session, t.ex. `/keeplogg` för att logga projektet, nämn det som ett förslag och kör det inte själv.
