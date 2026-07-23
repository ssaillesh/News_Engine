# Vercel Deployment Guide

This project is now configured for deployment on Vercel. Follow these steps to deploy your News Engine.

## Prerequisites

1. **Vercel Account**: Sign up at [vercel.com](https://vercel.com)
2. **PostgreSQL Database**: You'll need a Postgres database (Vercel doesn't persist filesystem, so SQLite won't work)
   - Recommended: [Neon](https://neon.tech) (free tier available)
   - Alternative: [Supabase](https://supabase.com), [AWS RDS](https://aws.amazon.com/rds/), [Render](https://render.com)

## Step 1: Prepare Your Database

### Option A: Use Neon (Recommended)

1. Go to [neon.tech](https://neon.tech) and sign up
2. Create a new project
3. Copy the connection string (looks like `postgresql://user:password@host/dbname`)
4. Keep it safe — you'll need it in Step 3

### Option B: Use Another Postgres Provider

Follow your provider's setup instructions and get the PostgreSQL connection string.

## Step 2: Push Code to GitHub

Make sure your code is pushed to GitHub (you've already done this!):

```bash
git push origin main
```

## Step 3: Deploy to Vercel

### Via Vercel Web Dashboard (Easiest)

1. Go to [vercel.com/dashboard](https://vercel.com/dashboard)
2. Click **"Add New"** → **"Project"**
3. Select your GitHub repo (`News_Engine`)
4. In **Environment Variables**, add:
   - `DATABASE_URL`: Your PostgreSQL connection string
   - `ARCHIVER_ENV`: Set to `prod`
   - `API_BASE_URL`: `https://mastodon.social` (or your preferred instance)

5. Click **Deploy**

### Via Vercel CLI

1. Install Vercel CLI:
   ```bash
   npm install -g vercel
   ```

2. Deploy from your project directory:
   ```bash
   vercel
   ```

3. When prompted, select your project and add the environment variables:
   ```
   DATABASE_URL=postgresql://user:password@host/dbname
   ARCHIVER_ENV=prod
   ```

## Step 4: Initialize the Database

After deployment, you need to run migrations once:

```bash
vercel env pull  # Get your .env from Vercel
source .venv/bin/activate
alembic upgrade head
```

Or run via Vercel build hook (if you set one up).

## Step 5: Access Your Archive

Your archive will be live at:
```
https://your-project.vercel.app
```

- **Dashboard**: `https://your-project.vercel.app/`
- **API Docs**: `https://your-project.vercel.app/api/docs`
- **Stats API**: `https://your-project.vercel.app/api/stats`
- **Items API**: `https://your-project.vercel.app/api/statuses`

## Environment Variables Reference

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `DATABASE_URL` | ✅ Yes | — | PostgreSQL connection string |
| `ARCHIVER_ENV` | ❌ No | `prod` | Configuration profile (dev/test/prod) |
| `API_BASE_URL` | ❌ No | `https://mastodon.social` | Mastodon-compatible API endpoint |
| `WEB_PORT` | ❌ No | `8137` | Port (Vercel ignores, uses auto-assigned) |
| `TARGET_HANDLE` | ❌ No | `realDonaldTrump` | Account handle to archive |

## Limitations on Vercel

⚠️ **Important**: The following features have limitations on serverless:

### ❌ Cannot Use
- **SQLite**: Vercel doesn't persist files between deployments
- **Scheduled ingest jobs**: Each request is stateless; use external schedulers
- **Downloaded media**: Store URLs only, not actual files

### ✅ Still Works
- **Read-only API & Dashboard**: Browse and search the archive
- **Data already ingested**: All your data is in PostgreSQL
- **Migrations**: Run via build hooks or manually

## Scheduled Ingestion (Optional)

To keep your archive fresh, set up scheduled ingest runs:

### Option A: GitHub Actions

Create `.github/workflows/ingest.yml`:

```yaml
name: Ingest Archive

on:
  schedule:
    - cron: '0 0 * * *'  # Daily at midnight UTC

jobs:
  ingest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - run: |
          python -m venv .venv
          source .venv/bin/activate
          pip install -e ".[dev]"
          archiver ingest-federal-register
          archiver ingest-presidential-documents
          archiver ingest-white-house
          archiver ingest-news
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
```

### Option B: External Cron Service

Use [cron-job.org](https://cron-job.org) or similar to POST to a Vercel Function endpoint.

## Troubleshooting

### 500 Error on Deploy

Check the Vercel Function logs:
```bash
vercel logs --follow
```

### Database Connection Issues

1. Verify `DATABASE_URL` is set in Vercel dashboard
2. Check that Postgres is accessible (IP whitelist if needed)
3. Run migrations: `alembic upgrade head` locally, then redeploy

### Slow Initial Request

Vercel cold-starts (~5-10s) are normal. Requests warm up after.

## Support

- **Vercel Docs**: https://vercel.com/docs/python
- **FastAPI Docs**: https://fastapi.tiangolo.com/
- **Project README**: See [README.md](README.md)

---

**Happy deploying! 🚀**
