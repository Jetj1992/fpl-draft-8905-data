# Changelog

## Version 4 – Wirtz Watch + draft recap

- rettet choices-endpoint til `/draft/{league_id}/choices`
- tilføjet liga-transaktioner fra `/draft/league/{league_id}/transactions`
- tilføjet berigede transaktioner uden typegæt
- tilføjet recap-klar initial draft og stabilt fingerprint
- tilføjet fallback fra choices til element-status
- tilføjet dynamisk watched-player-konfiguration med Wirtz som standard
- tilføjet historisk ejerbestemmelse via gameweek-opstillinger
- tilføjet Wirtz-stats, bænkstatus, fixture og H2H-kontekst
- tilføjet bootstrap-metadata i gameweek-snapshots
- tilføjet offline-tests i korrekt `tests/`-mappe
- opdateret GitHub Actions til at køre tests før datahentning
