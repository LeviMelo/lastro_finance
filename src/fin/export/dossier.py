"""The dossier for the external LLM (PLAN §8): `fin export dossier --as-of <date> --portfolio <file>`.

A Markdown report plus Parquet tables in `exports/dossier-<as-of>/`. Every figure carries its as-of date and source
or method; the numbers are computed here (the reader does no arithmetic on raw series); unreliable items are
labeled, not hidden. Owner-facing text is pt-BR.

The portfolio file is TOML, until the ledger (Stage I) exists:

    [holdings]          # ticker = quantity
    ITUB4 = 1000
    [performance]
    since = 2025-10-02  # optional: buy-and-hold window start
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import duckdb
import polars as pl

from fin.config import Zones


@dataclass(frozen=True)
class Portfolio:
    holdings: dict[str, float]
    since: date | None

    @classmethod
    def load(cls, path: Path) -> Portfolio:
        doc = tomllib.loads(path.read_text(encoding="utf-8"))
        perf = doc.get("performance", {})
        since = perf.get("since")
        return cls({k: float(v) for k, v in doc.get("holdings", {}).items()}, since)


def _q(con: duckdb.DuckDBPyConnection, sql: str, params: list[Any]) -> pl.DataFrame:
    """The query as a frame; empty when a view it needs is not in the catalog (its files do not exist yet)."""
    try:
        cur = con.execute(sql, params)
    except duckdb.CatalogException:
        return pl.DataFrame()
    cols = [d[0] for d in cur.description or []]
    return pl.DataFrame(cur.fetchall(), schema=cols, orient="row", infer_schema_length=None)


def holdings_table(con: duckdb.DuckDBPyConnection, p: Portfolio, as_of: date) -> pl.DataFrame:
    rows = []
    for tk, qty in p.holdings.items():
        r = con.execute(
            """
            SELECT i.instrument_id, ins.asset_class, pd.trade_date, CAST(pd.close AS DOUBLE)
                   * pd.brl_num / pd.brl_den AS close_brl
            FROM instrument_identifier i JOIN instrument ins USING (instrument_id)
            JOIN price_daily pd ON pd.instrument_id = i.instrument_id AND pd.market_segment = 'lote_padrao'
            WHERE i.scheme = 'TICKER' AND i.value = ? AND i.vt_from <= ? AND pd.trade_date <= ?
            ORDER BY pd.trade_date DESC LIMIT 1
            """,
            [tk, as_of, as_of],
        ).fetchone()
        if r is None:
            rows.append({"ticker": tk, "quantity": qty, "status": "sem preço (instrumento não encontrado)"})
            continue
        iid, cls, d, close = r
        stale = (as_of - d).days
        rows.append(
            {
                "ticker": tk, "instrument_id": iid, "asset_class": cls, "quantity": qty, "price_date": d,
                "close_brl": close, "market_value_brl": qty * close, "method": "B3 COTAHIST: último fechamento",
                "status": "ok" if stale <= 7 else f"preço defasado ({stale} dias)",
            }
        )  # fmt: skip
    df = pl.DataFrame(rows)
    if "market_value_brl" in df.columns:
        total = df["market_value_brl"].sum()
        df = df.with_columns((pl.col("market_value_brl") / total).alias("weight"))
    return df


def performance(con: duckdb.DuckDBPyConnection, h: pl.DataFrame, since: date, as_of: date) -> pl.DataFrame:
    """Buy-and-hold total and price return per line over [since, as_of], from `price_adjusted`, and the line's
    start value (quantity x the raw close on `since`), which weights the portfolio's buy-and-hold return."""
    out = []
    for r in h.filter(pl.col("instrument_id").is_not_null()).iter_rows(named=True):
        x = con.execute(
            """
            SELECT
              (SELECT close_adjusted FROM price_adjusted WHERE instrument_id = ? AND trade_date <= ?
                ORDER BY trade_date DESC LIMIT 1),
              (SELECT close_adjusted FROM price_adjusted WHERE instrument_id = ? AND trade_date <= ?
                ORDER BY trade_date DESC LIMIT 1),
              (SELECT close_split_adjusted FROM price_adjusted WHERE instrument_id = ? AND trade_date <= ?
                ORDER BY trade_date DESC LIMIT 1),
              (SELECT close_split_adjusted FROM price_adjusted WHERE instrument_id = ? AND trade_date <= ?
                ORDER BY trade_date DESC LIMIT 1),
              (SELECT close FROM price_adjusted WHERE instrument_id = ? AND trade_date <= ?
                ORDER BY trade_date DESC LIMIT 1)
            """,
            [r["instrument_id"], since, r["instrument_id"], as_of] * 2 + [r["instrument_id"], since],
        ).fetchone()
        a0, a1, s0, s1, c0 = x if x else (None, None, None, None, None)
        out.append(
            {
                "ticker": r["ticker"],
                "total_return": (a1 / a0 - 1) if a0 and a1 else None,
                "price_return": (s1 / s0 - 1) if s0 and s1 else None,
                "start_value_brl": r["quantity"] * c0 if c0 else None,
            }
        )
    return pl.DataFrame(out)


def benchmark(con: duckdb.DuckDBPyConnection, since: date, as_of: date) -> dict[str, float | None]:
    if not con.execute("SELECT count(*) FROM duckdb_views() WHERE view_name = 'series_observation'").fetchone()[0]:
        return {"ibovespa": None, "cdi": None}

    def level(sid: str, d: date) -> float | None:
        r = con.execute(
            "SELECT value FROM series_observation WHERE series_id = ? AND vt_reference <= ? "
            "ORDER BY vt_reference DESC LIMIT 1",
            [sid, d.isoformat()],
        ).fetchone()
        return float(r[0]) if r else None

    i0, i1 = level("ipeadata:GM366_IBVSP366", since), level("ipeadata:GM366_IBVSP366", as_of)
    cdi = con.execute(
        "SELECT exp(sum(ln(1 + value::DOUBLE / 100))) - 1 FROM series_observation "
        "WHERE series_id = 'bcb_sgs:12' AND vt_reference > ? AND vt_reference <= ?",
        [since.isoformat(), as_of.isoformat()],
    ).fetchone()
    return {"ibovespa": (i1 / i0 - 1) if i0 and i1 else None, "cdi": cdi[0] if cdi else None}


def upcoming(con: duckdb.DuckDBPyConnection, h: pl.DataFrame, as_of: date) -> pl.DataFrame:
    ids = h.filter(pl.col("instrument_id").is_not_null())["instrument_id"].to_list()
    if not ids:
        return pl.DataFrame()
    up = _q(
        con,
        """
        SELECT e.instrument_id, e.event_type, e.data_com, e.ex_date, e.payment_date, e.cash_per_share,
               e.ratio_num, e.ratio_den, e.sources, e.status
        FROM corporate_event e
        WHERE e.instrument_id IN (SELECT unnest(?)) AND (e.ex_date > ? OR e.payment_date > ?)
        ORDER BY coalesce(e.payment_date, e.ex_date)
        """,
        [ids, as_of, as_of],
    )
    return up.join(h.select("instrument_id", "ticker"), on="instrument_id", how="left") if up.height else up


def fundamentals(con: duckdb.DuckDBPyConnection, h: pl.DataFrame, as_of: date) -> pl.DataFrame:
    tickers = h["ticker"].to_list()
    return _q(
        con,
        """
        SELECT coalesce(on_ticker, pn_ticker) AS line, issuer_name, market_cap_brl, earnings_ttm, earnings_period_end,
               book_value, book_date, price_earnings, price_book
        FROM valuation(?) WHERE on_ticker IN (SELECT unnest(?)) OR pn_ticker IN (SELECT unnest(?))
        """,
        [as_of, tickers, tickers],
    )


def findings(con: duckdb.DuckDBPyConnection, h: pl.DataFrame) -> pl.DataFrame:
    ids = h.filter(pl.col("instrument_id").is_not_null())["instrument_id"].to_list()
    if not ids:
        return pl.DataFrame()
    return _q(
        con,
        """
        SELECT check_id, severity, status, vt, entity_id, detail, resolution_note FROM dq_finding
        WHERE list_has_any(?, [split_part(entity_id, ':', 1), split_part(entity_id, '>', 1),
                               split_part(entity_id, '>', 2)])
        ORDER BY severity DESC, vt DESC
        """,
        [ids],
    )


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{100 * x:+.2f} %".replace(".", ",")


def _f(x: Any) -> float | None:
    return None if x is None else float(x)


def _num(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".")


def _brl(x: float | None) -> str:
    return "—" if x is None else f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def build(zones: Zones, portfolio_path: Path, as_of: date) -> Path:
    p = Portfolio.load(portfolio_path)
    con = duckdb.connect(str(zones.catalog), read_only=True)
    con.execute("SET enable_progress_bar = false")
    out = zones.exports / f"dossier-{as_of.isoformat()}"
    out.mkdir(parents=True, exist_ok=True)
    h = holdings_table(con, p, as_of)
    since = p.since or as_of - timedelta(days=365)
    perf = performance(con, h, since, as_of)
    bench = benchmark(con, since, as_of)
    up = upcoming(con, h, as_of)
    fund = fundamentals(con, h, as_of)
    fnd = findings(con, h)
    for name, df in (("holdings", h), ("performance", perf), ("upcoming", up), ("fundamentals", fund),
                     ("findings", fnd)):  # fmt: skip
        if df.height:
            df.write_parquet(out / f"{name}.parquet")
    w = perf.drop_nulls(["start_value_brl", "total_return"]) if perf.height else perf
    w0 = float(w["start_value_brl"].sum()) if w.height else 0.0
    port_tr = float((w["start_value_brl"] * w["total_return"]).sum()) / w0 if w0 else None
    port_pr = float((w["start_value_brl"] * w["price_return"]).sum()) / w0 if w0 else None
    lines = [
        f"# Dossiê LASTRO — posição em {as_of.isoformat()}",
        "",
        f"Gerado pelo sistema a partir de `{portfolio_path.name}` (a carteira; o razão contábil ainda não existe).",
        "Todo número abaixo é calculado pelo sistema, com data de referência e fonte; itens não confiáveis são",
        "marcados, não omitidos.",
        "",
        "## Posições e avaliação",
        "",
        "| ativo | quantidade | preço (data) | valor de mercado | peso | método | situação |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in h.iter_rows(named=True):
        lines.append(
            f"| {r['ticker']} | {_num(r['quantity'])} | {_brl(r.get('close_brl'))} ({r.get('price_date') or '—'}) | "
            f"{_brl(r.get('market_value_brl'))} | {_pct(r.get('weight')).lstrip('+')} | {r.get('method') or '—'} | "
            f"{r['status']} |"
        )
    total = float(h["market_value_brl"].sum()) if "market_value_brl" in h.columns else None
    lines += [f"| **total** | | | **{_brl(total)}** | 100 % | | |", ""]
    lines += [
        f"## Desempenho ({since.isoformat()} a {as_of.isoformat()}, comprar e manter, pesos do início)",
        "",
        f"- Retorno total da carteira (proventos reinvestidos na data ex): **{_pct(port_tr)}**",
        f"- Retorno de preço: {_pct(port_pr)}",
        f"- Ibovespa (pontos): {_pct(_f(bench['ibovespa']))}; CDI acumulado: {_pct(_f(bench['cdi']))}",
        "- Método: `price_adjusted` (desdobramentos, grupamentos, cisões e proventos a partir de eventos verificados;",
        "  ADR-0016).",
        "",
        "| ativo | retorno total | retorno de preço |",
        "|---|---|---|",
    ]
    for r in perf.iter_rows(named=True):
        lines.append(f"| {r['ticker']} | {_pct(r['total_return'])} | {_pct(r['price_return'])} |")
    lines += ["", "## Fundamentos (como conhecidos na data; ADR-0021)", ""]
    if fund.height:
        lines += ["| linha | emissor | valor de mercado | lucro 12m | P/L | P/VP |", "|---|---|---|---|---|---|"]
        for r in fund.iter_rows(named=True):
            pe = "—" if r["price_earnings"] is None else f"{r['price_earnings']:.1f}".replace(".", ",")
            pb = "—" if r["price_book"] is None else f"{r['price_book']:.2f}".replace(".", ",")
            lines.append(f"| {r['line']} | {r['issuer_name']} | {_brl(r['market_cap_brl'])} | "
                         f"{_brl(r['earnings_ttm'])} | {pe} | {pb} |")  # fmt: skip
    covered = set(fund["line"].to_list()) if fund.height else set()
    issuers = {tk[:4] for tk in covered}
    for tk in h["ticker"].to_list():
        if tk not in covered and tk[:4] not in issuers:
            lines.append(f"| {tk} | — | sem dados na data | — | — | — |")
    lines += ["", "## Próximos eventos", ""]
    if up.height:
        lines += [
            "| ativo | tipo | data com | data ex | pagamento | valor/ação | fontes |",
            "|---|---|---|---|---|---|---|",
        ]
        for r in up.iter_rows(named=True):
            v = _brl(float(r["cash_per_share"])) if r["cash_per_share"] is not None else (
                f"{r['ratio_num']}:{r['ratio_den']}" if r["ratio_num"] else "—")  # fmt: skip
            lines.append(f"| {r['ticker']} | {r['event_type']} | {r['data_com'] or '—'} | {r['ex_date']} | "
                         f"{r['payment_date'] or '—'} | {v} | {r['sources']} |")  # fmt: skip
    else:
        lines.append("Nenhum evento anunciado após a data de referência.")
    lines += ["", "## Achados de qualidade de dados que afetam as posições (ADR-0022)", ""]
    if fnd.height:
        lines += ["| verificação | gravidade | situação | data | detalhe |", "|---|---|---|---|---|"]
        for r in fnd.iter_rows(named=True):
            lines.append(f"| {r['check_id']} | {r['severity']} | {r['status']} | {r['vt']} | {r['detail']} |")
    else:
        lines.append("Nenhum.")
    lines += ["", "## Tabelas anexas", "", *[f"- `{f.name}`" for f in sorted(out.glob("*.parquet"))], ""]
    report = out / "dossie.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    return report
