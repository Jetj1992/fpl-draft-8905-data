# JSON-schemaoversigt

Dette er en praktisk feltoverigt, ikke et formelt JSON Schema-dokument.

## `data/summary.json`

```json
{
  "schema_version": 4,
  "generated_at": "ISO-8601",
  "league_id": 8905,
  "league_name": "OK Data Liga",
  "latest_complete_gameweek": 1,
  "draft": {
    "status": "post",
    "draft_id": 9516,
    "completed_at": "ISO-8601 eller null",
    "recap_ready": true,
    "recap_fingerprint": "SHA-256 eller null",
    "pick_order_available": true,
    "resolved_picks": 105,
    "current_recap_path": "data/current/draft-recap.json",
    "snapshot_recap_path": "data/draft/initial/draft-recap.json"
  },
  "watched_players": {
    "configured": ["Wirtz"],
    "latest_gameweek": 1,
    "current_path": "data/current/watched-players.json"
  }
}
```

`draft.recap_fingerprint` er stabilt for den frosne initialdraft. En automation kan huske senest rapporterede fingerprint og dermed undgå dubletter.

## `draft-recap.json`

Vigtigste topfelter:

- `recap_ready`: sand, når draften virker afsluttet og alle hold har 15 spillere
- `draft_fingerprint`: stabil SHA-256 af spiller, ejer og valgnummer
- `draft_order`: første rundes rækkefølge, kun når den kan dokumenteres
- `picks`: alle berigede draftvalg
- `teams`: trupper grupperet pr. ligahold
- `watched_players`: blandt andet Wirtz' ejer og valgnummer
- `insights.first_player_by_position`: første valgte spiller pr. position
- `insights.largest_positive_draft_rank_deltas`: valgt senere end officiel Draft Rank
- `insights.largest_negative_draft_rank_deltas`: valgt tidligere end officiel Draft Rank
- `data_quality`: kilde, antal records, komplethed og advarsler

Et pick indeholder blandt andet:

```json
{
  "overall_pick": 8,
  "round": 2,
  "pick_in_round": 1,
  "element_id": 366,
  "web_name": "Wirtz",
  "club_short_name": "LIV",
  "position": "MID",
  "official_draft_rank": 12,
  "draft_rank_delta": 4,
  "league_entry_id": 42948,
  "entry_id": 42888,
  "entry_name": "AGFs Førstehold"
}
```

En positiv `draft_rank_delta` betyder, at spilleren blev valgt senere end den officielle Draft Rank. Det er et datapunkt, ikke en objektiv karakter.

## `watched-players.json`

```json
{
  "schema_version": 1,
  "gameweek": 1,
  "players": [
    {
      "element_id": 366,
      "web_name": "Wirtz",
      "owner": {
        "league_entry_id": 42948,
        "entry_id": 42888,
        "entry_name": "AGFs Førstehold"
      },
      "owner_source": "entry-events",
      "squad_status": "starter",
      "squad_position": 6,
      "multiplier": 1,
      "points_counted": 7,
      "bench_points": null,
      "stats": {
        "minutes": 84,
        "total_points": 7,
        "goals_scored": 0,
        "assists": 1,
        "bonus": 1
      },
      "fixtures": [],
      "h2h": {
        "opponent_entry_name": "Hyggemix",
        "owner_score": 57,
        "opponent_score": 52,
        "result": "win",
        "margin": 5,
        "points_exceeded_final_margin": true
      }
    }
  ]
}
```

Mulige `squad_status`-værdier:

- `starter`
- `substituted_in`
- `bench`
- `starter_not_counted`
- `not_in_squad_data`
- `unowned`
- `unknown`

`points_exceeded_final_margin` er kun en matematisk sammenligning. Det beviser ikke, at én spiller alene afgjorde kampen.

## `transactions-enriched.json`

Hver record indeholder:

- eksplicit API-type som `waiver`, `free_agent`, `trade` eller `draft`, når genkendelig
- resultat/status, når genkendelig
- liga- og Team ID
- fantasy-holdnavn
- beriget spiller ind og spiller ud
- den rå API-record under `raw`

Ukendt type forbliver `null`.
