# OK Data Liga - Copilot recap data source

Use the single raw GitHub JSON file `fpl-draft.json` in the repository root. Schema version 6 is authoritative.

## Data hierarchy
- Current data is at the JSON root (`summary`, `league_details`, `transactions_enriched`, `watched_players`, `pl_fixtures`, etc.).
- Historical data is under `history.gw-XX`.
- For a gameweek recap, use `history.gw-XX.recap` as the primary and authoritative recap-ready data layer.
- `initial_draft` contains the frozen draft snapshot.

## Recap workflow
1. Read `summary.latest_complete_gameweek`.
2. Read `history.gw-XX.recap`.
3. Check `history.gw-XX.recap.metadata.recap_ready`. If false, do not invent missing facts.
4. Use `h2h_matches` and `league_average_match` for the round's matches.
5. Use `standings` for the table after the round.
6. Use `transfer_awards`, `transactions`, and `transfer_performance` for transfer awards.
7. Use `almost_there_candidates` for Almost There.
8. Use `wirtz` for Wirtz Watch.
9. Use `fixtures` for documented fixtures.

## League Average
If `league_average_match` exists, show the opponent as `Liga Average`. Never refer to a blank or anonymous FPL opponent as a separate team.

## Awards
Use only the precomputed recap data. Do not recalculate from unrelated raw structures unless needed for verification.
- Transferkongen = `transfer_awards.transfer_king`
- Bedste transfer = `transfer_awards.best_transfer`
- How You Like Me Now = `transfer_awards.how_you_like_me_now`; only show it when the stored difference is >= 5
- Almost There = first/most relevant record from `almost_there_candidates`; candidates already require xG >= 0.75
- Galaxy Brain = include only when there is a clearly documented case; otherwise omit
- Fraud Watch = include only when a clearly documented high-draft/target player had an unusually poor GW; otherwise omit
- Wirtz Watch = always show `wirtz`

## Output format
### 🏆 OK DATA LIGA — GWXX
Short intro.

### ⚔️ Rundens kampe
All real H2H matches plus Liga Average when applicable. Show scores and short factual comments.

### 🏆 Highlights
Include only applicable sections: Transferkongen, Bedste transfer, How You Like Me Now, Almost There, Galaxy Brain, Fraud Watch, Wirtz Watch.

### 📊 Stillingen efter runden
Use `standings`.

### 🔄 Transferkontoret
Use documented `transactions` and `trades`. Never guess transaction type.

### 📅 Næste runde
Use `summary.next_deadline` and documented upcoming fixtures.

### 🎙️ Fra studiet
1-3 short, factual, lightly teasing lines.

## Hard rules
Never invent scores, points, owners, transfers, fixtures, deadlines, quotes, reasons, or statistics.
If a required recap field is missing, omit the field or stop the recap according to `recap_ready`.
Never report the same gameweek or draft fingerprint twice.


## LIVE GAMEWEEK MODE

Filen indeholder også `live_gameweek`, som skal bruges når den aktuelle gameweek endnu ikke er afsluttet.

Hvis `live_gameweek` findes og har status `in_progress`, kan du lave en live-rundeupdate. Brug kun dokumenterede live-tal. Der findes ingen sandsynlighedsmodel i datasættet. Opfind derfor ikke win probability eller expected points.

Brug `live_gameweek.h2h_matches` til de aktuelle H2H-stillinger. Brug `live_gameweek.key_matchups` til at identificere de tætteste eller mest relevante opgør. Brug `live_gameweek.managers[].remaining_players` og `remaining_starting_players` til at vise hvilke spillere der endnu ikke har spillet.

En live-update kan beskrive:
- aktuelle scores
- aktuel føring og margin
- resterende spillere
- hvilke H2H-opgør der er tætte
- hvilke resterende spillere der er de vigtigste at holde øje med
- kampstatus for de resterende spillere

Du må ikke konkludere, at en manager sandsynligvis vinder, medmindre der findes en dokumenteret model i data. Beskriv i stedet den aktuelle situation.

Når `live_gameweek.status` er `finished`, skal den normale færdige GW-recap-logik bruges i stedet.
