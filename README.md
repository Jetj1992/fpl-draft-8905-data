# FPL Draft 8905 data sync

Denne repo-pakke henter offentligt tilgængelige data for FPL Draft-liga **8905 – OK Data Liga** og gemmer dem som sanitiseret JSON i GitHub.

Formålet er:

**FPL Draft API → GitHub Action → recap-klare JSON-filer → ChatGPT**

Versionen indeholder både:

- automatisk **draft recap** efter den første draft
- fast **🔎 Wirtz Watch** i hver afsluttet gameweek
- ligaens waivers, free-agent-transfers og trades, når API-dataene dokumenterer dem
- faste historiksnapshots, så senere spillerskift ikke omskriver gamle recaps

## Nye hovedfunktioner

### 1. Draft recap

Efter draften oprettes:

- `data/current/draft-recap.json`
- `data/draft/initial/draft-recap.json`

Det første dokument opdateres, indtil draften er komplet. Når alle hold har en komplet trup, fryses et initialt snapshot under `data/draft/initial/`.

Draft-recap-filen indeholder blandt andet:

- draftstatus og afslutningstidspunkt
- draftorden, når `/api/draft/{LEAGUE_ID}/choices` leverer den
- samtlige valg og trupper
- spiller, klub, position og officiel Draft Rank
- forskel mellem faktisk valgnummer og officiel Draft Rank
- første valgte målmand, forsvarer, midtbanespiller og angriber
- mulige value/reach-kandidater baseret på Draft Rank-forskellen
- hvilket hold der draftede Wirtz og ved hvilket valg
- et stabilt `draft_fingerprint`, som kan bruges til kun at sende én recap

Hvis choices-endpointet ikke kan læses, rekonstrueres trupperne fra `element-status`. I så fald opfindes draftordenen ikke.

### 2. Wirtz Watch

Efter hver afsluttet gameweek oprettes:

- `data/current/watched-players.json`
- `data/history/gw-XX/watched-players.json`

Wirtz identificeres dynamisk via spillernavnet – der hardcodes ikke et sæsonafhængigt element-ID.

Filen samler:

- ejer i den konkrete gameweek
- startopstilling, bænk eller indskiftet via autosub
- position i fantasy-opstillingen og multiplier
- minutter og samlede Draft-point
- mål, assists, bonus, kort, clean sheet, BPS og øvrige tilgængelige stats
- om pointene talte eller lå på bænken
- Premier League-modstander og resultat, når fixture-data findes
- ejerens H2H-modstander, score, resultat og margin

Gameweek-ejeren findes først ved at scanne de gemte `entry-events`. Det er vigtigt, fordi den aktuelle `element-status` kan være ændret af et waiver eller en free-agent-transfer efter rundens afslutning.

### 3. Waivers, free agents og trades

Pakken bruger ligaens offentlige transaktionsendpoint:

- `/api/draft/league/{LEAGUE_ID}/transactions`

Det gemmes som:

- `data/current/transactions.json` – rå API-data
- `data/current/transactions-enriched.json` – spiller- og holdnavne tilføjet
- tilsvarende filer i hvert gameweek-snapshot

En bevægelse kaldes kun `waiver`, `free_agent`, `trade` eller `draft`, hvis API-recorden har en genkendelig eksplicit type. Ukendte records mærkes ikke ved gæt.

Bekræftede direkte trades hentes desuden fra:

- `/api/draft/league/{LEAGUE_ID}/trades`

## Hentede endpoints

Kerne-endpoints:

- `/api/bootstrap-static`
- `/api/league/{LEAGUE_ID}/details`
- `/api/league/{LEAGUE_ID}/element-status`
- `/api/draft/{LEAGUE_ID}/choices`
- `/api/draft/league/{LEAGUE_ID}/transactions`
- `/api/draft/league/{LEAGUE_ID}/trades`
- `/api/entry/{TEAM_ID}/public`
- `/api/event/{GW}/live`
- `/api/entry/{TEAM_ID}/event/{GW}`

Fra den almindelige FPL API:

- `/api/bootstrap-static/`
- `/api/fixtures/?event={GW}`

Valgfrie endpoints må gerne returnere 401, 403 eller 404. Syncen fortsætter, og manglen beskrives i `data/summary.json`.

## Vigtige filer

- `data/summary.json` – trigger- og statusfil, schema version 4
- `data/current/draft-recap.json` – recap-klart billede af den første draft
- `data/draft/initial/draft-recap.json` – frosset initial draft
- `data/current/watched-players.json` – seneste Wirtz Watch
- `data/history/gw-XX/watched-players.json` – Wirtz Watch for en bestemt runde
- `data/current/transactions-enriched.json` – læsbare transaktioner
- `data/current/league-details.json` – liga, kampe og stilling
- `data/current/latest-entry-events.json` – seneste afsluttede GW-opstillinger
- `data/current/latest-event-live.json` – seneste afsluttede GW-spillerpoint
- `data/history/gw-XX/` – uforanderligt recap-input pr. afsluttet runde

Se også `SCHEMA.md`.

## Installation i det eksisterende repo

Upload eller erstat disse filer:

```text
.github/workflows/fpl-draft-sync.yml
scripts/fetch_fpl_draft.py
tests/test_logic.py
README.md
SCHEMA.md
AUTOMATION_PROMPT.md
```

Slet den gamle `test_logic.py` fra repoets rod, hvis den stadig ligger der. Den korrekte testfil ligger nu i `tests/`.

Behold den eksisterende `data/`-mappe. Den nye kode kan fortsætte oven på den og backfiller de nye afledte filer, når det er sikkert.

## Kør lokalt

```bash
python -m py_compile scripts/fetch_fpl_draft.py
python tests/test_logic.py
python scripts/fetch_fpl_draft.py --league-id 8905 --watch-player Wirtz
```

Der bruges kun Python-standardbiblioteket.

Flere overvågede spillere kan tilføjes:

```bash
python scripts/fetch_fpl_draft.py \
  --league-id 8905 \
  --watch-player Wirtz \
  --watch-player Isak
```

Hvis `--watch-player` udelades, overvåges Wirtz som standard.

## Kør i GitHub

Gå til:

**Actions → FPL Draft 8905 Sync + Pages → Run workflow**

Workflowet:

1. kompilerer scriptet
2. kører alle offline-tests
3. henter data
4. committer kun ændringer under `data/`
5. publicerer JSON-filerne via GitHub Pages

Det planlagte job kører hver tredje time ved minut 17.

## Kontrol efter første kørsel

Efter draften bør følgende være opfyldt i `data/summary.json`:

```json
{
  "draft": {
    "recap_ready": true,
    "recap_fingerprint": "...",
    "snapshot_recap_path": "data/draft/initial/draft-recap.json"
  }
}
```

Når en gameweek er færdig, bør følgende være udfyldt:

```json
{
  "latest_complete_gameweek": 1,
  "watched_players": {
    "configured": ["Wirtz"],
    "latest_gameweek": 1,
    "current_path": "data/current/watched-players.json"
  }
}
```

## Privatliv

Repoet er beregnet til at være offentligt. Managerens fornavn, efternavn og e-mail fjernes rekursivt før skrivning. Fantasy-holdnavne og korte initialer bevares, fordi de bruges i liga-recaps.

## ChatGPT-automation

`AUTOMATION_PROMPT.md` indeholder en samlet prompt til:

- én draft recap pr. nyt `draft_fingerprint`
- én gameweek-recap pr. ny `latest_complete_gameweek`
- fast `🔎 Wirtz Watch`
- waivers/free agents/trades uden gæt
