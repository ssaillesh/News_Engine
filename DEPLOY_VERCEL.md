# Deploying the Dashboard to Vercel

## Architecture

Vercel hosts only the **static dashboard** (`static/index.html`). The Python
pipeline — FastAPI, FinBERT/NER models, Postgres, the 10-minute auto-refresh
loop — cannot run on Vercel (serverless functions cap at 250 MB; torch +
transformers alone is ~2 GB, and Vercel has no long-running processes or
persistent disk). The backend keeps running wherever you deploy the Docker
stack (see `DEPLOY_ORACLE.md`).

```
Browser ──> Vercel (static dashboard)
              └─ rewrites /events, /news, /stats/... ──> your backend (FastAPI :8000)
```

The dashboard uses relative API paths, so `vercel.json` rewrites proxy every
API route to the backend — no code changes and no CORS issues.

## Steps

1. **Deploy the backend first** (e.g. Oracle Cloud via `DEPLOY_ORACLE.md`).
   Note its public URL. HTTPS is strongly recommended — Vercel serves the
   dashboard over HTTPS, and proxying to plain HTTP works via rewrites but
   sends traffic unencrypted between Vercel and your server. Putting Caddy or
   nginx + Let's Encrypt in front of port 8000 fixes that.

2. **Set the backend URL** — replace every `YOUR-BACKEND-HOST` in
   `vercel.json` with your host (e.g. `api.example.com` or `203.0.113.7:8000`
   with `http://` if you skip TLS):

   ```bash
   sed -i '' 's|https://YOUR-BACKEND-HOST|https://api.example.com|g' vercel.json
   ```

3. **Deploy** — either:
   - CLI: `npm i -g vercel && vercel --prod` from the repo root, or
   - Git: push to GitHub and import the repo at vercel.com/new. No framework,
     no build step — `vercel.json` already sets `outputDirectory: static`.

4. **Verify**: open the Vercel URL — the dashboard should load and the header
   status dot should turn green (it polls `/health` through the rewrite).

## Notes

- `.vercelignore` excludes everything except `static/` and `vercel.json`, so
  the Python code and `data/` are never uploaded to Vercel.
- `POST /run/batch` is proxied too — anyone with the Vercel URL can trigger a
  pipeline run. Remove that rewrite from `vercel.json` if you want batch runs
  reachable only directly on the backend.
- If you move the backend, update the host in `vercel.json` and redeploy.
