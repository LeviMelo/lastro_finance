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
uv run fin status                          # freshness per source, raw size, orphan objects, blockers, last runs
uv run fin verify-raw                      # re-hash every raw object
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
