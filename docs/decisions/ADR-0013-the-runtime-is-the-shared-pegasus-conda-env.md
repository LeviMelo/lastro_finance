## ADR-0013: The runtime is the shared `pegasus` conda environment (Python 3.11); LASTRO is installed in it editable, without dependencies

**Date:** 2026-11-07. **Status:** active. Owner decision. Departs from PLAN §2 ("Python ≥ 3.12, managed with `uv`").

**Context.** The owner asked on 2026-11-07 that LASTRO use the `pegasus` conda environment of the pegasus projects,
whose numerical stack is the one analysis will need. The env runs Python 3.11.15. On 2026-11-07 it already held
every runtime dependency (duckdb 1.5.5, polars 1.41.2, pyarrow 23, httpx, typer, xlrd, zstandard), plus statsmodels,
scipy, scikit-learn, pandas, openpyxl, pypdf, pymupdf and geopandas. The pegasus projects install themselves with
`pip install -e . --no-deps`, and never with conda: their RUNBOOK records the solver once replacing a CUDA PyTorch
and removing geopandas.

**Decision.**
- `requires-python = ">=3.11"`; ruff targets py311; pyright checks against `envs/pegasus` (`venvPath`/`venv` in
  `pyproject.toml`).
- One 3.12-only construct was rewritten (a nested-quote f-string in `ingest/context.py`).
- LASTRO is installed with `pip install -e . --no-deps`. `fin` is `envs/pegasus/Scripts/fin.exe`, which the scheduled
  task calls.
- Missing tools are installed with `pip` only (hypothesis, pyright and pyarrow-stubs on 2026-11-07) and declared in
  `pyproject.toml`. `conda install` into `pegasus` is not used.

**Evidence.** Under the env on 2026-11-07: 40 tests pass, ruff is clean, and pyright strict reports 0 errors.

**Alternatives.**
- *Keep the uv venv on 3.12*: rejected by the owner. It meant two stacks to keep current.
- *Upgrade `pegasus` to 3.12*: rejected, because it risks the pegasus projects.

**What would reverse it.** A dependency LASTRO needs that conflicts with the pegasus projects, or the env moving
to a Python the code cannot run on.
