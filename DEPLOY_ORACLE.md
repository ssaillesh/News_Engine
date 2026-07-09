# Deploying on Oracle Cloud (Always Free)

Target: one **VM.Standard.A1.Flex** instance (Ampere ARM, Always Free) running the
whole stack via docker compose — Postgres, Redis, and the API server with its
10-minute news auto-refresh.

## 1. Create the account and instance (manual, ~20 min)

1. Sign up at https://signup.cloud.oracle.com (card required for identity
   verification only — Always Free resources never charge). Pick a **home region**
   close to you; ARM capacity varies by region, so if instance creation fails later
   with "out of capacity", retry at another time of day (capacity is re-released
   continually).
2. Console → **Compute → Instances → Create instance**:
   - Image: **Ubuntu 22.04** (aarch64)
   - Shape: **VM.Standard.A1.Flex** — set **4 OCPUs / 24 GB RAM** (the full
     Always-Free allowance; you can also split it into smaller instances later)
   - Boot volume: 100+ GB (200 GB total is free)
   - Add your SSH public key (`cat ~/.ssh/id_ed25519.pub`; generate with
     `ssh-keygen -t ed25519` if you don't have one)
3. Open the dashboard port. Instance page → its **subnet** → **security list** →
   **Add ingress rule**: source `0.0.0.0/0`, protocol TCP, destination port **8000**.

## 2. Prepare the server (run over SSH)

```bash
ssh ubuntu@<INSTANCE_PUBLIC_IP>

# Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
exit   # log back in so the docker group applies
ssh ubuntu@<INSTANCE_PUBLIC_IP>

# Ubuntu's own firewall also blocks 8000 by default on Oracle images
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8000 -j ACCEPT
sudo netfilter-persistent save
```

## 3. Deploy the app

```bash
git clone https://github.com/ssaillesh/News-Intelligence-Pipeline.git
cd News-Intelligence-Pipeline

cp .env.example .env
nano .env    # paste your ALPHA_VANTAGE_API_KEY and FINNHUB_API_KEY (both free):
             #   https://www.alphavantage.co/support/#api-key
             #   https://finnhub.io/register

docker compose up -d --build   # first build ~5-10 min (compiles hdbscan, pulls torch)
```

First startup downloads the three HuggingFace models (~1.5 GB) into a persistent
volume — one-time cost, then the first news refresh runs automatically.

## 4. Verify

```bash
curl localhost:8000/health            # {"status":"ok"}
curl localhost:8000/refresh/status    # last_run_at fills in after the first cycle
docker compose logs -f api            # watch the pipeline run
```

Then open `http://<INSTANCE_PUBLIC_IP>:8000` in a browser — the dashboard should
show today's stories in the LATEST bar, refreshing every 10 minutes.

## Operations

| Task              | Command                                              |
|-------------------|------------------------------------------------------|
| Update to latest  | `git pull && docker compose up -d --build`           |
| Logs              | `docker compose logs -f api`                         |
| Restart           | `docker compose restart api`                         |
| Back up database  | `docker exec nlp_postgres pg_dump -U nlp_user nlp_pipeline > backup.sql` |

Notes:
- `restart: unless-stopped` on every service means the stack survives reboots
  and crashes — no extra systemd setup needed.
- Oracle can reclaim **idle** Always-Free instances; this app fetches news every
  10 minutes, which keeps CPU activity well above the idle threshold.
- Postgres and Redis are bound to localhost only; the only public port is 8000.
  Note the dashboard and API are otherwise unauthenticated — fine for a demo,
  add auth or an allowlist before putting anything sensitive behind it.

## Migrating the data collected on your Mac (optional)

```bash
# On the Mac
pg_dump -U nlp_user nlp_pipeline > local_data.sql
scp local_data.sql ubuntu@<INSTANCE_PUBLIC_IP>:~

# On the server (with the stack running)
docker exec -i nlp_postgres psql -U nlp_user nlp_pipeline < ~/local_data.sql
```
