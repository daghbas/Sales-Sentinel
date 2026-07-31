# Model Selection

The evaluation is chronological: the first 75% of feature rows are used for training and the final 25% for testing. No random shuffle is used.

| Candidate | MAE | RMSE | WAPE | sMAPE |
|---|---:|---:|---:|---:|
| Naive lag-1 | 22,524.68 | 31,679.15 | 84.69% | 82.83% |
| Seasonal lag-7 | 23,133.54 | 38,099.94 | 86.98% | 77.44% |
| **Moving average 7** | **18,842.85** | 27,515.69 | **70.85%** | 71.39% |
| Moving average 28 | 22,430.46 | 27,197.38 | 84.33% | 78.64% |
| Extra Trees | 20,803.81 | **26,892.01** | 78.22% | **70.35%** |

Moving average 7 was selected by the declared primary metric, WAPE. The system does not choose a more complex model merely because it is machine learning.
