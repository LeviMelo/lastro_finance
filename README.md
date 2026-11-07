# LASTRO

A local, owner-controlled data and analysis system for a Brazilian investor's portfolio: it acquires and keeps
trustworthy data on every reachable asset class (B3, CVM, BCB, IBGE, Tesouro, ANBIMA…), models holdings through
time, values and analyses them, and exports dossiers for an external LLM. Intent: [`PLAN.md`](PLAN.md). State:
[`STATUS.md`](STATUS.md).

```bash
uv sync
uv run fin status            # o que existe, frescor por fonte, bloqueios
uv run fin ingest daily      # arquiva as fontes efêmeras do dia
```

Everything fetched is kept byte for byte under `data/raw/` (git-ignored), and every derived table can be rebuilt
from it (`fin rebuild --from-raw`). Commands: [`RUNBOOK.md`](RUNBOOK.md). How to work on the code: `CLAUDE.md`.
