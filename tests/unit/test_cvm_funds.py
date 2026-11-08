"""CVM funds (FII reports, daily NAV, CDA positions): parse the committed real lines, header and value checks, plans."""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from fin.config import Zones
from fin.ingest import cvm_funds as cf
from fin.ingest.base import Mode

FIX = Path(__file__).parents[1] / "fixtures"
CONTRACTS = {**cf.FII_CONTRACTS, **cf.DAILY_CONTRACTS, **cf.CDA_CONTRACTS}
HGLG, KNRI, NEG = "11.728.688/0001-47", "12.005.956/0001-65", "00.613.094/0001-74"
SEP = date(2026, 9, 1)


def row(member: str) -> dict[str, Any]:
    return {"raw_sha256": "a" * 64, "ingest_run_id": "r", "notes": f"x|{member}"}


def parse(fn: Any, source: str, member: str, data: bytes | None = None) -> dict[str, pl.DataFrame]:
    blob = data if data is not None else (FIX / source / member).read_bytes()
    return {p.dataset_id: p.frame for p in fn(blob, row(member))}


def clean(dataset: str, frame: pl.DataFrame) -> None:
    valid, rejected = CONTRACTS[dataset].split(frame)
    assert rejected.height == 0 and valid.height == frame.height > 0


def edit_first_line(data: bytes, column: int, value: bytes) -> bytes:
    head, rest = data.split(b"\r\n", 1)
    first, tail = rest.split(b"\r\n", 1)
    cells = first.split(b";")
    cells[column] = value
    return head + b"\r\n" + b";".join(cells) + b"\r\n" + tail


def test_fii_monthly_nav_and_identity() -> None:
    summary = parse(cf.parse_fii, "cvm_fii", "inf_mensal_fii_complemento_2026.csv")["monthly_summary"]
    clean("monthly_summary", summary)
    sep = summary.filter((pl.col("cnpj") == HGLG) & (pl.col("reference_date") == SEP))
    assert sep.height == 1
    r = sep.row(0, named=True)
    assert r["nav_per_quota_brl"] == Decimal("165.476630173739")  # as written, no rounding
    assert r["quotas_issued"] == Decimal(45601713) and r["version"] == 1
    assert r["net_assets_brl"] == Decimal("7546017797.39") and r["holders_total"] == 613837
    assert r["dividend_yield_month"] == Decimal("0.007052")
    # NAV per quota is net assets / quotas
    assert abs(r["net_assets_brl"] / r["quotas_issued"] / r["nav_per_quota_brl"] - 1) < Decimal("1e-9")
    knri = summary.filter((pl.col("cnpj") == KNRI) & (pl.col("reference_date") == SEP))
    assert knri["nav_per_quota_brl"][0] == Decimal("163.639521340679")
    neg = summary.filter(pl.col("cnpj") == NEG)
    assert neg.height and neg["net_assets_brl"].max() < 0  # real negative NAV is kept, not quarantined

    general = parse(cf.parse_fii, "cvm_fii", "inf_mensal_fii_geral_2026.csv")["monthly_general"]
    clean("monthly_general", general)
    g = general.filter((pl.col("cnpj") == HGLG) & (pl.col("reference_date") == SEP)).row(0, named=True)
    assert g["isin"] == "BRHGLGCTF004" and g["delivered_on"] == date(2026, 10, 15) and g["fiscal_year_end"] == "31/12"
    assert not {"email", "address", "phone"} & set(general.columns)

    balance = parse(cf.parse_fii, "cvm_fii", "inf_mensal_fii_ativo_passivo_2026.csv")["monthly_balance"]
    clean("monthly_balance", balance)
    b = balance.filter((pl.col("cnpj") == HGLG) & (pl.col("reference_date") == SEP)).row(0, named=True)
    assert b["total_invested_brl"] == Decimal("8291806411.18")
    assert b["total_liabilities_brl"] == Decimal("1289637537.45")


def test_fii_quarterly_and_annual() -> None:
    for member, dataset in [
        ("inf_trimestral_fii_geral_2026.csv", "quarterly_general"),
        ("inf_trimestral_fii_imovel_2026.csv", "quarterly_property"),
        ("inf_trimestral_fii_ativo_2026.csv", "quarterly_asset"),
        ("inf_anual_fii_geral_2026.csv", "annual_general"),
    ]:
        out = parse(cf.parse_fii, "cvm_fii", member)
        assert set(out) == {dataset}
        clean(dataset, out[dataset])
    prop = parse(cf.parse_fii, "cvm_fii", "inf_trimestral_fii_imovel_2026.csv")["quarterly_property"]
    assert prop["vacancy_ratio"].drop_nulls().max() <= 1  # a fraction in the 2026 files
    quarter = parse(cf.parse_fii, "cvm_fii", "inf_trimestral_fii_geral_2026.csv")["quarterly_general"]
    assert quarter["quarter_end_date"].null_count() == 0 and quarter["delivered_on"].null_count() == 0


def test_fii_legacy_header_and_optional_columns() -> None:
    for member, dataset in [
        ("inf_mensal_fii_geral_2016.csv", "monthly_general"),
        ("inf_mensal_fii_complemento_2016.csv", "monthly_summary"),
        ("inf_mensal_fii_ativo_passivo_2016.csv", "monthly_balance"),
        ("inf_trimestral_fii_geral_2016.csv", "quarterly_general"),
    ]:
        out = parse(cf.parse_fii, "cvm_fii", member)[dataset]
        clean(dataset, out)
        assert out["cnpj"].null_count() == 0
    bal = parse(cf.parse_fii, "cvm_fii", "inf_mensal_fii_ativo_passivo_2016.csv")["monthly_balance"]
    assert bal["cri_cra_brl"].null_count() == bal.height  # the column does not exist in 2016-2018 files
    gen = parse(cf.parse_fii, "cvm_fii", "inf_mensal_fii_geral_2016.csv")["monthly_general"]
    assert gen["fund_type"].null_count() == gen.height  # Tipo_Fundo_Classe came with CVM 175


def test_fii_zip_and_unrelated_members() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("inf_mensal_fii_geral_2026.csv", (FIX / "cvm_fii" / "inf_mensal_fii_geral_2026.csv").read_bytes())
        z.writestr("inf_anual_fii_diretor_responsavel_2026.csv", b"Nome;CPF\r\nx;y\r\n")  # personal data: never read
    out = list(cf.parse_fii(buf.getvalue(), {"raw_sha256": "b" * 64, "ingest_run_id": "r", "notes": "2026"}))
    assert [(p.dataset_id, p.partition) for p in out] == [("monthly_general", "year=2026")]
    assert list(cf.parse_fii(b'{"zip": "record"}', row("x"))) == []  # the JSON record of an unpacked zip
    assert out[0].frame["raw_locator"][0] == "member=inf_mensal_fii_geral_2026.csv;line=2"


def test_fii_header_change_and_bad_value_raise() -> None:
    member = "inf_mensal_fii_complemento_2026.csv"
    data = (FIX / "cvm_fii" / member).read_bytes()
    with pytest.raises(cf.LayoutError, match="header changed"):
        parse(cf.parse_fii, "cvm_fii", member, data.replace(b"Patrimonio_Liquido", b"Patrimonio_L", 1))
    with pytest.raises(cf.LayoutError, match="do not cast"):
        parse(cf.parse_fii, "cvm_fii", member, edit_first_line(data, 4, b"12x"))  # Total_Numero_Cotistas


def test_daily_three_header_eras() -> None:
    new = parse(cf.parse_inf_diario, "cvm_fi_inf_diario", "inf_diario_fi_202609.csv")["daily"]
    clean("daily", new)
    big = new.filter((pl.col("cnpj") == "07.593.972/0001-86") & (pl.col("reference_date") == date(2026, 9, 30)))
    r = big.row(0, named=True)
    assert r["net_assets_brl"] == Decimal("284132679911.60") and r["quota_value_brl"] == Decimal("8.497325")
    assert r["subscriptions_brl"] == Decimal("1072831957.54") and r["holders"] == 250 and r["subclass_id"] is None
    assert r["fund_type"] == "CLASSES - FIF"
    assert new.filter(pl.col("subclass_id").is_not_null()).height > 0
    neg = new.filter(pl.col("cnpj") == "09.613.232/0001-90")
    assert neg.height and neg["quota_value_brl"].max() < 0  # a negative quota is a real value
    assert new.columns[:4] == ["fund_type", "cnpj", "subclass_id", "reference_date"]

    legacy = parse(cf.parse_inf_diario, "cvm_fi_inf_diario", "inf_diario_fi_202101.csv")["daily"]
    clean("daily", legacy)
    assert legacy["fund_type"].unique().to_list() == ["FI"] and legacy["subclass_id"].null_count() == legacy.height
    hist = parse(cf.parse_inf_diario, "cvm_fi_inf_diario", "inf_diario_fi_200501.csv")["daily"]
    clean("daily", hist)
    assert hist["fund_type"].null_count() == hist.height  # HIST files have no TP_FUNDO
    member = "inf_diario_fi_2001.csv"
    (old,) = cf.parse_inf_diario((FIX / "cvm_fi_inf_diario" / member).read_bytes(), row(member))
    assert old.partition == "year=2001" and old.frame["portfolio_value_brl"].null_count() > 0
    clean("daily", old.frame)


def test_daily_header_change_and_scale_raise() -> None:
    member = "inf_diario_fi_202609.csv"
    data = (FIX / "cvm_fi_inf_diario" / member).read_bytes()
    with pytest.raises(cf.LayoutError, match="header changed"):
        parse(cf.parse_inf_diario, "cvm_fi_inf_diario", member, data.replace(b"VL_QUOTA", b"VL_COTA", 1))
    with pytest.raises(cf.LayoutError, match="header changed"):
        parse(cf.parse_inf_diario, "cvm_fi_inf_diario", member, data.replace(b";NR_COTST", b";NR_COTST;X", 1))
    # net assets with three decimals: numeric(17,2) in the source, so a layout change, never silently rounded
    with pytest.raises(cf.LayoutError, match="more than 2 decimals"):
        parse(cf.parse_inf_diario, "cvm_fi_inf_diario", member, edit_first_line(data, 6, b"1.123"))


def test_cda_blocks_union_and_provenance() -> None:
    frames = []
    for n in range(1, 9):
        member = f"cda_fi_BLC_{n}_202610.csv"
        out = list(cf.parse_cda((FIX / "cvm_fi_cda" / member).read_bytes(), row(member)))
        assert [(p.dataset_id, p.partition) for p in out] == [("position", "month=202610")]
        assert (out[0].frame["block"] == n).all()
        clean("position", out[0].frame)
        frames.append(out[0].frame)
    union = pl.concat(frames)
    assert union.columns == CONTRACTS["position"].names
    b1 = frames[0].row(0, named=True)
    assert b1["position_category"] == "Títulos Públicos" and b1["isin"] == "BRSTNCLF1RH3"
    assert (
        b1["selic_code"] == "210100"
        and b1["final_qty"] == Decimal("20")
        and b1["market_value_brl"] == Decimal("403934.95")
    )
    assert b1["maturity_date"] == date(2027, 9, 1) and b1["reference_date"] == date(2026, 10, 31)
    assert b1["raw_locator"] == "member=cda_fi_BLC_1_202610.csv;line=2"
    b2 = frames[1].row(0, named=True)
    assert b2["held_fund_cnpj"] == "01.165.780/0001-92" and b2["related_issuer"] == "S"
    assert "fund_name" not in union.columns  # the name is not repeated on every position
    b5 = frames[4].row(0, named=True)
    assert b5["index_code"] == "DI1" and b5["index_percent"] == Decimal("102.6")
    assert b5["issuer_tax_id"] == "31.895.683/0001-16"


def test_cda_net_assets_and_legacy_header() -> None:
    pl_ = parse(cf.parse_cda, "cvm_fi_cda", "cda_fi_PL_202610.csv")["net_assets"]
    clean("net_assets", pl_)
    assert pl_.row(0, named=True)["net_assets_brl"] == Decimal("1228168.72") and pl_["cnpj"][0] == "00.017.024/0001-53"
    clean("net_assets", parse(cf.parse_cda, "cvm_fi_cda", "cda_fi_PL_202301.csv")["net_assets"])
    for member in ("cda_fi_BLC_2_202301.csv", "cda_fi_BLC_6_202301.csv"):
        pos = parse(cf.parse_cda, "cvm_fi_cda", member)["position"]
        clean("position", pos)
        assert pos["fund_type"].null_count() == 0
    b2 = parse(cf.parse_cda, "cvm_fi_cda", "cda_fi_BLC_2_202301.csv")["position"]
    assert (
        b2["held_fund_cnpj"].null_count() == 0 and b2["held_subclass_id"].null_count() == b2.height
    )  # none before 175


def test_cda_natural_person_issuer_is_dropped_and_other_members_ignored() -> None:
    member = "cda_fi_BLC_6_202301.csv"
    raw = (FIX / "cvm_fi_cda" / member).read_bytes().split(b"\r\n")
    head, line = raw[0], raw[1].split(b";")
    cols = head.decode("cp1252").split(";")
    assert line[cols.index("PF_PJ_EMISSOR")] == b"PJ"
    line[cols.index("PF_PJ_EMISSOR")] = b"PF"  # synthetic: a made-up person, never a real CPF
    line[cols.index("CPF_CNPJ_EMISSOR")] = b"000.000.000-00"
    line[cols.index("EMISSOR")] = b"PESSOA FICTICIA DE TESTE"
    pos = parse(cf.parse_cda, "cvm_fi_cda", member, head + b"\r\n" + b";".join(line) + b"\r\n")["position"]
    r = pos.row(0, named=True)
    assert r["issuer_person_type"] == "PF" and r["issuer_tax_id"] is None and r["issuer_name"] is None
    line[cols.index("PF_PJ_EMISSOR")] = b""  # a bare CPF with no PF flag is dropped as well
    pos = parse(cf.parse_cda, "cvm_fi_cda", member, head + b"\r\n" + b";".join(line) + b"\r\n")["position"]
    assert pos["issuer_tax_id"][0] is None and pos["issuer_name"][0] is None
    for name in ("cda_fiim_202610.csv", "cda_fie_202610.csv", "cda_fi_CONFID_202610.csv", "cda_fie_CONFID_202610.csv"):
        assert list(cf.parse_cda(b"A;B\r\n1;2\r\n", row(name))) == []


def test_cda_header_change_raises() -> None:
    member = "cda_fi_BLC_4_202610.csv"
    data = (FIX / "cvm_fi_cda" / member).read_bytes()
    with pytest.raises(cf.LayoutError, match="header changed"):
        parse(cf.parse_cda, "cvm_fi_cda", member, data.replace(b"DS_ATIVO", b"DS_ATIVOS", 1))
    pl_data = (FIX / "cvm_fi_cda" / "cda_fi_PL_202610.csv").read_bytes()
    with pytest.raises(cf.LayoutError, match="header changed"):
        parse(cf.parse_cda, "cvm_fi_cda", "cda_fi_PL_202610.csv", pl_data.replace(b"DT_COMPTC", b"DT_REF", 1))


def test_discovery_plans(zones: Zones, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cf, "today_brt", lambda: date(2026, 11, 8))
    schema = {"notes": pl.String, "fetched_at": pl.Datetime("us", "UTC")}
    held: dict[str, pl.DataFrame] = {}
    monkeypatch.setattr(cf, "held_rows", lambda _z, source, _d: held.get(source, pl.DataFrame(schema=schema)))

    fii = list(cf.CvmFii().discover(Mode.BACKFILL, zones))
    assert len(fii) == 3 * (2026 - 2016 + 1) and fii[0].url.endswith(
        "/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_2016.zip"
    )
    assert all(s.unpack_members and s.absent_status == {404} for s in fii)

    nav = list(cf.CvmFiInfDiario().discover(Mode.BACKFILL, zones))
    urls = [s.url.rsplit("/", 1)[1] for s in nav]
    assert (
        urls[0] == "inf_diario_fi_202611.zip"
        and "inf_diario_fi_202101.zip" in urls
        and "inf_diario_fi_2000.zip" in urls
    )
    assert len(nav) == 71 + 21  # monthly 2021-01..2026-11 and HIST 2000..2020
    cda = list(cf.CvmFiCda().discover(Mode.BACKFILL, zones, hist=False))
    assert len(cda) == 47 and cda[-1].url.endswith("cda_fi_202301.zip")  # 2023-01..2026-11 (the last may be a 404)
    assert len(list(cf.CvmFiCda().discover(Mode.BACKFILL, zones))) == 47 + 18  # HIST 2005..2022 by default

    def at(*pairs: tuple[str, date]) -> pl.DataFrame:
        notes = [p for p, _ in pairs]
        return pl.DataFrame(
            {"notes": notes, "fetched_at": [datetime(d.year, d.month, d.day, tzinfo=UTC) for _, d in pairs]}
        )

    held["cvm_fi_inf_diario"] = at(
        ("202611", date(2026, 11, 7)),
        ("202610", date(2026, 11, 6)),
        ("202609", date(2026, 11, 1)),
        ("202511", date(2026, 11, 1)),
        ("202511|inf_diario_fi_202511.csv", date(2026, 11, 1)),
    )
    due = [s.locator for s in cf.CvmFiInfDiario().discover(Mode.INCREMENTAL, zones)]
    # 2026-11 (1 day) and 2026-10 (2 days) are current and previous, due daily; 2026-09 (7 days) weekly, due;
    # 2025-11 (age 12) was fetched 7 days ago: due. Never seen and inside the trailing year: fetched (2026-01);
    # never seen and older: backfill only (2021-01, HIST).
    assert due[:3] == ["202611", "202610", "202609"] and "202511" in due and "202601" in due
    assert "202101" not in due and "hist2005" not in due


def test_large_member_slices_keep_every_line_and_its_number() -> None:
    from fin.ingest.cvm_funds import slices

    data = b"A;B\n" + b"".join(f"{i};x\n".encode() for i in range(1000))
    got = list(slices(data, size=1000))
    assert len(got) > 3 and all(s.startswith(b"A;B\n") for s, _ in got)
    lines = [ln for s, _ in got for ln in s.split(b"\n")[1:] if ln]
    assert lines == [f"{i};x".encode() for i in range(1000)]
    firsts = [f for _, f in got]
    assert firsts[0] == 2 and all(int(s.split(b"\n")[1].split(b";")[0]) + 2 == f for s, f in got)
