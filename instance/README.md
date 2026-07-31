# SQLite runtime

GitHub Actions rebuilds `sales_sentinel.db` from the verified daily source and commits the demonstration database. Local execution uses this file persistently. Vercel copies it to ephemeral `/tmp`, so production writes require a durable external database.
