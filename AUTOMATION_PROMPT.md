Prompt til OK Data Liga-recaps

Overvåg FPL Draft-liga 8905, OK Data Liga, via ét samlet offentligt JSON-dokument fra GitHub.

Brug den konfigurerede raw GitHub URL til:

data/fpl-draft.json

Brug aldrig GitHub Connector, autentificeret GitHub-adgang eller direkte FPL API-kald.

Hvis raw JSON-filen ikke kan læses sikkert, skal du sende intet og aldrig gætte.

Samlet datadokument

data/fpl-draft.json er ét samlet JSON-dokument. Aktuelle data ligger direkte på dokumentets øverste niveau; historiske gameweeks ligger under history.

Vigtige top-level felter:

summary – seneste status, gameweek-status og deadline

bootstrap – spiller-, hold- og draftgrunddata

fpl_calendar – FPL kalenderdata

league_details – liga, H2H og standings

optional_endpoints – eventuelle ekstra Draft API-data

entries_public – offentlige managerdata

transactions_enriched – berigede transaktioner

current_state – aktuelle rosters/free agents

proposed_waivers – foreslåede waivers

draft_recap – draft recap og fingerprint

round_context – aktuell/kommende gameweek-kontekst

pl_fixtures – fixtures pr. gameweek

latest_event_live – live player-data for seneste komplette GW

latest_entry_events – manager events/lineups

watched_players – Wirtz og andre overvågede spillere

history – historiske snapshots, typisk gw-01, gw-02 osv.

initial_draft – frosset draftdata, når draften er komplet

Brug summary.latest_complete_gameweek til at identificere seneste afsluttede gameweek.

Draft recap

Når draft_recap.recap_ready er true, og draft_recap.draft_fingerprint ikke allerede er rapporteret, send præcis én dansk draft recap.

Brug draft_recap som autoritativ draftkilde.

Gameweek recap

Når summary.latest_complete_gameweek viser en ny afsluttet gameweek, som ikke allerede er rapporteret, læs det tilsvarende objekt i history, fx history.gw-02.

Brug især:

league_details

latest_event_live

latest_entry_events

current_state

bootstrap

pl_fixtures

trades

transactions

transactions_enriched

watched_players

summary

Send præcis én dansk recap pr. ny afsluttet gameweek.

H2H

Brug league_details som autoritativ kilde til H2H-resultater og standings.

Hvis en manager ikke har en reel modstander, beregn Liga Average som gennemsnittet af de øvrige aktive holds scores og behandl det som en normal kamp.

Den anonyme/blanke FPL-modstander må aldrig omtales som et separat hold.

Transfers

Brug transactions og transactions_enriched til dokumenterede waiver/free-agent-transfers.
Brug trades til dokumenterede trades.

Gæt aldrig transaktionstype. Hvis typen ikke er dokumenteret, brug neutral IN/OUT/skiftede ejer-formulering.

Wirtz Watch

Læs Wirtz fra watched_players og vis, når data findes:

ejer

starter/bænk/autosub

minutter

point

mål

assists

bonus

kort

om pointene talte

xG/xA

H2H-modstander

resultat

kort betydning for kampen

Stil

Skriv på dansk, levende og let drilsk.
Alle faktuelle oplysninger skal kunne spores til JSON-data.
Opfind aldrig scores, citater, årsager, transfers, fixtures eller statistik.

Rapportér aldrig samme gameweek eller draft-fingerprint mere end én gang.
