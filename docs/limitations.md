# Remaining Limitations

1. The dataset covers one showroom and four months only.
2. Annual seasonality, Ramadan, both Eids and repeated school seasons cannot be learned.
3. The source has no stock-on-hand or stockout indicator.
4. Detailed promotions and campaign identifiers are unavailable.
5. Sales-channel codes exist but their official meanings are not documented.
6. WAPE is 70.85%; the model is a Pilot and not production-ready.
7. The 90-day forecast is blocked by code until at least 365 calendar days are available.
8. SQLite is persistent locally. On Vercel, the bundled demo database is copied to ephemeral `/tmp`; writes are not durable.
