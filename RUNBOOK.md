# RUNBOOK.md

Operating commands as the code has them (2026-11-07). Every command takes `--help`. Owner-facing output is pt-BR.

```bash
uv sync                                    # once; uv lives in %APPDATA%\Python\Python312\Scripts
export PYTHONUTF8=1
```

## Checks before a commit

```bash
uv run pytest -q                           # ~5 s; network tests are opt-in: -m network
uv run ruff check src tests && uv run ruff format --check src tests
uv run pyright                             # strict
uv run python scripts/check_docs.py
```

## Ingest

```bash
uv run fin ingest daily                    # calendar + every ephemeral source (ADR-0007)
uv run fin ingest anbima_calendar          # one source by source_id (see src/fin/reference/sources.toml)
uv run fin ingest b3_cotahist --mode backfill --years 1986-2025      # yearly COTAHIST files
uv run fin ingest b3_instruments --mode backfill                     # every B3 file served since 2025-06-10
uv run fin ingest b3_pesquisapregao --mode backfill --families TS    # curves 2001-; PR (2018-, 10-15 GB) is OQ-20
uv run fin ingest pyield_data bcb_sgs --mode backfill               # mirror (bonds 2020-, futures 2018-); SGS 1986-
uv run fin ingest snd_debentures b3_fundosnet --mode backfill       # trades 1993-11-; FII notices 2016-11- (~10 h)
uv run fin ingest cvm_rad_versions                       # superseded DFP/ITR versions from RAD (XML + legacy layout, ~10 s each, resumable; ADR-0027); run alone
uv run fin ingest yahoo_chart --mode snapshot [--tickers ITUB4,SLCE3]  # tier U; default: last year's traded tickers
uv run fin ingest <context sources> --mode backfill  # the catalogue in src/fin/reference/context_series.toml
uv run fin status                          # freshness per source, raw size, orphan objects, blockers, last runs
uv run fin verify-raw                      # re-hash every raw object
uv run fin reparse bcb_sgs ipeadata ibge_sidra  # re-parse archived raw of some sources (after a parser change)
uv run fin compact-raw [sources]          # store repeated versions as deltas (verified; read bytes unchanged)
uv run fin compact-staging [sources]      # merge small staging files (the daily job does this itself)
uv run fin catalog                        # rebuild data/catalog.duckdb (views; the daily job does it)
uv run fin export panel                   # monthly model panels (equity, macro) + dictionary in data/exports/panel/
# a query killed mid-way leaves DuckDB spill files in data/catalog.duckdb.tmp/ (38 GB once): delete when idle
uv run fin quality [checks]               # run the data-quality checks → data/quality/dq_finding (the daily job does it)
uv run python scripts/check_golden_events.py  # golden corporate events vs core (exit 1 on a miss)
uv run fin export dossier --portfolio examples/portfolio_reference.toml --as-of 2026-10-16  # the dossier (ADR-0026)
uv run fin ledger [--file inbox/transactions.csv] [--as-of D]  # positions and average cost; writes core/ledger (ADR-0033)
uv run fin tax [--file inbox/transactions.csv]   # monthly IR, DARF 6015 and due date, losses carried, income IR
uv run fin export dossier --as-of D              # holdings from the ledger when inbox/transactions.csv exists
uv run python scripts/check_provenance.py  # invariant 2: every staging row carries its provenance (exit 1 on a gap)
uv run python scripts/check_exit_criteria.py  # PLAN §10 exit criteria C, E, G, H (exit 1 on a failure)
uv run python scripts/check_golden_portfolio.py  # PLAN §13.1 portfolio vs the plan's estimate (exit 1 outside tolerance)
uv run fin rebuild --from-raw              # rebuild staging/core/derived/quarantine from raw + manifest
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
