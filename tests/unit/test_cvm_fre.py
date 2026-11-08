"""FRE index and capital_social parse from the committed real lines; other members are skipped."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from fin.ingest import cvm_fre

FIX = Path(__file__).parents[1] / "fixtures" / "cvm_fre"
ROW = {"raw_sha256": "a" * 64, "ingest_run_id": "r", "notes": "2022"}


def test_index_and_capital_social() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in ("fre_cia_aberta_2022.csv", "fre_cia_aberta_capital_social_2022.csv",
                     "fre_cia_aberta_capital_social_aumento_2022.csv"):  # fmt: skip
            z.writestr(name, (FIX / name).read_bytes())
    out = {p.dataset_id: p.frame for p in cvm_fre.parse_payload(buf.getvalue(), ROW)}
    assert set(out) == {"document", "capital_social"}  # aumento is not parsed
    doc, cap = out["document"], out["capital_social"]
    assert cvm_fre.DOCUMENT.split(doc)[1].height == 0 and cvm_fre.CAPITAL_SOCIAL.split(cap)[1].height == 0
    itau = cap.filter((cap["cnpj"] == "60.872.504/0001-23") & (cap["capital_type"] == "Capital Integralizado"))
    assert itau.height >= 1 and itau["total"].max() > 9_000_000_000  # whole shares, not thousands
    assert doc["received_on"].null_count() == 0
