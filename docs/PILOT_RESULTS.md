# Sales Sentinel Pilot Results

## Data
- 2,700 raw Redsea rows; 2,695 after removal of five exact duplicates.
- One Saudi showroom, July–October 2023.
- Real transaction-level daily data; no synthetic sales were added.

## Time-based evaluation
| Model | MAE | RMSE | WAPE | sMAPE |
|---|---:|---:|---:|---:|
| Naive | 21,663.84 | 31,894.87 | 82.39% | 80.04% |
| Moving Average | 19,261.51 | 28,613.15 | 73.26% | 73.17% |
| Extra Trees | 21,070.83 | 27,002.72 | 80.14% | 71.78% |

Selected by WAPE: **Moving Average**. Decline classification: Precision 0, Recall 0, F1 0, PR-AUC 0.5714. These results are not production-grade.

## Verified local checks
- Four core tests passed.
- Python source compilation passed.
- Full Flask dependency installation could not be completed in the isolated local package index; Vercel build/runtime verification must be used for endpoint validation.

## Demo accounts
- Administrator: `admin` / `Admin@2026!`
- Analyst: `analyst` / `Analyst@2026!`

## Limitations
- 90-day forecast is deliberately blocked.
- Inventory and campaign metadata are unavailable.
- Vercel's local SQLite filesystem is ephemeral; use the Windows/local deployment for persistent writes.
