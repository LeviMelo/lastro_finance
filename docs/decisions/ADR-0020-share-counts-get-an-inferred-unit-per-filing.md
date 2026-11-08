## ADR-0020: CVM share counts get an inferred unit per filing, anchored to B3's current count

**Date:** 2026-11-07. **Status:** active. `core/shares.py`, core `share_count`.

**Context.** CVM's `composicao_capital` states no unit. Measured on 340 issuers against B3's current
`totalNumberShares`:
- 201 file in units (PETR: 12,888,732,761, equal to B3's count);
- 93 file in thousands (ITUB: 11,026,869 against 11,026,869,192);
- 46 differ otherwise (counts changed since the filing, or a mapping mismatch);
- some issuers switch: Bradesco files thousands until DFP 2023 and units from 2024.

**Decision.**
- The latest filing per issuer and form is anchored to B3: unit 1 or 1,000, whichever lands within 30 % of B3's count.
- Walking back, a filing keeps the next one's unit unless the raw counts jump by a factor between 300 and 3,000 (or
  its inverse), which toggles it.
- Without an anchor, the unit is null and no unit-free count is given. No guess is made.

**Measured.** 18,485 filing rows, 7,905 with an inferred unit. Bradesco's switch is found at 2024.

**Limits.** Issuers no longer listed (no B3 count) stay without units. FRE capital tables could anchor them later.
