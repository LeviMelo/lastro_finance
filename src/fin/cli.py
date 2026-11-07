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


@app.command()
def ingest(
    sources: Annotated[list[str], typer.Argument(help="fontes (source_id) ou 'daily' para o job diário")],
    mode: Annotated[Mode, typer.Option(help="backfill | incremental | snapshot")] = Mode.INCREMENTAL,
) -> None:
    """Busca, arquiva e carrega as fontes pedidas."""
    z = zones()
    ids = list(DAILY) if sources == ["daily"] else sources
    errors = 0
    with IngestRun(z, f"ingest {' '.join(sources)} --mode {mode}") as run:
        for sid in ids:
            typer.echo(f"→ {sid}")
            try:
                errors += run_connector(connector(sid), z, run, mode)
            except Exception as e:  # one source failing never stops the others; the run records it
                errors += 1
                run.error(sid, f"{type(e).__name__}: {e}")
                typer.echo(f"  ERRO em {sid}: {e}", err=True)
        for ds, c in sorted(run.counts.items()):
            typer.echo(f"  {ds}: entrada {c['in']}, saída {c['out']}, quarentena {c['quarantined']}")
        typer.echo(f"execução {run.run_id}: {errors} erro(s)")
    if errors:
        raise typer.Exit(1)


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
    try:
        with IngestRun(z, "rebuild --from-raw") as run:
            manifest = Manifest(z.manifest).read()
            for sid in DAILY + tuple(s for s in CONNECTORS if s not in DAILY):
                reparse(connector(sid), z, run, manifest)
    except BaseException:
        for p in z.rebuildable():
            if p.exists():
                shutil.rmtree(p)
        for p in moved:
            shutil.move(aside / p.name, p)
        typer.echo("reconstrução falhou; o estado anterior foi restaurado", err=True)
        raise
    if aside.exists():
        shutil.rmtree(aside)
    typer.echo("reconstrução concluída a partir do bruto")


if __name__ == "__main__":
    app()
