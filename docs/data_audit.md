# Data Audit — Redsea Daily Sales

## Provenance

- Source used by the repository: `data/raw/RedSea_Data_Cleaned.csv`
- SHA-256: `c0e8c57748e18d6da0a7cf83909f85043946aa257c8799b151595120f5d7fb66`
- Saudi electronics showroom data from Jeddah.
- The source is retained without modification; processed derivatives are separate.

## Verified counts

| Check | Result |
|---|---:|
| Raw rows | 2,700 |
| Exact duplicate rows | 5 |
| Accepted clean rows | 2,695 |
| Unique transaction numbers | 1,661 |
| Product codes | 352 |
| Categories (`CLASS`) | 23 |
| Sales channels | 4 |
| Date range | 2023-07-01 to 2023-10-31 |
| Observed sales days | 121 |
| Calendar days | 123 |
| Missing dates | 2023-09-01, 2023-09-15 |

The two absent dates are not treated as factual zero-sales days. Linear interpolation is used only inside the forecasting series to preserve daily lag continuity; the imputed values are not stored in the sales table.

## Financial treatment

- `INV` rows are sales invoices.
- Non-`INV` rows are treated as credit notes/returns.
- Signed quantity and signed net amount are retained.
- Net sales are stored before VAT.
- Total amount includes VAT.
- Discount amount is retained as supplied by the source.

## Missing fields

The source does not include dependable stock-on-hand, stockout flags, branch comparisons, campaign identifiers, or a documented sales-channel dictionary. These gaps are never silently invented.
