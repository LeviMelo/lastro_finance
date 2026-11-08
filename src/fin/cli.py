"""`fin`: the one entrypoint (PLAN §4.12). Owner-facing text is pt-BR (PLAN §11.7)."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from typing import Annotated

import polars as pl
import typer

from fin.config import zones
from fin.ingest.base import Mode, reparse, run_connector
from fin.ingest.registry import CONNECTORS, DAILY, connector, missing_ephemeral
from fin.reference.sources import registry
from fin.store.journal import Journal
from fin.store.manifest import Manifest
from fin.store.raw import RawStore, RawStoreError
from fin.store.runs import SCHEMA as RUNS_SCHEMA
from fin.store.runs import IngestRun, recover

app = typer.Typer(help="LASTRO: dados e análise de investimentos pessoais.", no_args_is_help=True)
export_app = typer.Typer(help="Exportações para o LLM externo (dossiê).", no_args_is_help=True)
app.add_typer(export_app, name="export")


@export_app.command("dossier")
def dossier_cmd(
    portfolio: Annotated[str, typer.Option(help="arquivo TOML da carteira ([holdings] ticker = quantidade)")],
    as_of: Annotated[str | None, typer.Option("--as-of", help="data de referência AAAA-MM-DD (padrão: hoje)")] = None,
) -> None:
    """Gera o dossiê (Markdown + tabelas Parquet) em data/exports/dossier-<data>/."""
    from datetime import date
    from pathlib import Path

    from fin.export.dossier import build
    from fin.ingest.snapshots import today_brt

    d = date.fromisoformat(as_of) if as_of else today_brt()
    typer.echo(f"dossiê: {build(zones(), Path(portfolio), d)}")


MIN_FREE = 5 * 10**9  # bytes of free disk below which ingest refuses to start


@app.command()
def ingest(
    sources: Annotated[list[str], typer.Argument(help="fontes (source_id) ou 'daily' para o job diário")],
    mode: Annotated[Mode, typer.Option(help="backfill | incremental | snapshot")] = Mode.INCREMENTAL,
    years: Annotated[str | None, typer.Option(help="backfill: anos, ex. 2020-2025 ou 2024")] = None,
    families: Annotated[str | None, typer.Option(help="b3_pesquisapregao: famílias, ex. TS ou PR,TS")] = None,
    tickers: Annotated[str | None, typer.Option(help="yahoo_chart: tickers, ex. ITUB4,SLCE3")] = None,
) -> None:
    """Busca, arquiva e carrega as fontes pedidas."""
    z = zones()
    z.home.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(z.home).free
    if free < MIN_FREE:  # a full disk mid-run corrupts nothing (atomic writes) but loses the day: refuse up front
        typer.echo(
            f"ERRO: só {free / 1e9:.1f} GB livres no disco (mínimo {MIN_FREE / 1e9:.0f} GB); nada foi buscado", err=True
        )
        raise typer.Exit(2)
    ids = list(DAILY) if sources == ["daily"] else sources
    errors = 0
    with IngestRun(z, f"ingest {' '.join(sources)} --mode {mode}") as run:
        for sid in ids:
            typer.echo(f"→ {sid}")
            try:
                errors += run_connector(
                    connector(sid),
                    z,
                    run,
                    mode,
                    years=_years(years),
                    families=families.split(",") if families else None,
                    tickers=tickers.split(",") if tickers else None,
                )
            except Exception as e:  # one source failing never stops the others; the run records it
                errors += 1
                run.error(sid, f"{type(e).__name__}: {e}")
                typer.echo(f"  ERRO em {sid}: {e}", err=True)
        if sources == ["daily"]:  # keep staging to one file per partition once small files pile up (ADR-0014)
            from fin.store.compact import compact_staging

            for sid in ids:
                if (z.staging / sid).exists():
                    compact_staging(z.staging / sid)
            from fin.catalog import build as build_catalog
            from fin.quality.findings import run as run_checks

            try:
                run_checks(z, run)
            except Exception as e:  # a failing check never loses the day's archive
                errors += 1
                run.error("quality", f"{type(e).__name__}: {e}")
            build_catalog(z)
        for ds, c in sorted(run.counts.items()):
            typer.echo(f"  {ds}: entrada {c['in']}, saída {c['out']}, quarentena {c['quarantined']}")
        typer.echo(f"execução {run.run_id}: {errors} erro(s)")
    if errors:
        raise typer.Exit(1)


def _years(spec: str | None) -> list[int] | None:
    if not spec:
        return None
    a, _, b = spec.partition("-")
    return list(range(int(a), int(b or a) + 1))


@app.command()
def status() -> None:
    """Frescor por fonte, arquivo bruto e execuções."""
    z = zones()
    crashed = recover(z)
    m = Manifest(z.manifest).read()
    reg = registry()
    typer.echo(f"base de dados: {z.home}")
    if crashed:
        typer.echo(f"execuções interrompidas recuperadas: {', '.join(crashed)}")
    objs = list(RawStore(z.raw).iter_objects())
    size = sum(p.stat().st_size for _, p in objs)
    typer.echo(f"arquivo bruto: {len(objs)} objetos, {size / 1e6:,.1f} MB")
    for name, zone in (("staging", z.staging), ("core", z.core), ("derived", z.derived)):
        if zone.exists():
            zb = sum(p.stat().st_size for p in zone.rglob("*") if p.is_file())
            typer.echo(f"{name}: {zb / 1e6:,.1f} MB")
    free = shutil.disk_usage(z.home).free
    typer.echo(f"espaço livre no disco: {free / 1e9:,.1f} GB (mínimo para ingerir: {MIN_FREE / 1e9:.0f} GB)")
    referenced = set(m["raw_sha256"].to_list())
    orphans = [s for s, _ in objs if s not in referenced]
    if orphans:
        typer.echo(f"ATENÇÃO: {len(orphans)} objeto(s) bruto(s) sem linha no manifesto")
    typer.echo("")
    typer.echo(
        f"{'fonte':<26}{'nível':<6}{'efêmera':<9}{'estado':<11}{'última busca (UTC)':<22}{'última data ref.':<17}"
    )
    for sid, src in sorted(reg.items()):
        rows = m.filter(pl.col("source_id") == sid)
        last = rows["fetched_at"].max() if rows.height else None
        ref = rows["source_reference_date"].max() if rows.height else None
        typer.echo(
            f"{sid:<26}{src.tier:<6}{'sim' if src.ephemeral else 'não':<9}{src.status:<11}"
            f"{(f'{last:%Y-%m-%d %H:%M}' if last else '—'):<22}{(str(ref) if ref else '—'):<17}"
        )
    gaps = missing_ephemeral()
    if gaps:
        typer.echo(f"\nBLOQUEIO: fontes efêmeras sem arquivamento diário (dias perdidos): {', '.join(gaps)}")
    runs = Journal(z.runs, RUNS_SCHEMA).read().filter(pl.col("event") == "end").sort("at")
    if runs.height:
        typer.echo("\núltimas execuções:")
        for r in runs.tail(5).iter_rows(named=True):
            typer.echo(f"  {r['ingest_run_id']}  {r['status']:<8} {r['command'] or ''}")


@app.command("verify-raw")
def verify_raw() -> None:
    """Recalcula o SHA-256 de cada objeto bruto."""
    store = RawStore(zones().raw)
    bad = 0
    n = 0
    for sha, _ in store.iter_objects():
        n += 1
        try:
            store.verify(sha)
        except RawStoreError as e:
            bad += 1
            typer.echo(f"CORROMPIDO: {e}", err=True)
    typer.echo(f"{n} objetos verificados, {bad} corrompido(s)")
    if bad:
        raise typer.Exit(1)


@app.command("catalog")
def catalog_cmd() -> None:
    """Recria o catálogo DuckDB (visões sobre os Parquet; nada é copiado)."""
    from fin.catalog import build

    z = zones()
    made = build(z)
    typer.echo(f"{z.catalog}: {len(made)} visões ({', '.join(made)})")


@app.command("quality")
def quality_cmd(
    checks: Annotated[list[str] | None, typer.Argument(help="verificações (padrão: todas)")] = None,
) -> None:
    """Roda as verificações de qualidade e grava os achados (dq_finding); a situação vem de resolutions.toml."""
    from fin.catalog import build
    from fin.quality.findings import run

    z = zones()
    with IngestRun(z, f"quality {' '.join(checks or [])}".strip()) as r:
        counts = run(z, r, checks)
    build(z)
    f = pl.scan_parquet(z.quality / "dq_finding" / "*.parquet").group_by("check_id", "severity", "status").len()
    for row in f.sort("check_id", "status").collect().iter_rows():
        typer.echo(f"  {row[0]} [{row[1]}] {row[2]}: {row[3]}")
    typer.echo(f"{sum(counts.values())} achado(s) em {len(counts)} verificação(ões)")


@app.command("compact-raw")
def compact_raw(
    sources: Annotated[list[str] | None, typer.Argument(help="fontes (padrão: todas)")] = None,
) -> None:
    """Regrava versões repetidas do bruto como deltas da versão anterior (ADR-0014); os bytes lidos não mudam."""
    from fin.store.compact import compact

    z = zones()
    raw = RawStore(z.raw)
    before = sum(p.stat().st_size for _, p in raw.iter_objects())
    saved = compact(raw, Manifest(z.manifest).read(), sources)
    for sid, n in sorted(saved.items(), key=lambda kv: -kv[1]):
        if n:
            typer.echo(f"  {sid}: {n / 2**20:,.1f} MiB economizados")
    after = sum(p.stat().st_size for _, p in raw.iter_objects())
    typer.echo(f"bruto: {before / 2**30:.2f} GiB -> {after / 2**30:.2f} GiB")


@app.command("compact-staging")
def compact_staging_cmd(
    sources: Annotated[list[str] | None, typer.Argument(help="fontes (padrão: todas)")] = None,
) -> None:
    """Junta os arquivos pequenos de staging (um por objeto bruto) em um arquivo por partição."""
    from fin.store.compact import compact_staging

    z = zones()
    for sid in sources or sorted(p.name for p in z.staging.iterdir() if p.is_dir()):
        fb, fa, bb, ba = compact_staging(z.staging / sid)
        if fb != fa:
            typer.echo(f"  {sid}: {fb} -> {fa} arquivos, {bb / 2**20:,.1f} -> {ba / 2**20:,.1f} MiB")


@app.command("reparse")
def reparse_cmd(
    sources: Annotated[list[str], typer.Argument(help="fontes (source_id) a reprocessar a partir do bruto")],
) -> None:
    """Reprocessa o bruto já arquivado de algumas fontes (após um parser novo ou corrigido), sem buscar nada."""
    z = zones()
    with IngestRun(z, "reparse " + " ".join(sources)) as run:
        manifest = Manifest(z.manifest).read()
        for sid in sources:
            reparse(connector(sid), z, run, manifest)
        errors = list(run.errors)
        counts = dict(run.counts)
    for k, v in counts.items():
        typer.echo(f"  {k}: {v}")
    for e in errors:
        typer.echo(f"  ERRO: {e['where']}: {e['message']}", err=True)
    typer.echo(f"reprocessamento concluído, {len(errors)} objeto(s) com erro")
    if errors:
        raise typer.Exit(1)


@app.command()
def rebuild(
    from_raw: Annotated[bool, typer.Option("--from-raw", help="reconstrói L2-L4 só a partir do bruto")] = False,
) -> None:
    """Reconstrói staging, core, derived e quarentena a partir do arquivo bruto e do manifesto."""
    if not from_raw:
        typer.echo("use --from-raw (a única reconstrução suportada)", err=True)
        raise typer.Exit(2)
    z = zones()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    aside = z.home / f".rebuild-previous-{stamp}"
    moved = []
    for p in z.rebuildable():
        if p.exists():
            aside.mkdir(parents=True, exist_ok=True)
            shutil.move(p, aside / p.name)
            moved.append(p)
    errors: list[dict[str, object]] = []
    try:
        with IngestRun(z, "rebuild --from-raw") as run:
            manifest = Manifest(z.manifest).read()
            for sid in dict.fromkeys(DAILY + tuple(CONNECTORS)):
                reparse(connector(sid), z, run, manifest)
            from fin.quality.findings import run as run_checks

            run_checks(z, run)  # quality/ is rebuildable too (ADR-0022)
            errors = list(run.errors)
    except BaseException:
        for p in z.rebuildable():
            if p.exists():
                shutil.rmtree(p)
        for p in moved:
            shutil.move(aside / p.name, p)
        if aside.exists():
            shutil.rmtree(aside)
        typer.echo("reconstrução falhou; o estado anterior foi restaurado", err=True)
        raise
    if aside.exists():
        shutil.rmtree(aside)
    for e in errors:
        typer.echo(f"  ERRO: {e['where']}: {e['message']}", err=True)
    typer.echo(f"reconstrução concluída a partir do bruto, {len(errors)} objeto(s) com erro")
    if errors:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
