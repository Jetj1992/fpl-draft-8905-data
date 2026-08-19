# FPL Draft 8905 data sync

Denne repo-pakke henter offentligt tilgængelige data for FPL Draft-liga **8905** og gemmer dem som JSON i GitHub.

Formålet er at give et stabilt mellemled:

**FPL Draft API -> GitHub Action -> JSON i repo -> ChatGPT recap**

## Hvad bliver hentet?

Kerne-endpoints:

- `/api/bootstrap-static`
- `/api/league/8905/details`
- `/api/league/8905/element-status`
- `/api/draft/league/8905/trades`
- `/api/draft/league/8905/choices`
- `/api/draft/entry/{Team_ID}/transactions`
- `/api/entry/{Team_ID}/public`
- `/api/event/{GW}/live`
- `/api/entry/{Team_ID}/event/{GW}`

Derudover prøves nogle hjælpe-endpoints. Hvis et valgfrit endpoint returnerer 401, 403 eller 404, fortsætter syncen uden at fejle hele jobbet.

`bootstrap-static` gemmes i en kompakt udgave for at undgå unødvendig repo-vækst.

## Privatliv

Pakken er lavet til et **offentligt GitHub-repo**, så ChatGPT kan læse data uden login. Derfor fjernes felter som managerens fornavn, efternavn og e-mail automatisk, før data skrives til disk. Fantasy-holdnavne (`entry_name`) bevares.

Hvis I ikke ønsker holdnavnene offentligt, skal repoet ikke publiceres, før scriptet er tilpasset yderligere.

## Opsætning

1. Opret et nyt GitHub-repo, fx `fpl-draft-8905-data`.
2. Gør repoet **Public**, hvis ChatGPT skal kunne læse JSON-filerne via web.
3. Upload **indholdet** af denne pakke til roden af repoet. Det er vigtigt, at `.github/workflows/fpl-draft-sync.yml` ender på netop den sti.
4. Gå til **Actions -> FPL Draft 8905 Sync -> Run workflow** og kør den manuelt første gang.
5. Kontroller efter kørslen, at `data/summary.json` findes.

Workflowet kører derefter hver 3. time ved minut 17. Det gør ikke noget, hvis data ikke har ændret sig: i så fald laves der ingen commit.

## Hvis `git push` fejler

Workflow-filen beder om `contents: write`. Hvis repository/organization-politikken stadig blokerer write-tokenet, så gå til:

**Settings -> Actions -> General -> Workflow permissions**

og tillad den nødvendige write-adgang for `GITHUB_TOKEN`.

## Vigtige filer

- `data/summary.json` - kompakt oversigt: liganavn, antal hold, Team IDs og seneste færdige gameweek.
- `data/current/league-details.json` - aktuelle H2H-kampe, standings og league entries.
- `data/current/element-status.json` - spillerstatus/ejerstatus, når endpointet er tilgængeligt.
- `data/current/transactions.json` - waivers/free agents pr. Team ID, når endpointet er tilgængeligt.
- `data/current/latest-entry-events.json` - holddata for seneste afsluttede GW.
- `data/current/latest-event-live.json` - spillerpoint for seneste afsluttede GW.
- `data/history/gw-XX/` - ét fast snapshot pr. afsluttet gameweek.

## Test lokalt

```bash
python tests/test_logic.py
python scripts/fetch_fpl_draft.py --league-id 8905
```

Det lokale miljø skal selvfølgelig kunne nå `draft.premierleague.com`.

## Næste trin med ChatGPT

Når første Action-kørsel er grøn, send repo-linket til ChatGPT. Derefter kan den eksisterende liga-automation ændres til at læse `data/summary.json`, `data/current/` og `data/history/gw-XX/` fra GitHub i stedet for at kalde FPL Draft direkte.
