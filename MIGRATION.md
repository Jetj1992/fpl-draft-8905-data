# Migration fra den nuværende kodebase

## Filer der skal erstattes

```text
.github/workflows/fpl-draft-sync.yml
scripts/fetch_fpl_draft.py
README.md
```

## Filer der skal tilføjes

```text
tests/test_logic.py
SCHEMA.md
AUTOMATION_PROMPT.md
MIGRATION.md
.gitignore
```

## Fil der bør slettes

```text
test_logic.py
```

Den gamle test ligger i repoets rod og beregner scriptstien forkert. Den nye ligger under `tests/`.

## Bevar data

Slet ikke den eksisterende `data/`-mappe. Den nye version:

- fortsætter med at skrive de kendte filer
- løfter `summary.json` til schema version 4
- opretter draft-recap-filer
- opretter Wirtz Watch efter næste afsluttede GW
- backfiller manglende afledte filer i et eksisterende GW-snapshot uden at overskrive de gamle rådata

## Første kørsel

1. Upload ændringerne til `main`.
2. Åbn GitHub Actions.
3. Kør **FPL Draft 8905 Sync + Pages** manuelt.
4. Kontroller, at testtrinnet er grønt.
5. Kontroller `data/summary.json`.
6. Hvis draften er komplet, kontroller `data/draft/initial/draft-recap.json`.

## Forventet fallback

Hvis `/draft/8905/choices` stadig ikke er tilgængelig, kan draft-recap stadig blive klar fra `element-status`, når alle 105 spillere har en ejer. I den situation indeholder recap'en komplette trupper, men ikke en opdigtet pick-by-pick-rækkefølge.
