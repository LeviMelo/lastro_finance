# RUNBOOK.md

Operating commands as the code has them (2026-11-07). Every command takes `--help`. Owner-facing output is pt-BR.

```bash
PY=C:/Users/Galaxy/miniconda3/envs/pegasus/python.exe   # shared `pegasus` conda env (ADR-0013)
PYTHONUTF8=1 $PY -m pip install -e . --no-deps            # once
export PYTHONUTF8=1                                       # `fin` = envs/pegasus/Scripts/fin.exe
```

## Checks before a commit

```bash
$PY -m pytest -q                           # ~5 s; network tests are opt-in: -m network
$PY -m ruff check src tests && $PY -m ruff format --check src tests
$PY -m pyright                             # strict
$PY scripts/check_docs.py
```

## Ingest

```bash
fin ingest daily                    # calendar + every ephemeral source (ADR-0007)
fin ingest anbima_calendar          # one source by source_id (see src/fin/reference/sources.toml)
fin ingest b3_cotahist --mode backfill --years 1986-2025      # yearly COTAHIST files
fin ingest b3_instruments --mode backfill                     # every B3 file served since 2025-06-10
fin ingest b3_pesquisapregao --mode backfill --families TS    # curves 2001-; PR (2018-, 10-15 GB) is OQ-20
fin ingest pyield_data bcb_sgs --mode backfill               # mirror (bonds 2020-, futures 2018-); SGS 1986-
fin ingest snd_debentures b3_fundosnet --mode backfill       # trades 1993-11-; FII notices 2016-11- (~10 h)
fin ingest yahoo_chart --mode snapshot [--tickers ITUB4,SLCE3]  # tier U; default: last year's traded tickers
fin ingest <context sources> --mode backfill  # the catalogue in src/fin/reference/context_series.toml
fin status                          # freshness per source, raw size, orphan objects, blockers, last runs
fin verify-raw                      # re-hash every raw object
fin rebuild --from-raw              # rebuild staging/core/derived/quarantine from raw + manifest
```

## The daily job on Windows

`scripts/schedule_daily.ps1` registers the task "LASTRO fin ingest daily": daily at 22:30 and at logon, start when
available, no overlap, log to `data/logs/scheduler.log`. Registering it changes the machine's configuration, so the
owner runs it (or approves it) once:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\schedule_daily.ps1
Get-ScheduledTaskInfo -TaskName "LASTRO fin ingest daily"      # last run, last result
Unregister-ScheduledTask -TaskName "LASTRO fin ingest daily" -Confirm:$false
```
A laptop that was off catches up by itself while missed days are still in a source's window (B3 BDI: 21 business
days; ANBIMA: ~6). Missing a registry snapshot loses that day; `fin status` shows the last reference date archived.
