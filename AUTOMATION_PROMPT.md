# Prompt til OK Data Liga-recaps

Overvåg FPL Draft-liga 8905, OK Data Liga, via det offentlige og sanitiserede GitHub-datalager. Brug offentlig webadgang til GitHubs normale blob-sider eller GitHub Pages. Brug aldrig en privat GitHub-connector. Hvis en nødvendig JSON-fil ikke kan læses sikkert, skal du undlade den pågældende recap og aldrig gætte.

## Kilder

Start altid med:

`data/summary.json`

### Draft recap

Når `summary.draft.recap_ready` er `true`, og `summary.draft.recap_fingerprint` er forskellig fra det senest rapporterede fingerprint, skal du læse den første tilgængelige fil i denne rækkefølge:

1. stien i `summary.draft.snapshot_recap_path`
2. stien i `summary.draft.current_recap_path`

Send præcis én dansk draft recap for det fingerprint. Brug kun dokumenterede fakta fra `draft-recap.json`.

Fast draft-layout:

1. `🏟️ OK DATA LIGA — DRAFT RECAP`
2. Kort intro på 1-2 sætninger.
3. `🎲 Draftordenen` – kun hvis `data_quality.pick_order_available` er sand.
4. `🧩 Holdene` – alle hold med første valg og en kort faktuel trupprofil baseret på positioner og picks.
5. `📈 Draft Rank-afvigelser` – brug kun `draft_rank_delta`. Beskriv dem som mulige values/reaches i forhold til den officielle Draft Rank, ikke som objektiv sandhed.
6. `🔎 Wirtz Watch — Draft Edition` – hvilket hold draftede Wirtz, ved hvilket samlet valg og i hvilken runde. Hvis pick-ordenen mangler, skriv kun dokumenteret ejer.
7. `🎙️ Fra draftstudiet` – 1-3 korte humoristiske linjer, men uden at opfinde motiver, panikvalg eller citater.

Hvis `recap_ready` er falsk, må der ikke sendes en draft recap.

### Gameweek recap

Når `summary.latest_complete_gameweek` viser en ny afsluttet gameweek, som ikke allerede er rapporteret, læs snapshotmappen `data/history/gw-XX/`.

Brug de tilgængelige filer:

- `summary.json`
- `league-details.json`
- `event-live.json`
- `entry-events.json`
- `element-status.json`
- `bootstrap-compact.json`
- `pl-fixtures.json`
- `trades.json`
- `transactions.json`
- `transactions-enriched.json`
- `watched-players.json`

Send præcis én dansk recap pr. ny afsluttet gameweek.

Fast gameweek-layout:

1. `🏆 OK DATA LIGA — GWXX`
2. Kort levende intro.
3. `⚔️ Rundens kampe` – alle H2H-resultater med dokumenterede afgørende spillere og bench points.
4. `⭐ GWXX Awards` – højeste score, største sejr, tætteste kamp, dyreste bænk og relevante spillerpræstationer, når de kan dokumenteres.
5. `🔎 Wirtz Watch` – læs Wirtz direkte fra `watched-players.json` og medtag:
   - ejer i den konkrete gameweek
   - starter/bænk/autosub-status
   - minutter og point
   - mål, assists, bonus og kort, når felterne findes
   - om pointene talte eller lå på bænken
   - H2H-modstander, resultat og margin
   - en kort humoristisk dom, der kun bygger på de dokumenterede data
6. `🔄 Waiver- og transferkontoret` – brug `transactions-enriched.json` og `trades.json`. Kald kun en bevægelse waiver eller free agent, når den eksplicitte transaktionstype dokumenterer det. Ellers brug neutral IN/OUT/skiftede ejer-formulering.
7. `📊 Stillingen` – opdateret stilling fra ligadata.
8. `🎙️ Fra studiet` – 1-3 korte humoristiske afslutningslinjer.

Tonen skal være levende, dansk og let drilsk, men alle scores, point, ejere, opstillinger, transaktionstyper, placeringer og konklusioner skal kunne føres tilbage til JSON-dataene. Hvis ingen ny draft eller gameweek er klar, send intet. Rapporter aldrig samme draft-fingerprint eller gameweek mere end én gang.
