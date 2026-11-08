"""B3 COTAHIST historical quote files -> staging `quote` (docs/sources/b3_cotahist.md).

Fixed width: every record is 245 bytes + CRLF; positions from B3's layout PDF (rev. 01, 2017), confirmed on the 1986,
2025 and 2026-11-06 files. Decoded as latin-1 so no byte can fail (1986 has binary garbage in PRAZOT).

Staging is source-shaped:
- prices are exact decimals **as quoted**: in the currency of the day (`modref`: CZ$, CR$, R$…) and per `fatcot`
  units of the instrument. Normalising to BRL per one unit is a core step (PLAN §4.3.4).
- `expiry` is null where the file says 99991231 (no expiry); `isin` holds B3 internal codes before 1995-05-15.

The trailer count means "records + header + trailer" in 1986 and "records" in 2025-2026 (measured); a file whose
trailer matches neither is refused.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, ClassVar

import polars as pl

from fin.config import Zones
from fin.ingest.base import Connector, Mode, Parsed
from fin.ingest.fetch import FetchSpec
from fin.ingest.http import BROWSER_UA
from fin.schema import Column, Contract, Rule

BASE = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist"
RECORD = 245
FIRST_YEAR = 1986
FIRST_DAILY = date(2014, 1, 2)
# Powers of ten observed 1986-2026: 1…10000 in recent years, 100000 (2005) and 1000000 (2016-2017); 0 is refused.
FATCOTS = tuple(10**k for k in range(7))
# TPMERC values of the 2017 PDF, plus 021 observed in 2025-2026 (meaning not documented: OPEN_QUESTIONS).
TPMERCS = (10, 12, 13, 17, 20, 21, 30, 50, 60, 70, 80)

PRICE = pl.Decimal(18, 2)
_P = "quoted price, in `modref` currency per `fatcot` units"

# (name, start, end) 1-based inclusive, from the layout PDF.
FIELDS: tuple[tuple[str, int, int], ...] = (
    ("tipreg", 1, 2),
    ("datpre", 3, 10),
    ("codbdi", 11, 12),
    ("codneg", 13, 24),
    ("tpmerc", 25, 27),
    ("nomres", 28, 39),
    ("especi", 40, 49),
    ("prazot", 50, 52),
    ("modref", 53, 56),
    ("preabe", 57, 69),
    ("premax", 70, 82),
    ("premin", 83, 95),
    ("premed", 96, 108),
    ("preult", 109, 121),
    ("preofc", 122, 134),
    ("preofv", 135, 147),
    ("totneg", 148, 152),
    ("quatot", 153, 170),
    ("voltot", 171, 188),
    ("preexe", 189, 201),
    ("indopc", 202, 202),
    ("datven", 203, 210),
    ("fatcot", 211, 217),
    ("ptoexe", 218, 230),
    ("codisi", 231, 242),
    ("dismes", 243, 245),
)

QUOTE = Contract(
    table="staging.b3_cotahist.quote",
    version=3,
    description="One row per COTAHIST record (TIPREG 01): an instrument's session summary on one trading date.",
    columns=(
        Column("trade_date", pl.Date, "trading session date (DATPRE)", "data do pregão", "date", nullable=False),
        Column("codbdi", pl.String, "BDI classification code (CODBDI)", "código BDI", nullable=False),
        Column(
            "ticker", pl.String, "trading code (CODNEG), valid on trade_date", "código de negociação", nullable=False
        ),
        Column(
            "tpmerc",
            pl.Int16,
            "market type (TPMERC): 10 spot, 20 odd lot, 30 termo, 70/80 options…",
            "tipo de mercado",
            nullable=False,
        ),
        Column("short_name", pl.String, "issuer short name (NOMRES); not an identifier", "nome resumido"),
        Column("especi", pl.String, "share specification (ESPECI: ON, PN, UNT, CI…)", "especificação do papel"),
        Column("prazot", pl.String, "termo term in days (PRAZOT) as written; padding varies", "prazo do termo"),
        Column(
            "modref", pl.String, "currency of the prices (MODREF: R$, CZ$, CR$…)", "moeda de referência", nullable=False
        ),
        Column("open", PRICE, _P, "preço de abertura", "modref per fatcot units"),
        Column("high", PRICE, _P, "preço máximo", "modref per fatcot units"),
        Column("low", PRICE, _P, "preço mínimo", "modref per fatcot units"),
        Column("avg", PRICE, _P, "preço médio", "modref per fatcot units"),
        Column("close", PRICE, _P, "preço do último negócio", "modref per fatcot units"),
        Column("best_bid", PRICE, _P, "melhor oferta de compra", "modref per fatcot units"),
        Column("best_ask", PRICE, _P, "melhor oferta de venda", "modref per fatcot units"),
        Column("n_trades", pl.Int64, "number of trades (TOTNEG)", "número de negócios", "count"),
        Column(
            "qty", pl.Int64, "quantity traded (QUATOT), in units of the instrument", "quantidade negociada", "units"
        ),
        Column("volume", pl.Decimal(20, 2), "traded volume (VOLTOT)", "volume financeiro", "modref"),
        Column("strike", PRICE, "option/termo strike (PREEXE)", "preço de exercício", "modref per fatcot units"),
        Column(
            "strike_correction",
            pl.Int8,
            "strike correction index (INDOPC): 1 US$, 2 TJLP, 8 IGPM, 9 URV",
            "indicador de correção",
        ),
        Column(
            "expiry", pl.Date, "expiry date (DATVEN); null where the file says 99991231", "data de vencimento", "date"
        ),
        Column(
            "fatcot",
            pl.Int32,
            "quote factor (FATCOT): prices are per this many units",
            "fator de cotação",
            "units",
            nullable=False,
        ),
        Column(
            "strike_points",
            pl.Decimal(13, 6),
            "strike in points (PTOEXE), for USD-indexed options",
            "preço de exercício em pontos",
            "points",
        ),
        Column(
            "isin", pl.String, "CODISI: ISIN from 1995-05-15, a B3 internal code before", "código ISIN", nullable=False
        ),
        Column(
            "dismes",
            pl.Int16,
            "distribution number (DISMES): changes at each corporate event",
            "número de distribuição",
            "ordinal",
            nullable=False,
        ),
    ),
    rules=(
        Rule("fatcot_known", pl.col("fatcot").is_in(FATCOTS)),
        Rule("tpmerc_known", pl.col("tpmerc").is_in(TPMERCS)),
        Rule("prices_non_negative", pl.min_horizontal("open", "high", "low", "avg", "close") >= 0),
        Rule("low_le_high", pl.col("low") <= pl.col("high")),
        # an open or close outside [low, high] is the file's (2020-06-08: dozens of closing auctions below the
        # day's low): the session is kept as written and listed by the quality check `ohlc_inconsistent`; quarantining
        # it had dropped 1,237 real sessions (measured 2026-11-08)
        Rule("trades_non_negative", (pl.col("n_trades") >= 0) & (pl.col("qty") >= 0)),
    ),
    key=("trade_date", "ticker", "tpmerc", "prazot"),
)


class LayoutError(ValueError):
    pass


@dataclass(frozen=True)
class CotahistFile:
    member: str
    header_date: date
    trailer_count: int
    records: pl.DataFrame  # parsed TIPREG 01 rows, with raw_locator
    unparsed: pl.DataFrame  # line (latin-1 text), reason, raw_locator: lines that cannot be read at fixed width


UNPARSED = Contract(
    table="staging.b3_cotahist.unparsed_line",
    version=1,
    description="COTAHIST lines that cannot be read at fixed width; kept whole, always quarantined.",
    columns=(
        Column("line", pl.String, "the line as latin-1 text", "linha bruta", nullable=False),
        Column("reason", pl.String, "why it could not be parsed", "motivo", nullable=False),
    ),
    rules=(Rule("unparseable_line", pl.lit(False)),),
)


def _num(col: str, scale: int, dtype: pl.DataType) -> pl.Expr:
    s = pl.col(col)
    if scale == 0:
        return s.str.strip_chars().cast(pl.Int64).cast(dtype)
    return (s.str.head(-scale) + "." + s.str.tail(scale)).cast(dtype)


def _repair(line: str) -> tuple[str | None, str]:
    """A wrong-length line. B3 wrote UTF-8 text into a latin-1 file (2026: `FROTA OCEÂNI`, 246 bytes): when the
    line's bytes decode as UTF-8 to exactly RECORD characters, that is the line. Anything else is unparseable."""
    try:
        fixed = line.encode("latin-1").decode("utf-8")
    except UnicodeDecodeError:
        return None, f"length {len(line)}, not UTF-8"
    if len(fixed) == RECORD:
        return fixed, "utf-8"
    return None, f"length {len(line)} ({len(fixed)} as UTF-8)"


def parse_text(text: str, member: str) -> CotahistFile:
    lines = text.split("\r\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not (lines and lines[0].startswith("00COTAHIST") and lines[-1].startswith("99COTAHIST")):
        raise LayoutError(f"{member}: missing header or trailer")
    header_date = date(int(lines[0][23:27]), int(lines[0][27:29]), int(lines[0][29:31]))
    trailer_count = int(lines[-1][31:42])
    decoded = ["latin-1"] * len(lines)
    bad: list[tuple[int, str, str]] = []
    for i in range(1, len(lines) - 1):
        if len(lines[i]) != RECORD:
            fixed, how = _repair(lines[i])
            if fixed is None:
                bad.append((i + 1, lines[i], how))
            else:
                lines[i], decoded[i] = fixed, how
    bad_idx = {n - 1 for n, _, _ in bad}
    keep = [i for i in range(1, len(lines) - 1) if i not in bad_idx]
    body = pl.DataFrame(
        {"lineno": [i + 1 for i in keep], "line": [lines[i] for i in keep], "decoded": [decoded[i] for i in keep]},
        schema={"lineno": pl.Int64, "line": pl.String, "decoded": pl.String},
    )
    other = body.filter(~pl.col("line").str.starts_with("01"))
    if other.height:
        raise LayoutError(f"{member}: {other.height} records of unknown TIPREG, e.g. line {other['lineno'][0]}")
    unparsed = pl.DataFrame(
        {
            "line": [b[1] for b in bad],
            "reason": [b[2] for b in bad],
            "raw_locator": [f"member={member};line={b[0]}" for b in bad],
        },
        schema={"line": pl.String, "reason": pl.String, "raw_locator": pl.String},
    )
    raw = body.select(
        pl.col("lineno"),
        pl.col("decoded"),
        *[pl.col("line").str.slice(a - 1, b - a + 1).alias(n) for n, a, b in FIELDS],
    )
    df = raw.select(
        pl.col("datpre").str.strptime(pl.Date, "%Y%m%d").alias("trade_date"),
        pl.col("codbdi").str.strip_chars().alias("codbdi"),
        pl.col("codneg").str.strip_chars().alias("ticker"),
        pl.col("tpmerc").cast(pl.Int16).alias("tpmerc"),
        pl.col("nomres").str.strip_chars().alias("short_name"),
        pl.col("especi").str.strip_chars().alias("especi"),
        pl.col("prazot").alias("prazot"),
        pl.col("modref").str.strip_chars().alias("modref"),
        *[
            _num(src, 2, PRICE).alias(dst)
            for src, dst in (
                ("preabe", "open"),
                ("premax", "high"),
                ("premin", "low"),
                ("premed", "avg"),
                ("preult", "close"),
                ("preofc", "best_bid"),
                ("preofv", "best_ask"),
            )
        ],
        _num("totneg", 0, pl.Int64()).alias("n_trades"),
        _num("quatot", 0, pl.Int64()).alias("qty"),
        _num("voltot", 2, pl.Decimal(20, 2)).alias("volume"),
        _num("preexe", 2, PRICE).alias("strike"),
        pl.col("indopc").cast(pl.Int8).alias("strike_correction"),
        pl.when(pl.col("datven") == "99991231")
        .then(None)
        .otherwise(pl.col("datven"))
        .str.strptime(pl.Date, "%Y%m%d")
        .alias("expiry"),
        pl.col("fatcot").cast(pl.Int32).alias("fatcot"),
        _num("ptoexe", 6, pl.Decimal(13, 6)).alias("strike_points"),
        pl.col("codisi").str.strip_chars().alias("isin"),
        pl.col("dismes").cast(pl.Int16).alias("dismes"),
        (
            pl.lit(f"member={member};line=")
            + pl.col("lineno").cast(pl.String)
            + pl.when(pl.col("decoded") == "latin-1").then(pl.lit("")).otherwise(";decoded=" + pl.col("decoded"))
        ).alias("raw_locator"),
    )
    return CotahistFile(member, header_date, trailer_count, df, unparsed)


def check_trailer(f: CotahistFile) -> None:
    n = f.records.height + f.unparsed.height
    if f.trailer_count not in (n, n + 2):
        raise LayoutError(f"{f.member}: trailer says {f.trailer_count}, file has {n} records")


def read_zip(blob: bytes) -> CotahistFile:
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names = z.namelist()
        if len(names) != 1:
            raise LayoutError(f"expected one member, got {names}")
        return parse_text(z.read(names[0]).decode("latin-1"), names[0])


class B3Cotahist(Connector):
    source_id: ClassVar[str] = "b3_cotahist"
    version: ClassVar[str] = "2"
    contracts: ClassVar[dict[str, Contract]] = {"quote": QUOTE, "unparsed_line": UNPARSED}
    user_agent: ClassVar[str | None] = BROWSER_UA

    def derive(self, zones: Zones, run: Any) -> None:
        """Core `instrument`, `instrument_identifier` and `price_daily` (ingest/../core/equities.py, ADR-0015)."""
        from fin.core import equities, events

        equities.build(zones, run)
        events.build(zones, run)

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        """backfill: yearly files `years` (default all, 1986 to last year); incremental/snapshot: the daily files of
        the last `days` business days (default 10). The current year's yearly file is rewritten daily, so it is
        fetched only on backfill."""
        from fin.ingest.snapshots import _calendar, today_brt  # pyright: ignore[reportPrivateUsage]

        if mode is Mode.BACKFILL:
            years: list[int] = list(options.get("years") or range(FIRST_YEAR, today_brt().year))
            for y in years:
                yield FetchSpec(
                    self.source_id,
                    "yearly",
                    f"{BASE}/COTAHIST_A{y}.ZIP",
                    "zip",
                    reference_date=date(y, 12, 31),
                    absent_status=frozenset({404}),
                )
            return
        cal = _calendar(zones)
        end = cal.preceding(today_brt() - timedelta(days=0))
        days = int(options.get("days") or 10)
        for d in cal.business_days(max(FIRST_DAILY, cal.add_business_days(end, -(days - 1))), end):
            yield FetchSpec(
                self.source_id,
                "daily",
                f"{BASE}/COTAHIST_D{d:%d%m%Y}.ZIP",
                "zip",
                reference_date=d,
                absent_status=frozenset({404}),
            )

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        f = read_zip(blob)
        check_trailer(f)
        df = f.records.with_columns(
            pl.lit(row["raw_sha256"]).alias("raw_sha256"), pl.lit(row["ingest_run_id"]).alias("ingest_run_id")
        )
        for (year,), part in df.group_by(pl.col("trade_date").dt.year(), maintain_order=True):
            yield Parsed("quote", f"year={year}", part)
        if f.unparsed.height:
            bad = f.unparsed.with_columns(
                pl.lit(row["raw_sha256"]).alias("raw_sha256"), pl.lit(row["ingest_run_id"]).alias("ingest_run_id")
            )
            yield Parsed("unparsed_line", f"year={f.header_date.year}", bad)
