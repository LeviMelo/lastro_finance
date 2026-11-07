# <source_id> — <institution>: <short name>

**Tier:** P | S | U. **Recon date:** YYYY-MM-DD. **Fixture:** `tests/fixtures/<source_id>/` (what each file is).

Every statement below was measured on the recon date against a real response, unless marked *(from docs)* or
*(not verified)*. A claim from memory is not a fact here.

## 1. Access
- Official URL(s), access method (HTTP file, REST/OData, HTML backend), auth, terms/licence notes.
- What was tried and what failed (DNS / TCP / TLS / User-Agent / other endpoints), when a request did not succeed.

## 2. Datasets
| dataset_id | granularity | history depth | cadence | publication lag | URL pattern |
|---|---|---|---|---|---|

## 3. Layout
- Link to the official layout document; field dictionary (name, type, unit, meaning) as confirmed against the fixture.
- Two or three sample rows, verbatim.

## 4. Quirks
- Encoding, decimal and date formats, scale factors, sentinels, schema changes over time (with dates).

## 5. Identity fields
- Which fields map to which PLAN §4.3.2 schemes (TICKER, ISIN, CNPJ, CVM_CODE, …).

## 6. Ephemerality
- Does the source publish only "today" or a rolling window? If so, what is lost if a day is not archived.

## 7. Open questions
