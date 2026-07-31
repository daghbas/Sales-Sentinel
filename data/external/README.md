# External Saudi indicators

The available Saudi POS weekly indicator dataset is intentionally **not merged into the current model training**, because the active model is trained on daily company sales and the weekly file is an external market signal. It can be added later through a lagged as-of join after source-date validation. Duplicate copies must never be concatenated because that would double the market observations.
