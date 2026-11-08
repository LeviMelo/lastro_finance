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

**Addendum (2026-11-08): beyond B3's list (OQ-7), and two defects fixed.** Before this addendum, 795 of 3,099
share and unit lines were linked.
- **`fca_ticker`.** CVM FCA securities (2010-) give a (CNPJ, trading code) per form. The code joins the ticker
  valid within a year of the form's date, since tickers are reused. 604 pairs, no instrument with two CNPJs; 176
  of them are new links. Of the 428 B3-root links FCA can check, it contradicts none.
- **`isin_issuer`.** B3's issuer code, letters 3–6 of the ISIN, follows the company across ticker changes. An
  unlinked instrument takes the issuer of a linked share or unit with the same code when:
  - that code maps to one issuer;
  - the ISIN is not a fund quota (CTF);
  - the instrument traded on or after the issuer's CVM registration. Embraer's 1991–2002 classes share EMBR with
    the CNPJ registered in 2006, so they are excluded.
  This adds 506 links.
- **Fund ISINs belong to a majority owner.** Some FII reports carry another fund's quota ISIN: BBPO11 has 204
  reports by its own fund and 5 and 4 by two others. Others carry a share they hold (MBRF3).
  - Fund pairs are now quota ISINs only (CTF).
  - An ISIN belongs to the CNPJ with a strict majority of its reports, and at least 3 of them.
  - The other claims link nothing and are `fund_isin_claim` findings (122).
  - This drops 30 spurious fund issuers and 78 double links.
- **A company root never covers a fund quota.** MBRF11 was an FII (2011–22); Marfrig took the root MBRF in 2025.
- **Result.** 948 of 1,204 share and unit lines trading since 2010 are linked, and 230 of 1,895 older ones. No
  instrument has two issuers, and no link ends before its issuer's registration. Companies gone before 2010 stay
  mostly unlinked: their CVM statements start in 2010, so the link would carry no fundamentals.

**Addendum (2026-11-08, later): B3's ISIN registry and name history.**
- **Why.** FCA trading codes are empty before 2019, so renamed and merged companies stayed unlinked. Those were
  2.5–5 % of spot volume in 2010–2017: Kroton, Cetip, Tractebel, Smiles, BR Properties, BTG units.
- **`b3_isin_emitter`.** B3's ISIN database (`b3_isin`) maps an issuer code to a CNPJ. It only applies to
  companies with a CVM code, and only to lines that traded on or after the company's registration: B3 reassigns
  deleted codes, some of them to funds (TRPL to an FII, CAFB to a fiagro). 1,038 links.
- **`name_history`.** It applies only where every other method fails, and needs two signals to agree on exactly
  one CNPJ:
  - every word of the COTAHIST short name starts a word of a name the company had while the line traded (FCA
    names and previous names by year, or the CVM register within registration);
  - the ISIN code is a subsequence of that name.

  222 links: KROT3 → Cogna, CTIP3 → Cetip, TBLE3 → Engie, BRIN3 → Alper.
- **Precision.** Measured against the other methods, name matching agrees on 2,008 of 2,038 links (98.5 %). It
  loses where similar names exist (SER EDUCA → "Saber Serviços Educacionais"), so it never overrides another
  method.
- **Result.**
  - Share and unit lines trading since 2010: 1,177 of 1,204 linked (97.8 %).
  - Older lines: 1,117 of 1,895.
  - Unlinked spot volume: 2.5 % in 2010, falling to ~0 from 2013.
  - No instrument has two issuers, and no link ends before its issuer's registration.
