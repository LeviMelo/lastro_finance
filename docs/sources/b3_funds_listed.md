# b3_funds_listed: B3's listed-funds pages

Recon 2026-11-08 in the in-app browser, then curl with a browser UA. Connector `B3FundsListed`
(`src/fin/ingest/b3_funds_listed.py`).

## Access
- Page: `https://sistemaswebb3-listados.b3.com.br/fundsListedPage/ETF`, an Angular app iframed by b3.com.br's
  "ETFs Listados". The older `fundsPage/main/etf` answers 500.
- API: `GET https://sistemaswebb3-listados.b3.com.br/fundsListedProxy/Search/<Endpoint>/<base64(JSON)>`. No login;
  curl with a browser UA works.
- Fund types come from the page's `assets/funds.json`: ETF, ETF-RF, ETF-FII, ETF-CRIPTO (all Fundos.NET type 3),
  FII, FIDC, FIAGRO-FII, FIAGRO-FIDC, CRI, CRA and others.

## Endpoints measured
- `GetListFunds {language, typeFund, pageNumber, pageSize}`: `{page:{totalRecords,totalPages}, results:[{id,
  acronym, fundName, tradingName}]}`. 134 ETF on 2026-11-08; BOVA has id 990 and trading name "ISHARES BOVA".
  The id is the fund's Fundos.NET id. No CNPJ.
- `GetStructuredReports {language, dateInitial, dateFinal, pageNumber, pageSize, idFNET, typeFund, type}`: the
  reports with `urlViewerFundosNet` (…`visualizarDocumento?id=<doc id>`), reference date, delivery
  (dd/mm/yyyy hh:mm BRT) and version. Type 64 is Informe Diário. BOVA (990) holds 25 reports in 2026, the last for
  2026-02-04.
- `GetDetailFund`, `GetFundName` and `GetListClassFund {language, idFNET, idCEM, typeFund}` answer 200 with an
  empty body for ETFs (BOVA, AGRI), in the browser too, so the page's "Sobre o Fundo" shows nothing.

## Use
- Acronym → Fundos.NET id → daily-report doc id → the CNPJ written in that document (`b3_fundosnet_daily`). This
  is B3's own link from a ticker root to a fund, and it checks the trading-name match of ADR-0029.
- The list is current state only, so it is archived daily.
