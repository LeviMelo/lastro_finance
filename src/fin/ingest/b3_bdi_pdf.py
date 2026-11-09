"""B3's daily bulletin PDF, the Boletim Diário do Mercado (docs/sources/b3_bdi_pdf.md): the only B3-official history
of index compositions (31 indices, theoretical quantity and weight) and of the stock-lending balances, served
2022-03-01 → yesterday at `arquivos.b3.com.br/bdi/download/bdi/<YYYY-MM-DD>/BDI_00_<YYYYMMDD>.pdf`.

The file is 4–32 MB a day (1,789 pages on 2026-11-05) and almost all of it repeats what COTAHIST and the Price Report
already hold. So it is streamed (ADR-0034): each day is downloaded, the pages of the index compositions
("Composição das Carteiras de Índices") and of the lending balances (pages that open with "Data Ticker ISIN Empresa
ou Fundo") are copied into a small PDF that is kept, and the rest is dropped. A record keeps the full file's size,
page count, kept page numbers and SHA-256. A few hundred MB in RAM at most, one file per download thread.

Parsed: staging `index_composition` (one row per index, asset and bulletin) and `index_total` (theoretical quantity
total and divisor per index). The lending pages are kept, not parsed yet.
"""

from __future__ import annotations

import io
import re
import threading
from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from typing import Any, ClassVar

import polars as pl
import zstandard

from fin.config import Zones
from fin.ingest.base import Connector, Mode, NotData, Parsed
from fin.ingest.fetch import FetchSpec
from fin.ingest.http import BROWSER_UA
from fin.schema import Column, Contract, Rule

URL = "https://arquivos.b3.com.br/bdi/download/bdi/{d:%Y-%m-%d}/BDI_00_{d:%Y%m%d}.pdf"
KEPT_LEVEL = 19
ZSTD_MAGIC = bytes.fromhex("28b52ffd")
FIRST = date(2022, 3, 1)  # first bulletin served (HTTP 500 before, measured 2026-11-07)

SECTION = "Composição das Carteiras de Índices"
HEADER = re.compile(r"^Código(?: IF)? Ação Tipo Quantidade teórica Participação \(%\)\s*$", re.M)  # "IF" from 2025-26
LENDING = re.compile(r"^Data (?:Ticker|Código IF) (?:Código )?ISIN Empresa ou [Ff]undo", re.M)  # 2022-24 / 2026

ROW = re.compile(r"^([A-Z0-9]{4}\d{1,2}[A-Z]?)\s+(.+?)\s+(\d{1,3}(?:\.\d{3})*)\s+(\d{1,3},\d+)$")
TOTAL_QTY = re.compile(r"Quantidade teórica total:\s*([\d.]+)")
REDUCTOR = re.compile(r"Valor do Redutor:\s*([\d.]+,\d+)")
PERIOD = re.compile(r"^Para\s+(\w+)\s+a\s+(\w+)\s+de\s+(\d{4})")
WEIGHTS_ON = re.compile(r"abertura\s+dos\s+negócios\s+do\s+dia\s+(\d{2})/(\d{2})/(\d{4})")
MONTHS = {m: i for i, m in enumerate(("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
                                      "setembro", "outubro", "novembro", "dezembro"), start=1)}  # fmt: skip


# PDFium is not thread-safe (concurrent calls crash the process, measured 2026-11-09): every use holds this lock, so
# downloads overlap but page work is serial
PDFIUM = threading.Lock()


class LayoutError(ValueError):
    """The kept pages do not read as the confirmed layout."""


COMPOSITION = Contract(
    table="staging.b3_bdi_pdf.index_composition",
    version=1,
    description="One asset of one index portfolio as printed in one daily bulletin (BDI PDF).",
    columns=(
        Column("bulletin_date", pl.Date, "session the bulletin reports", "data do boletim", "date", nullable=False),
        Column("index_name", pl.String, "index as printed (IBOVESPA, IBRX50, SMLL…)", "índice", nullable=False),
        Column("ticker", pl.String, "trading code", "código", nullable=False),
        Column("name_type", pl.String, "short name, class and listing segment as printed", "ação e tipo"),
        Column(
            "theoretical_qty",
            pl.Decimal(38, 0),
            "theoretical quantity of the period",
            "quantidade teórica",
            "shares",
            nullable=False,
        ),
        Column(
            "weight_pct",
            pl.Decimal(38, 6),
            "weight at the opening of `weights_on`",
            "participação",
            "percent",
            nullable=False,
        ),
        Column("weights_on", pl.Date, "session whose opening the weights are for", "abertura de", "date"),
        Column("period_start", pl.Date, "first day of the portfolio's quadrimester", "vigência início", "date"),
        Column("period_end", pl.Date, "last day of the portfolio's quadrimester", "vigência fim", "date"),
        Column(
            "page", pl.Int32, "page in the kept PDF (the full file's page numbers are in the record)", "página", "count"
        ),
    ),
    rules=(
        Rule("weight_range", (pl.col("weight_pct") >= 0) & (pl.col("weight_pct") <= 100)),
        Rule("qty_positive", pl.col("theoretical_qty") > 0),
    ),
    key=("bulletin_date", "period_start", "index_name", "ticker", "raw_sha256"),
)
TOTAL = Contract(
    table="staging.b3_bdi_pdf.index_total",
    version=1,
    description="The theoretical quantity total and divisor (redutor) of one index in one daily bulletin.",
    columns=(
        Column("bulletin_date", pl.Date, "session the bulletin reports", "data do boletim", "date", nullable=False),
        Column("index_name", pl.String, "index as printed", "índice", nullable=False),
        Column("period_start", pl.Date, "first day of the portfolio's quadrimester", "vigência início", "date"),
        Column(
            "theoretical_qty_total",
            pl.Decimal(38, 0),
            "sum of theoretical quantities",
            "quantidade teórica total",
            "shares",
        ),
        Column("reductor", pl.Decimal(38, 10), "index divisor", "redutor", "ratio"),
        Column("n_assets", pl.Int32, "rows parsed for the index", "ativos", "count"),
        Column("qty_sum_ok", pl.Boolean, "parsed quantities add up to the printed total", "soma confere"),
    ),
    rules=(),
    key=("bulletin_date", "index_name", "period_start", "raw_sha256"),
)


def page_texts(blob: bytes) -> list[str]:
    import pypdfium2 as pdfium

    if blob[:4] == ZSTD_MAGIC:
        blob = zstandard.ZstdDecompressor().decompress(blob)
    with PDFIUM:
        doc = pdfium.PdfDocument(blob)
        try:
            return [doc[i].get_textpage().get_text_range() for i in range(len(doc))]
        finally:
            doc.close()


def _kept(text: str) -> bool:
    head = text.lstrip()[:300]
    return (
        bool(HEADER.search(text))
        or SECTION.lower() in head.lower()
        or bool(LENDING.search(text[:1500]))
        or LEGACY in text
    )


_pool: Any = None
POOL_WORKERS = 4  # one PDFium per process: page work runs in parallel without sharing the library


def extract_pages(blob: bytes) -> tuple[bytes, str, dict[str, Any]]:
    """What is kept of a bulletin: its composition and lending pages as a PDF, and a record of the full file. The
    work runs in a small process pool (PDFium is not thread-safe, ~2-25 s a file); `extract_pages_local` is the
    same in this process."""
    global _pool
    if blob[:5] != b"%PDF-":
        raise NotData("B3 BDI: not a PDF")
    with PDFIUM:  # guards the pool's creation; the work itself runs outside the lock
        if _pool is None:
            import atexit
            from concurrent.futures import ProcessPoolExecutor

            _pool = ProcessPoolExecutor(max_workers=POOL_WORKERS)
            atexit.register(_pool.shutdown)  # before the interpreter tears its modules down
        pool = _pool
    return pool.submit(extract_pages_local, blob).result()


def extract_pages_local(blob: bytes) -> tuple[bytes, str, dict[str, Any]]:
    import pypdfium2 as pdfium

    if blob[:5] != b"%PDF-":
        raise NotData("B3 BDI: not a PDF")
    with PDFIUM:
        doc = pdfium.PdfDocument(blob)
        try:
            n = len(doc)
            keep = [i for i in range(n) if _kept(doc[i].get_textpage().get_text_range())]
            new = pdfium.PdfDocument.new()
            try:
                if keep:
                    new.import_pages(doc, keep)
                else:  # a bulletin without those sections: one blank page keeps the PDF valid
                    new.new_page(1, 1)
                buf = io.BytesIO()
                new.save(buf)
            finally:
                new.close()
        finally:
            doc.close()
    record = {"pages": n, "kept_pages": [i + 1 for i in keep], "reader": f"pypdfium2 {_version()}",
              "kept": {"format": "pdf+zstd", "level": KEPT_LEVEL}}  # fmt: skip
    # the page copy repeats each page's fonts and streams uncompressed (11 MB for 109 pages on 2024-09-02, 1.4 MB
    # once compressed): kept as zstd
    return zstandard.ZstdCompressor(level=KEPT_LEVEL).compress(buf.getvalue()), "pzst", record


def _dec(s: str) -> Decimal:
    return Decimal(s.replace(".", "").replace(",", "."))


def _period(text: str) -> tuple[date | None, date | None]:
    m = PERIOD.search(text)
    if not m or m.group(1).lower() not in MONTHS or m.group(2).lower() not in MONTHS:
        return None, None
    y, a, b = int(m.group(3)), MONTHS[m.group(1).lower()], MONTHS[m.group(2).lower()]
    end = date(y + 1, 1, 1) if b == 12 else date(y, b + 1, 1)
    return date(y, a, 1), date.fromordinal(end.toordinal() - 1)


def parse_compositions(
    texts: list[str], pages: list[int], bulletin: date
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    totals: list[dict[str, Any]] = []
    index: str | None = None
    period: tuple[date | None, date | None] = (None, None)
    weights_on: date | None = None
    pending: dict[str, Any] = {}

    def close() -> None:
        nonlocal pending
        if index is None or not pending:
            return
        mine = [r for r in rows if r["index_name"] == index and r["_block"] == pending["block"]]
        total = pending.get("total")
        totals.append({
            "bulletin_date": bulletin, "index_name": index, "period_start": pending.get("period_start"),
            "theoretical_qty_total": total,
            "reductor": pending.get("reductor"), "n_assets": len(mine),
            "qty_sum_ok": None if total is None else sum(r["theoretical_qty"] for r in mine) == total,
        })  # fmt: skip
        pending = {}

    block = 0
    for text, page in zip(texts, pages, strict=True):
        if LENDING.search(text[:1500]) and not HEADER.search(text):
            continue
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        prev = ""
        for i, ln in enumerate(lines):
            # a first session of a quadrimester prints the outgoing and the incoming portfolio, each under its own
            # "Para <month> a <month> de <year>": every table after it belongs to that period
            if PERIOD.match(ln):
                p = _period(ln)
                if p[0] and p != period:
                    close()
                    period, index = p, None
            if ln.startswith("(2)"):
                m = WEIGHTS_ON.search(" ".join(lines[i : i + 3]))
                if m:
                    weights_on = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            if HEADER.match(ln):
                cand = prev
                named = cand and not ROW.match(cand) and ":" not in cand and not HEADER.match(cand) and len(cand) <= 40
                if named and cand != index:  # a new index; a repeated header on a continuation page keeps it
                    close()
                    index = cand
                    block += 1
                    pending = {"block": block, "period_start": period[0]}
                if index is None:
                    raise LayoutError(f"B3 BDI {bulletin} p.{page}: composition table without an index name")
                prev = ln
                continue
            m = ROW.match(ln)
            if m and index is not None:
                rows.append({
                    "bulletin_date": bulletin, "index_name": index, "ticker": m.group(1), "name_type": m.group(2),
                    "theoretical_qty": _dec(m.group(3)), "weight_pct": _dec(m.group(4)), "weights_on": weights_on,
                    "period_start": period[0], "period_end": period[1], "page": page, "_block": pending.get("block"),
                })  # fmt: skip
            t = TOTAL_QTY.search(ln)
            if t and pending:
                pending["total"] = _dec(t.group(1))
            r = REDUCTOR.search(ln)
            if r and pending:
                pending["reductor"] = _dec(r.group(1))
            prev = ln
    close()
    return rows, totals


LEND_START = re.compile(r"^(\d{2})/(\d{2})/(\d{4}) (\S+) (BR[A-Z0-9]{10})\b")
LEND_NUM = r"(-|\d[\d.]*(?:,\d+)?%?)"
LEND_MARKET = re.compile(r"\s(Neg\.\s*Eletr\s*[ôo]\s*nica\s*D\s*\+\s*(\d)|Registro|Total|Renda Fixa)$")
LEND_TRADE_TAIL = re.compile(r"\s(\d[\d.]*)\s(\d[\d.]*)\s(\d[\d.]*,\d+)" + (r"\s" + LEND_NUM) * 6 + r"$")
LEND_OPEN_TAIL = re.compile(r"\s(\d[\d.]*)\s(-|\d[\d.]*,\d+)\s(-|\d[\d.]*,\d+)$")


def _num(s: str | None) -> Decimal | None:
    if s is None or s == "-":
        return None
    return _dec(s.rstrip("%"))


LEGACY = "Ação Empresa Tipo Saldo em número de ações Balanço (R$)"  # "Banco de Títulos", 2022 to 2024
LEGACY_AS_OF = re.compile(r"ações emprestadas em (\d{2})/(\d{2})/(\d{4})")
LEGACY_ROW = re.compile(r"^([A-Z0-9]{4}\d{1,2}[A-Z]?)\s+(.+?)\s+(\d[\d.]*)\s+(\d[\d.]*,\d{2})$")
_NOT_ROW = ("BDI", "Data ", "Boletim Diário", "Clearing", "Banco de Títulos", "Em atenção", "Ação Empresa")


def _lend_kind(line: str) -> str | None:
    """The table a header line opens: `open` (balances, "Saldo em quantidade") or `trade` (registered loans)."""
    if not line.startswith("Data ") or "Empresa ou" not in line:
        return None
    return "open" if "Saldo" in line else "trade"


def _complete(kind: str, rec: str) -> bool:
    tail = (LEND_TRADE_TAIL if kind == "trade" else LEND_OPEN_TAIL).search(rec)
    return bool(tail) and bool(LEND_MARKET.search(" " + rec[: tail.start()].strip()))


def lending_records(texts: list[str], pages: list[int]) -> list[tuple[str, int, str]]:
    """The lending rows of the kept pages, each joined across the lines it wraps over: (kind, page, text). Kind is
    `open` (open balances by market), `trade` (registered loans) or `legacy` (the 'Banco de Títulos' balance per
    asset of 2022-24, whose rows carry no date or ISIN: the balance date is in the page's opening sentence, and the
    record text is prefixed with it as `dd/mm/yyyy|`)."""
    out: list[tuple[str, int, str]] = []
    kind = "open"
    as_of = ""
    for text, page in zip(texts, pages, strict=True):
        legacy = LEGACY in text
        if not legacy and (not LENDING.search(text[:1500]) or HEADER.search(text)):
            continue
        m = LEGACY_AS_OF.search(" ".join(text.split()))
        if m:
            as_of = f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
        cur: list[str] | None = None
        for raw in text.splitlines():
            ln = raw.strip()
            if not ln:
                continue
            if legacy:
                if ln.startswith("Quadro Analítico"):  # the next section (futures open interest) shares the page
                    break
                if ln.startswith(_NOT_ROW) or re.match(r"^\d+ REFERENTE", ln):
                    if cur:
                        out.append(("legacy", page, as_of + "|" + " ".join(cur)))
                    cur = None
                    continue
                cur = (cur or []) + [ln]
                if LEGACY_ROW.match(" ".join(cur)) or len(cur) >= 4:
                    out.append(("legacy", page, as_of + "|" + " ".join(cur)))
                    cur = None
                continue
            k = _lend_kind(ln)
            if k:
                if cur:
                    out.append((kind, page, " ".join(cur)))
                kind, cur = k, None
                continue
            if LEND_START.match(ln):
                if cur:
                    out.append((kind, page, " ".join(cur)))
                cur = [ln]
            elif cur is not None:
                if ln == "BDI" or ln.startswith("Boletim Diário") or re.match(r"^\d+ REFERENTE", ln):
                    out.append((kind, page, " ".join(cur)))
                    cur = None
                    continue
                cur.append(ln)
            else:
                continue
            if cur and _complete(kind, " ".join(cur)):  # a finished row takes no more lines (section text follows)
                out.append((kind, page, " ".join(cur)))
                cur = None
        if cur:
            out.append(("legacy" if legacy else kind, page, (as_of + "|" if legacy else "") + " ".join(cur)))
    return out


def parse_lending(
    texts: list[str], pages: list[int], bulletin: date
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    trades: list[dict[str, Any]] = []
    opens: list[dict[str, Any]] = []
    for kind, page, rec in lending_records(texts, pages):
        if kind == "legacy":
            day, _, body = rec.partition("|")
            m = LEGACY_ROW.match(body)
            d = date(int(day[6:]), int(day[3:5]), int(day[:2])) if day else None
            opens.append({
                "bulletin_date": bulletin, "trade_date": d, "ticker": m.group(1) if m else body.split(" ")[0],
                "isin": None, "name_type": m.group(2) if m else None, "market": "Total" if m else None,
                "quantity": _num(m.group(3)) if m else None, "avg_price_brl": None,
                "value_brl": _num(m.group(4)) if m else None, "page": page, "raw_text": body,
            })  # fmt: skip
            continue
        s = LEND_START.match(rec)
        assert s is not None
        base = {"bulletin_date": bulletin, "trade_date": date(int(s.group(3)), int(s.group(2)), int(s.group(1))),
                "ticker": s.group(4), "isin": s.group(5), "page": page, "raw_text": rec}  # fmt: skip
        tail = (LEND_TRADE_TAIL if kind == "trade" else LEND_OPEN_TAIL).search(rec)
        body = rec[s.end() : tail.start()].strip() if tail else ""
        mk = LEND_MARKET.search(" " + body) if tail else None
        market = None
        if mk:
            market = f"Neg. Eletrônica D+{mk.group(2)}" if mk.group(2) else mk.group(1)
            body = (" " + body)[: mk.start()].strip()
        base |= {"name_type": body or None, "market": market}
        if kind == "trade":
            g = tail.groups() if tail and mk else (None,) * 9
            trades.append(base | {
                "n_contracts": None if g[0] is None else int(_dec(g[0])), "quantity": _num(g[1]),
                "value_brl": _num(g[2]), "lender_rate_min": _num(g[3]), "lender_rate_avg": _num(g[4]),
                "lender_rate_max": _num(g[5]), "borrower_rate_min": _num(g[6]), "borrower_rate_avg": _num(g[7]),
                "borrower_rate_max": _num(g[8]),
            })  # fmt: skip
        else:
            g = tail.groups() if tail and mk else (None,) * 3
            opens.append(base | {"quantity": _num(g[0]), "avg_price_brl": _num(g[1]), "value_brl": _num(g[2])})
    return trades, opens


_LEND_COMMON = (
    Column("bulletin_date", pl.Date, "session the bulletin reports", "data do boletim", "date", nullable=False),
    Column("trade_date", pl.Date, "date printed on the row (2022-24: the balance date of the page)", "data", "date"),
    Column("ticker", pl.String, "trading code", "código", nullable=False),
    Column("isin", pl.String, "ISIN (not printed before mid-2024)", "código ISIN"),
    Column("name_type", pl.String, "issuer or fund name and share type as printed", "empresa ou fundo"),
    Column("market", pl.String, "Neg. Eletrônica D+0 / D+1, Registro, Total, Renda Fixa", "mercado"),
)
LEND_TRADE = Contract(
    table="staging.b3_bdi_pdf.lending_trade",
    version=1,
    description="Stock-lending contracts registered in one session, per asset and market (BDI 'Empréstimos "
    "registrados'). Rates are % a year.",
    columns=(
        *_LEND_COMMON,
        Column("n_contracts", pl.Int64, "contracts", "número de contratos", "count"),
        Column("quantity", pl.Decimal(38, 0), "assets lent", "quantidade de ativos", "shares"),
        Column("value_brl", pl.Decimal(38, 2), "value lent", "valor em R$", "BRL"),
        Column("lender_rate_min", pl.Decimal(38, 4), "lender rate, minimum", "taxa doador mínima", "pct_per_year"),
        Column(
            "lender_rate_avg", pl.Decimal(38, 4), "lender rate, weighted by trades", "taxa doador média", "pct_per_year"
        ),
        Column("lender_rate_max", pl.Decimal(38, 4), "lender rate, maximum", "taxa doador máxima", "pct_per_year"),
        Column("borrower_rate_min", pl.Decimal(38, 4), "borrower rate, minimum", "taxa tomador mínima", "pct_per_year"),
        Column(
            "borrower_rate_avg",
            pl.Decimal(38, 4),
            "borrower rate, weighted by trades",
            "taxa tomador média",
            "pct_per_year",
        ),
        Column("borrower_rate_max", pl.Decimal(38, 4), "borrower rate, maximum", "taxa tomador máxima", "pct_per_year"),
        Column("raw_text", pl.String, "the row as joined from the page", "texto"),
    ),
    rules=(Rule("parsed", pl.col("quantity").is_not_null() & pl.col("market").is_not_null()),),
    key=("bulletin_date", "ticker", "market", "raw_sha256"),
)
LEND_OPEN = Contract(
    table="staging.b3_bdi_pdf.lending_open",
    version=1,
    description="Open stock-lending balance at the end of one session, per asset and market (BDI 'Posições em "
    "aberto'): the short-interest series.",
    columns=(
        *_LEND_COMMON,
        Column("quantity", pl.Decimal(38, 0), "assets on loan", "saldo em quantidade", "shares"),
        Column("avg_price_brl", pl.Decimal(38, 4), "average price (none on Total rows)", "preço médio", "BRL"),
        Column("value_brl", pl.Decimal(38, 2), "balance value", "saldo em R$", "BRL"),
        Column("raw_text", pl.String, "the row as joined from the page", "texto"),
    ),
    rules=(Rule("parsed", pl.col("quantity").is_not_null() & pl.col("market").is_not_null()),),
    key=("bulletin_date", "ticker", "market", "raw_sha256"),
)
CONTRACTS = {
    "index_composition": COMPOSITION,
    "index_total": TOTAL,
    "lending_trade": LEND_TRADE,
    "lending_open": LEND_OPEN,
}


def _frame(rows: list[dict[str, Any]], contract: Contract, row: dict[str, Any]) -> pl.DataFrame:
    schema = {c.name: c.dtype for c in contract.columns}
    df = pl.DataFrame([{k: r.get(k) for k in schema} for r in rows], schema=schema, orient="row")
    loc = [f"kept_page={r['page']}" if "page" in r else f"index={r['index_name']}" for r in rows]
    return df.with_columns(
        pl.Series("raw_locator", loc, dtype=pl.String),
        pl.lit(row["raw_sha256"]).alias("raw_sha256"),
        pl.lit(row["ingest_run_id"]).alias("ingest_run_id"),
    )


def parse_payload(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    bulletin = row["source_reference_date"]
    texts = page_texts(blob)
    rows, totals = parse_compositions(texts, list(range(1, len(texts) + 1)), bulletin)
    part = f"year={bulletin.year}"
    if rows:
        yield Parsed("index_composition", part, _frame(rows, COMPOSITION, row))
        yield Parsed("index_total", part, _frame(totals, TOTAL, row))
    trades, opens = parse_lending(texts, list(range(1, len(texts) + 1)), bulletin)
    if trades:
        yield Parsed("lending_trade", part, _frame(trades, LEND_TRADE, row))
    if opens:
        yield Parsed("lending_open", part, _frame(opens, LEND_OPEN, row))


class B3BdiPdf(Connector):
    """Streams the daily bulletin PDF, keeping only the composition and lending pages (ADR-0034)."""

    source_id: ClassVar[str] = "b3_bdi_pdf"
    version: ClassVar[str] = "1"
    user_agent: ClassVar[str | None] = BROWSER_UA
    contracts: ClassVar[dict[str, Contract]] = CONTRACTS
    concurrency: ClassVar[int] = 4  # each download waits on its own pool process (POOL_WORKERS)
    timeout: ClassVar[float] = 300
    LOOKBACK_BUSINESS_DAYS = 10

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        from fin.ingest.snapshots import archived_dates, calendar_for, today_brt

        cal = calendar_for(zones)
        end = cal.preceding(today_brt())
        have = archived_dates(zones, self.source_id, "bdi")
        if mode is Mode.BACKFILL:
            years: list[int] | None = options.get("years")
            lo = max(FIRST, date(min(years), 1, 1)) if years else FIRST
            hi = min(end, date(max(years), 12, 31)) if years else end
            days = cal.business_days(lo, hi) if lo <= hi else []
        else:
            days = cal.business_days(cal.add_business_days(end, -self.LOOKBACK_BUSINESS_DAYS), end)
        for d in reversed(days):
            if d in have:
                continue
            yield FetchSpec(
                self.source_id,
                "bdi",
                URL.format(d=d),
                "pdf",
                reference_date=d,
                conditional=False,
                min_bytes=1000,
                locator=f"bdi={d:%Y%m%d}",
                extract=extract_pages,
            )

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        return parse_payload(blob, row)

    def derive(self, zones: Zones, run: Any) -> None:
        from fin.core import indices

        indices.build(zones)  # index membership: B3's portfolios, ETF holdings before them (ADR-0036)


def _version() -> str:
    from importlib.metadata import version

    return version("pypdfium2")
