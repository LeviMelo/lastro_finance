# b3_holidays — B3: calendário de negociação (feriados)

**Tier:** P. **Recon date:** 2026-11-08. **Fixture:** `tests/fixtures/b3_holidays/feriados_20261108.html` (the whole page).

## 1. Access
- `https://www.b3.com.br/pt_br/solucoes/plataformas/puma-trading-system/para-participantes-e-traders/calendario-de-negociacao/feriados/`:
  one HTML page, 345,767 bytes, 200 with a browser UA, no login.

## 2. Content
- One section per year ("Calendário do mercado YYYY": 2021 to 2026 on 2026-11-08), a heading per month, a table
  per month with `Dia`, `Evento`, `Descrição`.
- The description states per segment what happens. Equities are closed when it says "Não haverá negociação nos
  mercados de renda variável".
- Foreign holidays (US) are listed too: B3 trades on them, with some settlement exceptions.
- Parsed to staging `market_day`: 156 days 2021-2026, 73 with equities closed, 6 with special hours (Ash Wednesday
  and the like).

## 3. Verification
- Against observed COTAHIST sessions 2021-01-01 to 2026-11-06, every ANBIMA business day without a session is a
  listed equities closure, and no listed closure had a session (0 differences each way).
- Local closures are listed too: São Paulo's anniversary (01-25) closed B3 in 2021 and is a trading day since
  2022; 12-24 and 12-31 are closures.

## 6. Ephemerality
The page shows only 2021 onward and adds the coming year when B3 publishes it: archived daily (conditional GET).
It feeds `calendar_day.is_b3_trading_day` after the last observed session, up to the last published year (OQ-1).
