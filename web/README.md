# Investment Hub — web

Next.js frontend for the investment hub API (`/api/hub`) served by the FastAPI
backend in this repo.

| Page | Route | Backed by |
| --- | --- | --- |
| Dashboard | `/` | `GET /api/hub/dashboard`, `/api/hub/watchlist` (add/remove) |
| Ticker | `/ticker/[symbol]` | `/api/hub/securities/{t}`, `…/prices`, `…/news`; `/api/statuses` for a chart day |
| News feed | `/news` | `/api/statuses` + `/api/facets` (filters live in the URL) |
| Portfolio | `/portfolio` | `/api/hub/portfolio`, `/api/hub/holdings` (add/edit/delete lots) |

## Run

```bash
# 1. backend (repo root)
archiver serve                      # http://127.0.0.1:8137

# 2. frontend
cd web
cp .env.example .env.local          # optional: BACKEND_URL, HUB_WRITE_TOKEN
npm install
npm run dev                         # http://localhost:3000
```

## How it talks to the backend

The browser only calls this app. `app/api/[...path]/route.ts` forwards every
`/api/*` request to `BACKEND_URL`, so there is no CORS setup, and it adds the
`X-Hub-Token` header to writes from `HUB_WRITE_TOKEN` on the server. The token
never reaches the client bundle.

## The price chart

`components/PriceChart.tsx` uses TradingView Lightweight Charts v5: candles or
line, a volume pane, and one news marker per bar, coloured by mean FinBERT
sentiment and sized by peak impact. News is dated by calendar day and bars exist
only on trading days, so each news day is drawn on the next trading bar (weekend
news lands on Monday), or on the last bar if no newer bar exists. Clicking a
marker filters the news list below to the calendar days folded into that bar.
