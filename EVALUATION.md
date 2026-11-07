# EVALUATION.md

The index of this project's measurements. Each one is a file under `docs/evaluation/`; read the index, then the
entries you need. What counts as ground truth: [`docs/evaluation/methods.md`](docs/evaluation/methods.md).

**Nothing is declared working on a plausible-looking output.** Open the table, and check it against an independent
figure: the source's own totals, a second source, a documented event.

A new measurement is a file `docs/evaluation/YYYY-MM-DD-<slug>.md` plus a row here, in the same commit as the work it
justifies. It names the command or script, the regime (commit, data home, date), what was counted and why that is what
matters, and the result against the independent figure.

| date | entry | what was measured |
|---|---|---|
| 2026-11-07 | [Stage A and the first daily run](docs/evaluation/2026-11-07-stage-a-first-daily-run.md) | calendar against BCB's CDI dates and factors; first archive of the ephemeral windows; rebuild from raw byte-identical |
