"""Machine-learning interfaces for Sales Sentinel.

The active transparent adapter lives in ``app.services.forecast_adapters``;
training and chronological evaluation are performed by
``scripts.build_from_redsea``. This package is reserved for future external
regressors and additional model implementations without coupling them to HTTP
routes.
"""
