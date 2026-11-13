# Plan: multipleAssistant

## Mål
Ett webbchattrum i Bottle där två AI-assistenter med egna namn och billiga modeller pratar allmänt och ger tips och råd. Användaren skriver i en chatruta och väljer om meddelandet ska gå till båda eller till en specifik assistent med `@namn`.

Varför: två assistenter med olika modeller och personligheter gör det lätt att jämföra svar och att se hur olika modeller resonerar. Samtidigt håller vi kostnaden nere genom billiga modeller.

## Kontext
- Ny mapp: `Modul05/multipleAssistant/`, parallellt med `Modul05/chat/`. Ingen kod delas, men mönstret tas från chat:
  - `llm.py`: tunt lager ovanpå OpenAI-SDK:n mot `https://api.1min.ai/openai/v1`, med `max_retries=0` och en `models()`-metod som listar modeller utan att kosta något.
  - `store.py`: append-only logg i `turns.jsonl` med fsync, där kontexten härleds ur loggen.
  - `config.py`: läser `.env` och har en varning när historiken blir stor.
- Webbgränssnittet byggs i Bottle, som `Modul05/app.py` redan använder.
- Nyckel och modeller läses från `.env` (`ONEMIN_API_KEY`, samt modellnamn per assistent). `.env` committas aldrig, och vi visar aldrig dess innehåll.
- Chat-mappens README säger `history.json` men koden använder `turns.jsonl`. Det ska inte kopieras. Den här mappen följer koden.

## Krav och avgränsningar
- Måste:
  - Två assistenter, var och en med eget namn och egen modell, som visas i gränssnittet.
  - Assistenterna pratar om allmänna tips och råd. Ingen specialistdomän.
  - Meddelande utan `@` går till båda. Båda svarar i ordning: assistent 1 först, sedan assistent 2, som ser assistent 1:s svar.
  - Meddelande med `@namn` går bara till den assistenten. Svaret ska inte innehålla något `@`.
  - Samma samtal för båda: båda ser hela det gemensamma samtalet, inklusive användarens meddelanden och den andra assistentens svar.
  - Historiken sparas i en append-only logg så att samtalet finns kvar efter omstart.
  - Modellerna väljs för låg kostnad. Vi undviker dyra modeller som standard.
  - Varje anrop får en tydlig felrad i gränssnittet om det misslyckas. Ingen traceback syns för användaren.
  - Skickar bara de senaste meddelandena (t.ex. 20) till modellen, så att kostnaden inte växer obegränsat.
- Får inte hända:
  - Ingen ny generering vid automatiska omförsök (`max_retries=0`).
  - Inga nycklar eller `.env`-innehåll i loggar, gränssnitt eller commits.
  - Inga personuppgifter eller studerandeuppgifter i meddelandena. 1min.AI är en tredjepart.
  - Ingen kod kopierad rakt av från `chat/`. Gränsen för historik och modellnamn ska vara konfigurerbar.
- Utanför scope:
  - Inloggning, flera användare, bilder och verktyg.
  - Streaming av svar ingår inte i första versionen. Om du vill ha det som i ChatGPT, säg till så lägger vi in det.
  - Automatisk komprimering (`/compact`). Vi använder ett fönster i stället.
  - Att köra de två assistenterna mot olika leverantörer.

## Utseende (ChatGPT-liknande layout)
- Smal, centrerad chattkolumn. Användarens meddelanden till höger, assistenternas till vänster.
- Varje assistent har en egen avatar (initial i en cirkel) och sitt namn ovanför svaret. Modellnamnet visas i liten grå text.
- Inmatningsrutan fast längst ner, med en skicka-knapp. Enter skickar, Shift+Enter ger ny rad.
- Mörkt tema som standard, med ljust tema som alternativ. Färger som tokens i `:root` så att båda temana går att byta.
- En "tänker…"-indikator medan en assistent svarar.
- Ingen OpenAI-logga eller varumärkesfärger. Vi härmar layouten, inte varumärket.

## Antaganden (ändra om du vill)
- Assistenterna svarar i sekvens, inte parallellt, så att den andra kan reagera på den första.
- Modellnamnen står i `.env`. Jag listar tillgängliga modeller med `models()` innan vi väljer, eftersom priser inte finns där. Du väljer vilka två som ska användas.
- Användarens meddelande sparas i loggen med assistenternas namn som mottagare, så att historiken går att läsa.

## Klart när
- [ ] `@Namn hej` får bara svar från den namngivna assistenten, och svaret innehåller inget `@`.
- [ ] Ett meddelande utan `@` får två svar, i ordning, och den andra assistenten nämner eller bygger på det första svaret i minst ett av sina testsamtal.
- [ ] Båda assistenterna visar sitt namn och sin modell i gränssnittet.
- [ ] Efter omstart av servern visas tidigare meddelanden och assistenterna fortsätter i samma samtal.
- [ ] Vid ett felaktigt API-nyckel visas ett tydligt felmeddelande i gränssnittet, och ingen traceback syns.
- [ ] Endast de senaste 20 meddelandena skickas till modellen. Testat med en lista på 30 meddelanden.
- [ ] Tester för routningen (`@namn`, utan `@`, okänt namn) och för historikfönstret går igenom.
