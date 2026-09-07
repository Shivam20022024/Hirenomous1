# Deployment — AWS EC2

Two processes behind nginx + HTTPS. HTTPS is **required** (the AI video interview uses `getUserMedia`, which browsers only allow on secure origins).

## Architecture

| Component | Runs on | Notes |
|---|---|---|
| Frontend (Next.js 16) | `npm start` → :3000 | `next build` first; `NEXT_PUBLIC_API_URL` is baked in at build time |
| Backend (FastAPI) | `uvicorn app.main:app` → :8001 | 1–2 workers; state is in MongoDB |
| MongoDB | Atlas | add the EC2 Elastic IP to Atlas Network Access |
| Interview recordings | local disk `backend/media/interviews/` | on the instance's EBS volume — snapshot it, or move `InterviewStorage` to S3/R2 |

Suggested DNS: `app.example.com` → frontend, `api.example.com` → backend (the API is **not** all under one path prefix, so use a subdomain, not a path proxy).

## 1. Instance

- **t3.small** (2 GB) minimum — `next build` OOMs on 1 GB unless you add a 4 GB swapfile.
- Ubuntu 24.04, ~20 GB gp3, **Elastic IP** attached.
- Security group inbound: 22 (your IP), 80, 443. Do not expose 3000/8001.

## 2. Install

```bash
sudo apt update && sudo apt install -y python3.11 python3.11-venv nginx certbot python3-certbot-nginx
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install -y nodejs

git clone https://github.com/Shivam20022024/Hirenomous1.git && cd Hirenomous1
cd backend && python3.11 -m venv venv && ./venv/bin/pip install -r requirements.txt && cd ..
cd frontend && npm ci && cd ..
```

## 3. Config

```bash
cp backend/.env.example backend/.env.local     # fill in real values
cp frontend/.env.example frontend/.env.local   # NEXT_PUBLIC_API_URL=https://api.example.com
```

Backend values that must change for prod: `MONGODB_URI`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`,
`SECRET_KEY` (`python -c "import secrets; print(secrets.token_hex(32))"`),
`INTERVIEW_PUBLIC_BASE_URL=https://app.example.com`, `SMTP_*`, `BOLNA_*`.

Then build the frontend (env is baked in now):

```bash
cd frontend && npm run build && cd ..
```

## 4. systemd

`/etc/systemd/system/hireonomous-api.service`:

```ini
[Unit]
After=network.target
[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/Hirenomous1/backend
ExecStart=/home/ubuntu/Hirenomous1/backend/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 2
Restart=always
[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/hireonomous-web.service`: same shape, `WorkingDirectory=.../frontend`,
`ExecStart=/usr/bin/npm start`.

```bash
sudo systemctl enable --now hireonomous-api hireonomous-web
```

`WorkingDirectory` matters — `InterviewStorage` writes `media/interviews/` relative to it.

## 5. nginx + HTTPS

API server block needs raised limits for video uploads:

```nginx
server {
  server_name api.example.com;
  client_max_body_size 250M;        # matches INTERVIEW_MEDIA_MAX_MB
  location / {
    proxy_pass http://127.0.0.1:8001;
    proxy_read_timeout 300s;        # STT + LLM turns are slow
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  }
}
```

App server block: plain `proxy_pass http://127.0.0.1:3000;`.

```bash
sudo certbot --nginx -d app.example.com -d api.example.com
```

## 6. Bolna callback

The backend is now reachable at a public HTTPS URL, so update the callback URL in the Bolna
agent config to point at `https://api.example.com/...` (no more tunnel needed).

## One-time org name migration

`backend/scripts/update_org.py` and `update_company.py` set the tenant org name. Edit the
`org_id` / target name before running against a fresh database.
