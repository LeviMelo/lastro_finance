## ADR-0035: Stock-event ratios come from B3's lists, the filing's text and B3's EG marker before the price move

**Date:** 2026-11-09. **Status:** active. Extends ADR-0016. `core/events.py` (`eg_events`, `repair_ratios`,
`filing_ratios`, `_snap`), `ingest/cvm_ipe_docs.py`.

**Context.**
- The monthly panel flagged 67 month-returns beyond +300 %/-90 % (ADR-0032). Each was graded on the price jump, its
  persistence over 20 sessions and the shares-per-trade change.
- **Real moves** (Americanas 2023, PDG, Ambipar, Azul, Gol): the price falls while lots grow.
- **Missing or wrong regroupings:** the price jumps, stays up, and lots shrink by the same factor:
  - TELB4 2011, ×9,546: Yahoo has 1:10, Telebras' AGE call says 10,000 into 1;
  - TIBR5/6 2015, ×110;
  - BTTL3 2015, ×24: the filing says 25:1;
  - MLFT4 2016, ×9.8; DMMO3 2019, ×9.2; BBTG12 2017, ×7.9.
- **B3 marks regroupings itself.** From the ex-date, COTAHIST's ESPECI field carries "EG" (ex-grupamento) for a
  while. Neither the 2017 layout PDF nor the bulletin's legend defines the suffix, so it was measured over every
  first EG session since 1994 (469):
  - 316 fall on a regrouping other sources prove; the price rose on 308 and fell on none;
  - the 101 with no event behave alike (81 rises, 15 flat, 0 falls).
- 530 applied stock events carry a filing link but take their ratio from Yahoo or the price.
- RAD serves each filing as PDF, Word 97, docx or HTML, whatever the Content-Type says. Under load it answers
  HTTP 200 with an empty 4.3 KB shell: 255 of 263 first answers on 2026-11-09, while the restatement backfill ran.

**Decision. A ratio is taken from, in order:**
1. **B3's event lists** (unchanged).
2. **The filing's own text.** `cvm_ipe_docs` fetches each linked filing once. The shell counts as a busy answer:
   retried, never stored. Its regrouping, split and bonus sentences are read to staging `ipe_ratio`:
   - "à razão de 25 … para 1", "cada 1 ação … desdobrada em 4", "1 nova ação para cada 5", "bonificação de
     10 %".
   - `filing_ratios` keeps the stated ratio of the event's direction nearest the move, within 30 %.
   - Equal to the event's ratio within 0.1 % ("16,666666667 %" for 7:6): the event gains `cvm_ipe_doc`.
   - Otherwise it replaces a ratio guessed from the price (snapped move, EG marker), but a ratio another source
     states (Yahoo) only when it fits the move better, because a filing can quote several proposals. The
     corrected event is added and the original becomes `conflicting`.
   - Measured 2026-11-09 on 367 filings: 170 events confirmed, 28 corrected (38:9 → 4:1, 47:6 → 8:1,
     1:47,981 → 1:50,000, 1:8,571 → 1:10,000).
3. **B3's EG marker** (`eg_events`). A first EG session that no factor adjusts and no known stock event explains,
   with a rise of 1.5× or more after at most 60 days without a trade, is a regrouping:
   - its ratio is the conventional one nearest the move, within 25 %;
   - else a simple fraction under 10, within 5 %;
   - a large odd ratio is left out, because from the price alone it would only absorb the move.
4. **Filing-backed price ratios.** A filing-backed event whose ratio misses the move by more than 3× is replaced by
   the conventional ratio the move shows (`repair_ratios`).
   - `_snap` prefers a conventional ratio within 10 % for moves of 10× or more (BTTL3: 24.1× → 25).
   - The filing-proven price rule (`implied_ipe_events`) accepts gaps of up to 60 days (BTTL3 had none traded for
     35 days).

**Consequences.**
- Events 52,933 → 53,031; the 9 golden event checks pass.
- TELB4 and INEP4 are 1:10,000; TIBR5/6 1:100; BTTL3 1:25; MLFT4 and DMMO3 1:10.
- A ratio that is wrong in every source and has no filing, no EG mark and no conventional fit stays as the price
  shows it, and its month stays `ret_suspect`.
