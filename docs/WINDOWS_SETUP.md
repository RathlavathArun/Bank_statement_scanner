# 🪟 Windows Developer Walkthrough
## Bank Statement Scanner — Start to Finish on Windows

> **Who this is for**: A developer on Windows who has just pulled the project
> from GitHub and wants to run it locally for development.
>
> **What you'll have running by the end**:
> - PostgreSQL, Redis, MinIO (S3), Qdrant — all via Docker
> - FastAPI backend on `http://localhost:8000`
> - Next.js frontend on `http://localhost:3000`

---

## What You Need First

Before touching the project, install these tools. Skip any you already have.

| Tool | Download | Why |
|------|----------|-----|
| Git | https://git-scm.com/download/win | Clone the repo |
| Python 3.11+ | https://www.python.org/downloads/ | Backend API |
| Node.js 20 LTS | https://nodejs.org/ | Frontend |
| Docker Desktop | https://www.docker.com/products/docker-desktop/ | Databases |
| VS C++ Build Tools | https://visualstudio.microsoft.com/visual-cpp-build-tools/ | Compile Python packages |
| Tesseract OCR | https://github.com/UB-Mannheim/tesseract/wiki | OCR for scanned PDFs |
| Poppler | https://github.com/oschwartz10612/poppler-windows/releases | PDF-to-image conversion |

> ⚠️ **Do all installs before moving on.** Skipping any one of them will cause
> errors later in the guide.

---

## Part 1 — One-Time System Setup

### 1.1 — Install Visual C++ Build Tools

1. Go to https://visualstudio.microsoft.com/visual-cpp-build-tools/
2. Click **Download Build Tools**
3. Run the installer
4. In the workloads screen, tick **"Desktop development with C++"**
5. Click **Install** (≈ 6 GB download)
6. **Restart your PC** after it finishes

> This is needed so `pip` can compile `argon2-cffi` (the password hashing library).

---

### 1.2 — Install Tesseract OCR

1. Go to https://github.com/UB-Mannheim/tesseract/wiki
2. Download `tesseract-ocr-w64-setup-5.x.x.exe` (latest stable)
3. Run the installer — use the default path:
   ```
   C:\Program Files\Tesseract-OCR\
   ```
4. **Add to PATH:**
   - Press `Win + S` → search **"Edit the system environment variables"**
   - Click **Environment Variables**
   - Under **System variables**, select `Path` → click **Edit**
   - Click **New** → paste:
     ```
     C:\Program Files\Tesseract-OCR
     ```
   - Click **OK** on all dialogs
5. Open a **new** PowerShell window and verify:
   ```powershell
   tesseract --version
   ```
   You should see version output like `tesseract 5.x.x`

---

### 1.3 — Install Poppler

1. Go to https://github.com/oschwartz10612/poppler-windows/releases
2. Download the latest `Release-xx.xx.x-0.zip`
3. Extract it to:
   ```
   C:\poppler\
   ```
   (so the path `C:\poppler\Library\bin\pdfinfo.exe` exists)
4. **Add to PATH** (same steps as above):
   - Add:
     ```
     C:\poppler\Library\bin
     ```
5. Open a **new** PowerShell window and verify:
   ```powershell
   pdfinfo --version
   ```

---

### 1.4 — Install Docker Desktop

1. Download from https://www.docker.com/products/docker-desktop/
2. Run the installer — accept defaults
3. When it asks, enable **WSL 2 backend** (recommended)
4. After install, **start Docker Desktop** from the Start Menu
5. Wait until the whale icon in the taskbar shows **"Docker Desktop is running"**
6. Verify:
   ```powershell
   docker --version
   docker compose version
   ```

---

## Part 2 — Clone the Repo

Open **PowerShell** (right-click Start → "Windows PowerShell"):

```powershell
# Navigate to where you want the project
cd C:\Projects   # or wherever you like

# Clone
git clone https://github.com/RathlavathArun/Bank_statement_scanner.git

# Enter the project folder
cd Bank_statement_scanner
```

> ✅ The repo has a `.gitattributes` file that automatically ensures all files
> have correct LF line endings on Windows — no manual intervention needed.

---

## Part 3 — Start the Databases (Docker Compose)

The project uses PostgreSQL, Redis, MinIO, and Qdrant. Docker Compose starts all
of them with a single command.

```powershell
# From the repo root
cd infra
docker compose up -d
```

Expected output (first time downloads images — may take a few minutes):
```
✔ Container bse_postgres   Started
✔ Container bse_redis      Started
✔ Container bse_qdrant     Started
✔ Container bse_minio      Started
✔ Container bse_prometheus Started
✔ Container bse_grafana    Started
```

Verify everything is healthy:
```powershell
docker compose ps
```

All containers should show `running` or `healthy`. If any show `Exit`, check logs:
```powershell
docker compose logs postgres
```

> **Ports used**: 5432 (Postgres), 6379 (Redis), 9000–9001 (MinIO), 6333 (Qdrant),
> 9090 (Prometheus), 3001 (Grafana). Make sure none are blocked by another app.

---

## Part 4 — Backend Setup (FastAPI)

Open a **new PowerShell window** (keep the first one with Docker running).

```powershell
# From repo root
cd apps\api
```

### 4.1 — Create a Virtual Environment

```powershell
python -m venv venv
```

### 4.2 — Activate It

```powershell
venv\Scripts\activate
```

Your prompt should now show `(venv)` at the start:
```
(venv) PS C:\Projects\Bank_statement_scanner\apps\api>
```

> If you get an error about script execution policy, run this first:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```
> Then try activating again.

### 4.3 — Install Python Dependencies

```powershell
pip install -r requirements.txt
```

This takes 2–4 minutes the first time. You'll see it download and compile packages.
If `argon2-cffi` fails, it means Visual C++ Build Tools aren't installed correctly
— go back to step 1.1.

### 4.4 — Create the `.env` File

The API needs environment variables. Copy the example:

```powershell
copy .env.example .env
```

Then open `.env` in any text editor (e.g. Notepad):
```powershell
notepad .env
```

Update or confirm these values for local development:
```env
DATABASE_URL=sqlite+aiosqlite:///./bank_statements.db
REDIS_URL=redis://localhost:6379/0
S3_ENDPOINT=http://localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin123
S3_BUCKET=bank-statements
JWT_SECRET_KEY=change-this-to-any-long-random-string
API_HOST=127.0.0.1
API_PORT=8000
DEBUG=True
CORS_ORIGINS=http://localhost:3000
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM_EMAIL=your-email@gmail.com
```

> For local dev, the SMTP fields can be dummy values — email sending will just
> silently fail, which is fine for testing.

### 4.5 — Start the API

```powershell
python main.py
```

Expected output:
```
[START] Starting Bank Statement Extraction API...
[OK] Database tables created / verified
[OK] Template manager initialized with hot-reload support
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

✅ **API is running.** Open http://localhost:8000/docs in your browser — you should
see the interactive Swagger UI.

---

## Part 5 — Frontend Setup (Next.js)

Open a **third PowerShell window**.

```powershell
# From repo root
cd apps\web
```

### 5.1 — Install Node Dependencies

```powershell
npm install
```

Takes about 1–2 minutes.

### 5.2 — Start the Dev Server

```powershell
npm run dev
```

Expected output:
```
▲ Next.js 16.x.x
- Local:        http://localhost:3000
- Network:      http://0.0.0.0:3000

✓ Starting...
✓ Ready in 2.3s
```

✅ **Frontend is running.** Open http://localhost:3000 in your browser.

---

## Part 6 — Verify Everything Works

Open http://localhost:3000 in your browser.

1. **Sign Up** — create a new account
2. **Check your email** for the verification link (or check API logs if SMTP isn't set up)
3. **Log in** → you should land on the dashboard
4. **Upload a bank statement** (PDF or Excel)
5. The statement should appear in the table with status `PARSING` → `READY_FOR_REVIEW`
6. Click **Review →** to see extracted transactions

---

## Quick Reference — Starting the Project Every Day

Once everything is set up, you only need these commands each time:

```powershell
# Terminal 1 — Databases
cd C:\Projects\Bank_statement_scanner\infra
docker compose up -d

# Terminal 2 — API
cd C:\Projects\Bank_statement_scanner\apps\api
venv\Scripts\activate
python main.py

# Terminal 3 — Frontend
cd C:\Projects\Bank_statement_scanner\apps\web
npm run dev
```

To **stop** everything:
```powershell
# Stop API and Frontend: press Ctrl+C in their terminals

# Stop databases
cd infra
docker compose down
```

---

## Troubleshooting

### `venv\Scripts\activate` gives an error about execution policy
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```
Then try activating again.

### `pip install` fails on `argon2-cffi`
Visual C++ Build Tools aren't installed. Go back to Part 1.1.

### `tesseract: command not found`
Tesseract is not on PATH. Make sure you added `C:\Program Files\Tesseract-OCR`
to your **System** PATH (not User PATH), then open a **new** terminal.

### `pdfinfo: command not found`
Poppler is not on PATH. Make sure you added `C:\poppler\Library\bin` to PATH,
then open a **new** terminal.

### Docker Compose fails or containers exit immediately
- Make sure Docker Desktop is running (whale icon in taskbar = running)
- Run `docker compose logs <service-name>` to see what failed
- Port conflicts: check if something else is using 5432, 6379, or 9000

### API starts but shows database errors
Make sure the `.env` file exists in `apps\api\` and has `DATABASE_URL` set.

### Frontend shows "Network Error" or API calls fail
- Make sure the API is running on port 8000
- Check that `CORS_ORIGINS=http://localhost:3000` is set in `.env`

---

## Deploying to AWS (from Windows)

Instead of `infra/deploy.sh` (bash-only), use the PowerShell script:

```powershell
# Prerequisites: AWS CLI configured, Docker Desktop running
aws configure   # enter your Access Key, Secret, region: ap-south-1

# Full deploy (API + Web → ECR → ECS)
cd C:\Projects\Bank_statement_scanner
.\infra\deploy.ps1

# API only
.\deploy_api.ps1
```
