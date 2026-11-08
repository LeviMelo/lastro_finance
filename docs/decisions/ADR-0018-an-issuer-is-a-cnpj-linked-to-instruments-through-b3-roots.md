## ADR-0018: An issuer is a CNPJ; it is linked to its instruments through B3's CVM code → ticker root

**Date:** 2026-11-07. **Status:** active. Implements PLAN §4.3.2 `issuer` (`core/issuers.py`).

**Decision.**
- **One issuer per CNPJ** (14 digits): `issuer_id` = `C` + 12 hex of SHA-256.
  - It carries every CVM code of the CNPJ, newest registration first (Itaú: 19348, 1279), and the newest
    registration's status, sector and names.
  - CVM's register is a current-state file, archived daily; changed-row staging keeps its history from now on.
- **Link to instruments.** B3's issuer list maps a CVM code to a ticker root.
  - An instrument belongs to that root's issuer when a modern ticker of it (root + 1–2 digits) traded.
  - The link spans the instrument's whole history. ISIN changes after mergers make new instruments, which join the
    issuer through their own roots; events link old to new later (ADR-0015).
- **Personal data stays out.** The register's contact fields (named officers, their phones, e-mails and addresses)
  are not parsed.

**Measured (2026-11-07).** 2,532 issuers (661 active), 344 of them linked to 1,575 instruments. Itaú Unibanco:
ITUB3/ITUB4 from 2009-05-20, the date of its post-merger ISINs.

**Limits.**
- Issuers outside B3's list (cancelled before it, or never listed in the spot market) have no link.
- Fund issuers (FIIs) are not in CVM's company register; their identity is the fund's CNPJ in Fundos.NET.

**Addendum (2026-11-08): funds.** FII and Fiagro funds are issuers too, keyed by their CNPJ.
- The (CNPJ, quota ISIN) pairs come from CVM's FII monthly reports and Fundos.NET payout notices. Quotas join to
  instruments by ISIN (method `fund_isin`).
- 1,474 fund issuers, 712 quota lines linked; issuers total 4,006 and links 2,287.
