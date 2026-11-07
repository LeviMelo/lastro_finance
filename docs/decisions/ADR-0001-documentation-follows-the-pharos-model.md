## ADR-0001: Documentation follows the PHAROS model; PLAN.md stays the reference of intent

**Date:** 2026-11-07. **Status:** active.

**Context.** The repository started on 2026-11-07 with only `PLAN.md` (56 KB), the owner's foundational plan. The
owner asked that the documentation practices of `pegasus_data` and later projects be inherited. Those come from
`../pharos_project` and were adopted by pegasus_data (its ADR-0001, 2026-09-28) after fourteen overlapping Markdown
files drifted into contradiction. `PLAN.md` §0 and §9 ask for `docs/DECISIONS.md`, `docs/sources/` and a short
`CLAUDE.md`.

**Decision.**
- `CLAUDE.md` = `AGENTS.md`, `STATUS.md` (rewritten in place), `ARCHITECTURE.md`, `DECISIONS.md` +
  `docs/decisions/`, `EVALUATION.md` + `docs/evaluation/`, `OPEN_QUESTIONS.md`, `DATA_SOURCES.md` (an index over the
  per-source recon notes `docs/sources/<source_id>.md` that PLAN §4.13 asks for), `RUNBOOK.md`, `README.md`, and
  `scripts/check_docs.py`.
- The decision index is `DECISIONS.md` at the root, not `docs/DECISIONS.md` as PLAN §9 has it, so the indexes sit
  where the owner's other projects keep them.
- `PLAN.md` is the reference of intent and is not edited. Where reality differs, the discrepancy is recorded in an
  ADR or a source note.
- The model is kept as the user-level skill `project-documentation` so later projects inherit it.

**Alternatives.** *Follow PLAN §9 literally* (`docs/DECISIONS.md`): rejected for consistency with the owner's other
repositories; the content is the same.

**What would reverse it.** The owner asking for the PLAN §9 layout, or the indexes falling behind their entries.
