# Deploying JurisAI to Oracle Cloud Always Free

Target: one Always Free VM in **Mumbai (`ap-mumbai-1`) or Hyderabad (`ap-hyderabad-1`)**
running `docker compose` — the app, self-hosted MongoDB, self-hosted Qdrant and Caddy
(automatic HTTPS). Recurring cost: ₹0 (plus an optional domain name). Data and security
logs stay on this VM, in India.

> **Status:** the compose files, Caddy config and scripts below are validated locally
> (merged config, only Caddy is public, backup/restore round-trip, uptime check). Steps 1–3
> and 5–8 need your Oracle account and a domain, so **this has not been run on a real
> Oracle VM yet** — treat the first deployment as the real test of this document and fix
> whatever it gets wrong.

## 0. What you need

- An Oracle Cloud account. Choose the **home region at signup** (Mumbai or Hyderabad) —
  it cannot be changed afterwards.
- A hostname whose DNS you control (a free DuckDNS subdomain works). Caddy needs it to
  issue a certificate; the app's refresh cookie is `Secure`, so **plain HTTP will not
  keep users logged in**.
- A Groq (or Mistral) API key.
- The real **grievance officer's** name, email and postal address (DPDP). The app refuses
  to start in production without them.

## 1. Create the VM

1. Compute → Instances → Create. Image: **Ubuntu 22.04**, shape: **VM.Standard.A1.Flex**
   (Ampere ARM, up to 4 OCPU / 24 GB is free). 2 OCPU / 12 GB is plenty to start.
2. Add your SSH public key. Boot volume 100–150 GB.
3. If you get "Out of capacity", retry later or try the other India region — Always Free
   ARM capacity is not guaranteed.
4. Note the public IP and point your hostname's **A record** at it.

## 2. Open the ports (both layers)

Oracle blocks traffic twice, and forgetting the second one is the usual reason HTTPS
"doesn't work":

1. **VCN → Security List → Ingress rules:** allow TCP **80** and **443** from `0.0.0.0/0`.
   Keep **22** restricted to your own IP.
2. **On the VM** (the Ubuntu image ships restrictive iptables rules):
   ```bash
   sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80  -j ACCEPT
   sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
   sudo apt-get install -y iptables-persistent && sudo netfilter-persistent save
   ```

Do **not** open 8000, 27017 or 6333. The prod overlay publishes nothing but Caddy
(Qdrant is bound to `127.0.0.1` only, for ingestion).

## 3. Install tooling

```bash
sudo apt-get update && sudo apt-get install -y git git-lfs ca-certificates curl
sudo git lfs install --system
curl -fsSL https://get.docker.com | sudo sh && sudo usermod -aG docker $USER   # re-login after
curl -LsSf https://astral.sh/uv/install.sh | sh                                 # for ingestion
docker compose version   # must be >= 2.24 (the overlay uses !reset / !override)
```

## 4. Get the code and configure

```bash
sudo mkdir -p /opt/jurisai && sudo chown $USER /opt/jurisai
git clone https://github.com/innovator-sh/jurisai.git /opt/jurisai && cd /opt/jurisai
git lfs pull                       # the two source PDFs are in LFS; ingest fails without them
cp .env.example .env && chmod 600 .env
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # -> JWT_SECRET_KEY
```

Edit `.env` — everything marked required below must be real:

| Variable | Value |
|---|---|
| `ENVIRONMENT` | `production` |
| `DOMAIN` | your hostname, e.g. `jurisai.example.in` |
| `CORS_ORIGINS` | `https://<DOMAIN>` |
| `JWT_SECRET_KEY` | the generated secret |
| `LLM_PROVIDER`, `GROQ_API_KEY` (or Mistral) | your provider + key |
| `GRIEVANCE_OFFICER_NAME` / `_EMAIL` / `_ADDRESS` | real contact (required) |
| `SECURITY_LOG_DIR` | any non-empty value; the overlay sets `/var/log/jurisai` |
| `CHAT_RETENTION_DAYS`, `BACKUP_RETENTION_DAYS` | `365`, `14` (these are stated on `/privacy`) |

`.env` holds live secrets: never commit it (it is gitignored; CI also runs gitleaks).

## 5. Build the search indexes (one time, and after any corpus change)

```bash
DC="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
$DC up -d qdrant
uv sync
uv run python scripts/ingest.py --corpus ipc     # downloads the ~400 MB embedding model on first run
uv run python scripts/ingest.py --corpus bns
```

## 6. Start everything

```bash
$DC up -d --build
$DC ps
curl -s https://<DOMAIN>/readyz        # {"status":"ok","corpora":{"ipc":true,"bns":true},"mongo":true,...}
```

The first start downloads the embedding model into the `hf_cache` volume (about a minute);
later restarts reuse it. `/healthz` means the process is up; `/readyz` additionally checks
Mongo and both indexes — monitor `/readyz`.

## 7. Verify the compliance behaviour on the live box

```bash
# Production guard: with a grievance field blanked in .env the app must refuse to start.
# CERT-In log: events are written, on this VM, rotated daily, 180 files kept.
$DC exec app ls -l /var/log/jurisai
$DC exec app tail -n 5 /var/log/jurisai/security.jsonl
# Sign up in the browser, then confirm: signup + login_success events appear, and the
# file contains no password, token, email address or question text.
```

Also open `https://<DOMAIN>/privacy` in both languages and check the grievance officer
and the provider named as the recipient of question text.

## 8. Schedule backups and the uptime check

```bash
chmod +x scripts/*.sh
( crontab -l 2>/dev/null
  echo '17 2 * * * cd /opt/jurisai && /opt/jurisai/scripts/backup_mongo.sh >> /var/log/jurisai-backup.log 2>&1'
  echo '*/5 * * * * /opt/jurisai/scripts/uptime_check.sh https://<DOMAIN> >> /var/log/jurisai-uptime.log 2>&1'
) | crontab -
```

- Backups land in `/var/backups/jurisai` (root-readable only) and are pruned after
  `BACKUP_RETENTION_DAYS`. They contain personal data — **do not copy them to a
  foreign-hosted cloud**; that would undo the India-only posture.
- Restore: `scripts/restore_mongo.sh <archive.gz>` (asks for confirmation; replaces the
  live database).
- Better uptime monitoring is an external one (UptimeRobot free tier on `/readyz`), because
  it still works when this whole VM is down. The cron check is the zero-account fallback.

## Operating it

| Task | Command |
|---|---|
| Deploy an update | `git pull && git lfs pull && $DC up -d --build` |
| Re-ingest after a corpus change | repeat step 5, then `$DC restart app` |
| Logs (capped at 5 × 50 MB per service) | `$DC logs -f app` |
| Roll back | `git checkout <previous-tag-or-sha> && $DC up -d --build` |

## Risks to keep in mind

- **Single VM, no managed backups.** Mongo and Qdrant live on one disk. The nightly dump is
  the only safety net; test a restore before you rely on it.
- **Oracle reclaims idle Always Free instances** (sustained very low CPU/network) and does
  not guarantee A1 capacity. The compose files are plain Docker — if the VM is lost,
  restore on any other Linux host in India.
- **Question text leaves the VM**: it goes to the LLM provider named on `/privacy`. The
  provider's servers are outside India. Only the *logs* are India-resident by design.
- **Docker's json-file logs are capped and not the compliance record.** The CERT-In record
  is `/var/log/jurisai/security.jsonl` on the `security_logs` volume. Keep that volume;
  `docker compose down -v` deletes it.
