## ADR-0028: A debenture is identified by its SND code, not its ISIN, in its own core table outside `instrument`

**Date:** 2026-11-08. **Status:** active. `ingest/snd.py`, `core/debentures.py`, views `debenture*` (`catalog.py`).

**Context.** ADR-0015 makes an exchange-traded instrument an ISIN with time-ranged tickers, built from COTAHIST. The SND
register (`caracteristicas`, 2026-11-08) has 10,069 rows for 10,004 codes: 200 rows have no ISIN, 16 hold `000000000000`
and 2 hold `0`, and 42 valid ISINs are each carried by several codes (the old Dibens issues: up to 21 series on one
ISIN). `BRKANTDBS999`-type values (40 codes) fail the ISO 6166 check digit and are placeholders. 9 codes appear twice
because two companies co-issue them. The code is unique per debenture otherwise.

**Decision.**
- `core.debenture` has one row per SND code: `debenture_id` = `D` + 12 hex of sha256(`SND:` + code). It is not added
  to `instrument` / `instrument_identifier`: those are COTAHIST's universe (`first_trade`, `last_trade`, `asset_class`
  come from sessions), and an ISIN identity would merge series and drop the codes without one.
- `isin` is kept only when well formed with a valid check digit; `isin_shared_by` says how many codes carry it.
- `issuer_cnpj` is the 14 digits (lowest CNPJ among the code's rows, the others in `co_issuer_cnpjs`); `issuer_id` is
  filled when that CNPJ is in core `issuer` (5,902 of 10,004).
- Terms are the latest version seen; staging keeps the changed rows only (ADR-0014), `kt_first_seen_at` dates them.
- Rows are not dropped on source defects: CPCM12 and PLIM15 have a maturity before the issue date and stay as published.
- Daily PU (`snd_pu_historico`), SND trade statistics and B3 OTC trades (`b3_fixed_income`) join on the code in the
  catalog (`debenture_pu`, `debenture_secondary_price`).

**Alternatives.** ISIN as identity (rejected: shared and missing); extend `instrument` (rejected: breaks its
exchange-traded assumptions and the price_daily/COTAHIST link); ticker plus issue date (not needed: codes are unique).

**Would overturn it.** SND reusing a code for a different debenture, or ANBIMA Data (the announced successor) giving a
stable debenture identifier.
