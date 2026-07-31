# Data Dictionary

| Source column | Normalized field | Meaning |
|---|---|---|
| TRX DATE | sale_date | Transaction date |
| TRX NUMBER | transaction_number | Invoice or credit-note number |
| SALES CHANNEL | channel | Source channel code; code meanings are not documented |
| Type | transaction_type | `INV` or credit-note type |
| ITEM CODE | product.sku | Product code |
| ITEM DESC | product name | Product description |
| FAMILY | family | Product family |
| CLASS | category | Product class used as the primary category |
| SUBCLASS | subclass | Product subclass |
| FRANCHISE | franchise | Brand/franchise label |
| QUANTITY | quantity | Signed quantity |
| Unit Price | unit_price | Unit price before VAT |
| Discount Amount | discount_amount | Signed discount amount from source |
| Discount Amount(%) | discount_percent | Discount percentage |
| Net Amount | net_sales | Net amount before VAT |
| Vat Amount | vat_amount | VAT amount |
| TOTAL AMOUNT | total_amount | Amount including VAT |
