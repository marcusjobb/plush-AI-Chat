---
name: cleancode
description: Refaktorera kod enligt clean code-principerna SRP, SoC, DRY, KISS och mänskligt läsbar kod. Använd när användaren skriver /cleancode, ber om clean code, städa upp koden, refaktorera för läsbarhet, eller vill att en fil ska bli enklare att läsa och underhålla. Bevarar beteendet och verifierar med tester.
---

# Clean code

Refaktorera utan att ändra beteende. Målet är kod som är lätt att läsa, ändra och testa.

## Principer

- **SRP (Single Responsibility):** varje funktion och klass gör en sak och har en anledning att ändras. Blandar funktionen validering, beräkning och utskrift? Dela upp den.
- **SoC (Separation of Concerns):** rendera inte, beräkna inte och validera inte i samma funktion. Beräkningar ska kunna köras och testas utan I/O. `print` och `input` hör hemma i ett tunt lager längst ut, t.ex. `main()`.
- **DRY (Don't Repeat Yourself):** samma logik på två ställen ska bli en funktion. Upprepade kontroller ska bli hjälpfunktioner med tydliga namn, t.ex. `_is_int(value)`.
- **KISS (Keep It Simple):** välj den enklaste lösningen som fungerar. Ta bort abstraktioner som inte används, onödiga mellanvariabler och kod som ingen behöver. Lägg inte till mönster i förväg.
- **Mänskligt läsbar kod:**
  - Namn ska säga vad något är eller gör. Undvik `x`, `tmp`, `data2`, `flag`.
  - Magiska tal och strängar får namn i en konstant.
  - Funktioner är korta och gör en sak. Om du behöver en kommentar för att förklara vad ett block gör, kan blocket bli en funktion med ett bra namn.
  - Håll en nivå av abstraktion per funktion.
  - Ingen oanvänd kod, variabel eller import.
  - Tidiga returer och `raise` i stället för djup nästling.
  - Tydlig ordning: publika funktioner först eller sist, hjälpfunktioner med `_`-prefix.

## Dela upp långa filer och klasser

Dela upp när en fil blir svår att överblicka, eller när en fil har flera ansvar som kan namnges var för sig (t.ex. validering och beräkning).

- **Ett ansvar per klass.** Namnge klassen efter ansvaret: `ItemValidator`, `VatCalculator`, `InvoiceRepository`. Undvik namn som `Manager`, `Helper` eller `Util`.
- **En fil per klass** när klassen är tillräckligt stor för att ha en egen fil. Filnamnet följer projektets konvention (t.ex. `snake_case.py`).
- **Injicera beroenden via konstruktorn** i stället för att skapa dem inne i klassen. Då kan du testa klassen i isolering och byta ut delar. Ge en rimlig standard om det går: `def __init__(self, validator: ItemValidator | None = None)`.
- **Klassen ska hålla sitt tillstånd privat.** Använd `_`-prefix för interna metoder och attribut. Offentliga metoder beskriver vad klassen gör.
- **Behåll den publika ytan.** Funktioner och klasser som tester eller andra moduler använder ska fortfarande gå att importera. Om namnen ändras, uppdatera importerna i tester och anropare i samma steg.
- **Gör inte klasser i onödan.** En klass utan tillstånd med en enda metod är oftast bättre som funktion (KISS).
- **Kontrollera beroenden efter uppdelningen.** Det ska inte finnas cirkulära imports. Gemensamma typer, t.ex. en typalias som `Item`, placeras i den modul som ägar begreppet.
- **Kör testerna efter varje uppdelning** och kontrollera att programmet fortfarande fungerar när det körs direkt.

## Arbetssätt

1. **Läs hela filen** och tester innan du ändrar något.
2. **Lista problemen** kort, grupperat per princip (SRP, SoC, DRY, KISS, läsbarhet). Ange radnummer.
3. **Gör ändringarna i små steg.** Kör testerna efter varje steg som ändrar struktur, inte bara i slutet.
4. **Bevara beteendet.** Samma publika funktioner, samma returvärden och samma felmeddelanden om tester eller användare förväntar sig dem. Ändra inte tester för att få dem gröna.
5. **Om projektet har regler** (t.ex. `AGENTS.md` eller `CLAUDE.md`) följ dem. Exempel: docstring på publika funktioner, tester för ny logik, svenska i användarvända texter.
6. **Kör testerna** och rapportera resultatet. Säg om något inte gick igenom.
7. **Avsluta med en kort sammanfattning:** vad som ändrades, varför, och eventuella val du gjorde som användaren kan vilja ändra.

## Vad du inte gör

- Lägger inte till nya funktioner, beroenden eller beteenden.
- Gör inte commit eller push om inte användaren ber om det.
- Refaktorerar inte kod utanför det användaren pekat ut, om det inte är nödvändigt för att rätta strukturen.
