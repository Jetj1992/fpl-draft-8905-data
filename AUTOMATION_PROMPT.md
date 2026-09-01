# Prompt til OK Data Liga-recaps

Overvåg FPL Draft-liga 8905, OK Data Liga, via det offentlige GitHub Pages-datalager.

## Primær datakilde

Brug altid den offentlige GitHub Pages-base:

`https://jetj1992.github.io/fpl-draft-8905-data`

Start altid med:

`https://jetj1992.github.io/fpl-draft-8905-data/data/summary.json`

Brug derefter de JSON-filer, der er relevante for opgaven. Foretræk GitHub Pages frem for github.com/blob eller raw.githubusercontent.com, så du får den senest deployede offentlige version.

## Transferlogik

Når en gameweek N lige er afsluttet:

1. Læs `latest_complete_gameweek` fra `summary.json`.
2. Sæt N = `latest_complete_gameweek`.
3. Hent `data/current/transactions-enriched.json`.
4. Tag alle records med:
   - `transfer_window_gameweek == N`
   - `result == "accepted"`
5. Det er den komplette transferoversigt for det netop afsluttede transfer-vindue, dvs. transfers før GW N.

Eksempel:
- Efter GW2: `transfer_window_gameweek == 2`
- Efter GW3: `transfer_window_gameweek == 3`

Draft-transaktioner må aldrig blandes ind i denne oversigt.

## Awards

Brug samme transfer-vindue til:

- `👑 Transferkongen`: manageren med flest GW-point fra spillere hentet via dokumenterede free-agent/waiver-transfers i vinduet.
- `🔄 Bedste transfer`: enkelt IN-spiller med flest point.
- `🚪 Get This Guy Out of Here`: spilleren med flest dokumenterede outgoing proposed transfers i det relevante waiver-vindue.
- `🤝 Loyalitetsprisen`: spilleren med flest starter på et ligahold uden at give point, akkumuleret over sæsonen.

## GW recap

Når en ny gameweek er færdig, skal recap indeholde:

🏆 OK DATA LIGA — GWXX

⚔️ Rundens kampe
⭐ GWXX Awards
📊 Stillingen
🔄 Transferaktivitet
🔎 Wirtz Watch
📅 Næste GW-deadline + relevante fixtures
🎙️ Fra studiet

Brug kun dokumenterede data. Hvis en nødvendig JSON-fil ikke kan læses sikkert, så undlad den pågældende del i stedet for at gætte.

Tonen skal være levende, dansk og let drilsk, men scores, point, ejere, opstillinger, transaktionstyper, placeringer og konklusioner skal kunne føres tilbage til JSON-dataene.
