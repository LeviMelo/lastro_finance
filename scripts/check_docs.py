"""Are the documents internally consistent, and do they describe the code?

Ported from pegasus_data (ADR-0001). The documents are read by people and models who cannot check a claim against
the code, so a dangling ADR, a module missing from the map or a source without a recon note is a false statement
about the project. Checks, all mechanical:

    1  every ADR-NNNN referenced anywhere exists under docs/decisions/
    2  every OQ-N referenced anywhere is an open row, a resolved row, or named in a decision
    3  ADR numbers are unique and contiguous, and each is in the DECISIONS.md index
    4  every evaluation entry is in the EVALUATION.md index, and every docs/ link resolves
    5  every script named in a current document exists in scripts/
    6  every module under src/fin is named in ARCHITECTURE.md, and every module it names exists
    7  every source in src/fin/reference/sources.toml has its recon note, and DATA_SOURCES.md lists it
    8  CLAUDE.md and AGENTS.md are byte-for-byte copies

`docs/history/` is frozen and not scanned. Exits non-zero when anything fails.

    uv run python scripts/check_docs.py
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECISIONS = ROOT / "docs" / "decisions"
EVALUATION = ROOT / "docs" / "evaluation"
SOURCES = ROOT / "docs" / "sources"
RESOLVED = ROOT / "docs" / "history" / "open_questions_resolved.md"
PACKAGE = ROOT / "src" / "fin"

ADR_REF = re.compile(r"ADR-(\d{4})")
OQ_REF = re.compile(r"\bOQ-(\d{1,3})\b")
SCRIPT_REF = re.compile(r"scripts/([A-Za-z0-9_/]+\.(?:py|ps1))")
LINK = re.compile(r"\]\((docs/[^)#\s]+\.md)\)")
ROW = re.compile(r"^\|\s*(\d{1,3})\s*\|", re.MULTILINE)
MODULE_REF = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*(?:/[A-Za-z_][A-Za-z0-9_]*)*(?:\.py|/))`")


def current_documents() -> dict[str, str]:
    out = {p.name: p.read_text(encoding="utf-8") for p in sorted(ROOT.glob("*.md")) if p.name != "PLAN.md"}
    for folder in (DECISIONS, EVALUATION, SOURCES):
        for p in sorted(folder.glob("*.md")):
            out[f"{folder.name}/{p.name}"] = p.read_text(encoding="utf-8")
    return out


def package_modules() -> set[str]:
    out: set[str] = set()
    for p in PACKAGE.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        rel = p.relative_to(PACKAGE).as_posix()
        if rel.endswith("__init__.py"):
            if parent := rel[: -len("__init__.py")]:
                out.add(parent)
            continue
        out.add(rel)
    return out


def main() -> int:
    docs = current_documents()
    print(f"{len(docs)} current documents, {sum(len(v.splitlines()) for v in docs.values()):,} lines")
    failures: list[str] = []

    files = {int(m.group(1)): p.name for p in DECISIONS.glob("ADR-*.md") if (m := re.match(r"ADR-(\d{4})", p.name))}
    defined = sorted(files)
    gaps = [n for n in range(defined[0], defined[-1] + 1) if n not in files] if defined else []
    if gaps:
        failures.append(f"missing ADR numbers: {gaps}")
    index = docs.get("DECISIONS.md", "")
    for n, name in files.items():
        if f"docs/decisions/{name}" not in index:
            failures.append(f"ADR-{n:04d} ({name}) is not in the DECISIONS.md index")
    for name, text in docs.items():
        for num in sorted({int(m) for m in ADR_REF.findall(text)}):
            if num not in files:
                failures.append(f"{name} references ADR-{num:04d}, which does not exist")
    print(f"  {len(defined)} ADRs, {len(gaps)} gaps")

    open_rows = {int(m) for m in ROW.findall(docs.get("OPEN_QUESTIONS.md", ""))}
    resolved = {int(m) for m in ROW.findall(RESOLVED.read_text(encoding="utf-8"))} if RESOLVED.exists() else set()
    in_decisions = {int(m) for n, t in docs.items() if n.startswith("decisions/") for m in OQ_REF.findall(t)}
    known = open_rows | resolved | in_decisions
    for name, text in docs.items():
        for num in sorted({int(m) for m in OQ_REF.findall(text)}):
            if num not in known:
                failures.append(f"{name} references OQ-{num}, which is neither a row nor named in a decision")
    print(f"  {len(open_rows)} open questions, {len(resolved)} resolved")

    ev_index = docs.get("EVALUATION.md", "")
    for p in EVALUATION.glob("*.md"):
        if p.name != "methods.md" and f"docs/evaluation/{p.name}" not in ev_index:
            failures.append(f"docs/evaluation/{p.name} is not in the EVALUATION.md index")
    for name, text in docs.items():
        for link in sorted(set(LINK.findall(text))):
            if not (ROOT / link).exists():
                failures.append(f"{name} links {link}, which does not exist")

    have = {p.relative_to(ROOT / "scripts").as_posix() for p in (ROOT / "scripts").rglob("*") if p.is_file()}
    for name, text in docs.items():
        for script in sorted(set(SCRIPT_REF.findall(text))):
            if script not in have:
                failures.append(f"{name} names scripts/{script}, which does not exist")

    arch = docs.get("ARCHITECTURE.md", "")
    modules = package_modules()
    for module in sorted(modules):
        if f"`{module}`" not in arch:
            failures.append(f"ARCHITECTURE.md does not name the module `{module}`")
    for module in sorted(set(MODULE_REF.findall(arch))):
        if module.startswith(("scripts/", "tests/", "docs/", "src/", "data/")):
            continue
        if module not in modules and not (PACKAGE / module).exists():
            failures.append(f"ARCHITECTURE.md names `{module}`, which is not a module")
    print(f"  {len(modules)} modules")

    registry = tomllib.loads((PACKAGE / "reference" / "sources.toml").read_text(encoding="utf-8"))
    ds = docs.get("DATA_SOURCES.md", "")
    for sid, entry in registry.items():
        if not (ROOT / entry["recon"]).exists():
            failures.append(f"source {sid}: recon note {entry['recon']} does not exist")
        if f"`{sid}`" not in ds:
            failures.append(f"source {sid} is not listed in DATA_SOURCES.md")
    print(f"  {len(registry)} registered sources")

    claude, agents = ROOT / "CLAUDE.md", ROOT / "AGENTS.md"
    if not agents.is_file() or claude.read_bytes() != agents.read_bytes():
        failures.append("CLAUDE.md and AGENTS.md must be byte-for-byte copies")

    print()
    if failures:
        print(f"{len(failures)} problems:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("consistent: every ADR, open question, evaluation entry, script, module and source checks out.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
