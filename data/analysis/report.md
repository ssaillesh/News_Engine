# Sentiment ↔ Stock-price correlation report

_Generated 2026-06-16 05:20_  
Sentiment span: **2025-02-04 → 2026-05-27**

Signed daily news sentiment vs close-to-close return, Pearson r at lags 0–3 trading days (lag > 0 means sentiment *leads* the price move).

| Ticker | Sentiment days | lag 0 r (p) | lag +1 r (p) | strongest |r| |
|---|---|---|---|---|
| AAPL | 28 | 0.11 (0.60) | 0.23 (0.23) | -0.29 @ +3d |
| MSFT | 28 | 0.01 (0.95) | -0.22 (0.25) | -0.22 @ +3d |
| TSLA | 28 | 0.11 (0.57) | -0.18 (0.37) | 0.27 @ +2d |
| NVDA | 28 | 0.14 (0.47) | -0.30 (0.12) | -0.30 @ +1d |

## How to read this
- **r > 0**: positive news sentiment tends to coincide with / precede price *gains*.
- **r < 0**: positive sentiment precedes price *drops* (or the news lags the move).
- **p-value**: probability of seeing this |r| by chance. With the current sparse
  sample most p-values will be > 0.05, i.e. *not statistically significant yet* —
  treat the numbers as directional until the processed-article corpus grows.

## Caveats
- Sentiment is attributed to every ticker an article's query referenced, so
  multi-ticker articles add correlated noise across symbols.
- EPS is best-effort (quarterly, forward-filled) and is not used in the correlation.
- Non-trading-day news is rolled forward to the next trading day.

Artifacts: `merged_panel.csv`, `*_timeseries.png`, `*_scatter_lag1.png`, `lag_correlation_heatmap.png`.