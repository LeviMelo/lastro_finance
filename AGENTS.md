# CLAUDE.md — LASTRO (lastro_finance)

**`AGENTS.md` is a byte-for-byte copy of this file**; change both in the same commit (`scripts/check_docs.py`).

How to work on this repository. Intent lives in `PLAN.md` (the owner's long-form plan; never edited to match
reality — discrepancies go to an ADR or a source note). State, decisions and evidence live in the documents of §7.
Documentation follows the PHAROS model (ADR-0001; skill `project-documentation`).

---

# 1. What LASTRO is for

A local, owner-controlled platform for a Brazilian tax resident's investments: acquire and keep trustworthy data on
every reachable asset class, model holdings through time, value them, analyse risk, and export dossiers for an
external LLM (PLAN §1). **The data layer is the project** (PLAN §4): the owner's previous attempt failed on data
availability, quality, instrument identity through time and price adjustment.

# 2. Run it

```bash
PY=C:/Users/Galaxy/miniconda3/envs/pegasus/python.exe   # the shared `pegasus` conda env (ADR-0013)
PYTHONUTF8=1 $PY -m pip install -e . --no-deps            # once; the env already holds the dependencies
$PY -m pytest -q                                          # unit tests (network tests: -m network)
$PY -m ruff check src tests && $PY -m pyright
$PY scripts/check_docs.py
fin status                                                # fin = envs/pegasus/Scripts/fin.exe
fin ingest daily                                          # the daily snapshot job (ephemeral sources)
```
- Install with `pip` only, never `conda install` into `pegasus` (the solver once swapped packages of the pegasus
  projects) and never `uv`. `PYTHONUTF8=1` for owner-facing pt-BR output. Data home: `data/` (git-ignored) or `FIN_DATA_HOME`.

# 3. Invariants (PLAN §4.1, non-negotiable)

```text
1  Raw is immutable: bytes stored content-addressed (SHA-256) with a manifest row; never edited or deleted.
   Normalisation bugs are fixed by re-deriving from raw.
2  Every L2/L3 row carries provenance: raw_sha256, raw_locator, ingest_run_id. A number without it is a defect.
3  Bitemporal: valid time and knowledge time (kt_published_at, kt_first_seen_at). Restatements add versions.
4  Identity is ours: surrogate keys; tickers, ISINs, CNPJs, codes are time-ranged attributes, never keys.
5  Point-in-time universes include delisted and dead instruments. Survivorship bias is a defect.
6  Derive, don't store adjusted data: raw prices and events are stored; adjustments are rebuilt.
7  Reconcile, don't trust: disagreements become dq_finding records; never pick a winner silently.
8  Explicit units and conventions on every numeric column (currency, scale, quote basis, day count).
9  One calendar: ANBIMA's (fin.reference.calendar). Never a library's holiday set.
10 Idempotent steps; L2-L4 rebuildable from L1 + code (`fin rebuild --from-raw`, tested byte-identical).
11 Fail loudly, quarantine, never drop. Every ingest reports in/out/quarantined.
12 Completeness is measured: what should exist vs what does.
13 Archive the ephemeral from day one: the daily snapshot job is first-class. Lost days are unrecoverable.
```

# 4. Working agreement (PLAN §11, and the owner's standing rules)

- **Verify before you build.** Fetch real files, read official layouts, commit fixtures (≤ 1 MB, byte-exact,
  README with URL, date, sha256). Never invent layouts, endpoints or codes from memory. No parser for a layout
  not confirmed against a real file.
- **"Unreachable" is a finding, not a guess** (owner): before declaring a source down, try DNS/TCP/TLS
  (`curl -v`), a browser User-Agent, other endpoints of the host, the in-app browser; record what failed.
- **A source unavailable, changed or paywalled** is recorded in its note and an ADR, with alternatives; an
  unofficial source is never silently promoted to primary. Tier-U facts enter only as candidates or cross-checks.
- **Explicit over clever** in the data layer: typed contracts (`fin/schema.py`), `Decimal`/rationals for money,
  ratios, rates; small pure functions; named checks.
- **Small, test-backed changes.** Run the relevant tests before calling a step done; plan mode for changes to
  §3 invariants or the canonical schema.
- **Owner-facing text is pt-BR** with Brazilian market terms; code, identifiers and internal docs are English.
- **Ask the owner only for owner decisions** (PLAN §12, OPEN_QUESTIONS) and personal documents; decide
  engineering defaults, record them as ADRs.
- **Respect source terms**: ≤ 1 request/s per host, generic UA with no personal email, no CAPTCHA bypass,
  no scraping behind logins.
- **Dependencies** (owner): install the library the job needs into the `pegasus` env (pip) and declare it in
  `pyproject.toml`; never hand-roll a weaker substitute. Ask only for heavy or license-restricted ones.
- **Agents** (owner, 2026-11-07): at most 3 subagents at a time, Sonnet for low/medium tasks (recon, surveys);
  they write their results to disk as they go.
- **Never act outward as the owner**: pushing, publishing, contacting anyone, registering scheduled tasks or
  other persistent system changes need explicit authorisation, each time.

# 5. Code, tests and documentation

- **Weight** (owner): commit in batches; ADRs only for settled decisions; a measurement is a few lines, added to an
  existing entry where one fits; documentation must not outweigh the code it describes.
- **Documentation ships with the change, in the same commit.** A decision is `docs/decisions/ADR-NNNN-<slug>.md`
  + a row in `DECISIONS.md`; a measurement is `docs/evaluation/YYYY-MM-DD-<slug>.md` + a row in `EVALUATION.md`; a
  fact about a source goes to its note `docs/sources/<source_id>.md`; `STATUS.md` is rewritten when the state of the
  work changes; `ARCHITECTURE.md` when a module or persistent object does; `RUNBOOK.md` for commands.
- **Commit subjects state what is now true**, with the evidence or ADR (no `feat:` prefixes).
- **Tests**: fixture-based parser tests per connector; each §3 invariant has a test; property tests (Hypothesis)
  for calendar, event graph and ledger; golden tests from PLAN §4.11.8 and §4.8.4 as they are verified.

# 6. The repository (PLAN §9)

`src/fin/` — `store/` (L1 raw, manifest, runs, Parquet IO), `ingest/` (connectors), `reference/` (calendar,
source registry), `schema.py` (contracts); `core/`, `quality/`, `derive/`, `ledger/`, `tax/`, `valuation/`,
`analytics/`, `export/`, `llm/` as stages reach them. `tests/` (unit, fixtures), `scripts/`, `docs/`.
Git-ignored: `data/` (zones of PLAN §4.2), `inbox/` (owner documents).

# 7. Where to look

| Need | Read |
|---|---|
| intent, scope, stages and exit criteria | `PLAN.md` (§4 data layer, §10 stages) |
| current state and what is next | `STATUS.md` |
| module map, persistent objects | `ARCHITECTURE.md` |
| decisions and their evidence | `DECISIONS.md` → `docs/decisions/` |
| measurements | `EVALUATION.md` → `docs/evaluation/` |
| open questions (engineering and owner) | `OPEN_QUESTIONS.md` |
| facts about each source | `DATA_SOURCES.md` → `docs/sources/<source_id>.md` |
| commands, scheduler setup | `RUNBOOK.md` |
