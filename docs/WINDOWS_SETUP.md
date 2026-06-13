# 🪟 Windows Developer Walkthrough
## Bank Statement Scanner — Pull → Edit → Deploy → Verify

> **Goal**: Make a code change on Windows, deploy it to AWS, and see it live
> on the production URL. No local server needed.

---

## What You'll Have at the End

```
Your Windows Machine
      │
      │  git clone → edit code → run .\infra\deploy.ps1
      │
      ▼
AWS ECS Fargate (already running)
  ├── API  → http://<ALB_DNS>/docs
  └── Web  → http://<ALB_DNS>
```

The existing AWS infrastructure (ECS, RDS, Redis, S3, ECR) is already provisioned
via Terraform. You just build Docker images, push them to ECR, and force a new
ECS deployment.

---

## Part 1 — One-Time Prerequisites

Install these tools once. Skip any you already have.

### 1.1 — Git

1. Download: https://git-scm.com/download/win
2. Run installer — accept all defaults
3. Verify:
   ```powershell
   git --version
   ```

---

### 1.2 — VS Code (Code Editor)

1. Download: https://code.visualstudio.com/
2. Run installer
3. Recommended extensions (install from VS Code's Extensions panel):
   - **Python** (ms-python.python)
   - **ESLint** (dbaeumer.vscode-eslint)
   - **Prettier** (esbenp.prettier-vscode)

---

### 1.3 — AWS CLI

1. Download: https://awscli.amazonaws.com/AWSCLIV2.msi
2. Run the installer
3. Verify:
   ```powershell
   aws --version
   ```

---

### 1.4 — Docker Desktop

Docker Desktop is used to **build** the images locally before pushing to AWS ECR.
You do NOT need to run any containers locally for development.

1. Download: https://www.docker.com/products/docker-desktop/
2. Run installer — enable **WSL 2 backend** when prompted
3. After install, **launch Docker Desktop** from the Start Menu
4. Wait for the whale icon in the taskbar to show **"Docker Desktop is running"**
5. Verify:
   ```powershell
   docker --version
   ```

> ⚠️ Docker Desktop must be **running** every time you deploy. If it's not
> running, the `docker build` step will fail.

---

### 1.5 — Python 3

Needed by the deploy script to manipulate ECS task definition JSON.

1. Download: https://www.python.org/downloads/ (Python 3.11 or later)
2. During install, **tick "Add python.exe to PATH"**
3. Verify:
   ```powershell
   python --version
   ```

---

## Part 2 — Configure AWS Credentials

You need AWS credentials with permissions to push to ECR and update ECS.

Ask the project owner for an **IAM Access Key** (Access Key ID + Secret Access Key).

```powershell
aws configure
```

You'll be prompted for:
```
AWS Access Key ID:     <paste your Access Key ID>
AWS Secret Access Key: <paste your Secret Access Key>
Default region name:   ap-south-1
Default output format: json
```

Verify it works:
```powershell
aws sts get-caller-identity
```

You should see your account ID and user ARN. If you see an error, your credentials
are wrong — double-check with the project owner.

---

## Part 3 — Clone the Repository

```powershell
# Go to your preferred folder
cd C:\Projects   # create this folder first if it doesn't exist: mkdir C:\Projects

# Clone
git clone https://github.com/RathlavathArun/Bank_statement_scanner.git

# Enter the project
cd Bank_statement_scanner

# Open in VS Code
code .
```

---

## Part 4 — Understand the Project Structure

```
Bank_statement_scanner/
├── apps/
│   ├── api/          ← Python FastAPI backend (port 8000 on AWS)
│   │   ├── main.py
│   │   ├── statements/
│   │   │   ├── router.py       ← API endpoints
│   │   │   ├── parser.py       ← PDF/Excel parsing logic
│   │   │   └── ocr_worker.py   ← OCR for scanned PDFs
│   │   ├── auth/               ← Login/signup logic
│   │   └── db/                 ← Database models
│   │
│   └── web/          ← Next.js frontend (port 3000 on AWS)
│       └── src/app/
│           ├── dashboard/page.tsx   ← Main dashboard
│           ├── login/page.tsx       ← Login page
│           └── signup/page.tsx      ← Signup page
│
├── packages/
│   └── bank-templates/   ← YAML configs for each bank (HDFC, ICICI, etc.)
│
├── infra/
│   ├── deploy.ps1        ← 🪟 Windows: deploy BOTH API + Web
│   ├── deploy.sh         ← 🍎 macOS/Linux: deploy BOTH API + Web
│   └── terraform/        ← AWS infrastructure (already provisioned, don't touch)
│
└── deploy_api.ps1        ← 🪟 Windows: deploy API only (faster)
```

---

## Part 5 — Make a Code Change

Edit whatever you need. Here are the most common files:

| What you want to change | File to edit |
|------------------------|--------------|
| API endpoint logic | `apps/api/statements/router.py` |
| PDF parsing | `apps/api/statements/parser.py` |
| Dashboard UI | `apps/web/src/app/dashboard/page.tsx` |
| Login / Signup page | `apps/web/src/app/login/page.tsx` |
| Bank template (HDFC etc) | `packages/bank-templates/hdfc.yaml` |

**Example**: Add a comment to confirm your change works end-to-end:

Open `apps/api/main.py` in VS Code and change the root response:
```python
@app.get("/", tags=["System"])
async def root():
    return ApiResponse.ok(
        data={
            "service": "Bank Statement Extraction API",
            "version": "0.1.0",
            "docs": "/docs",
            "deployed_by": "Windows Dev - your name here",  # ← add this
        }
    )
```

Save the file (`Ctrl + S`).

---

## Part 6 — Deploy to AWS

Open **PowerShell** from the repo root folder.

> Make sure **Docker Desktop is running** before this step.

### Option A — Deploy Everything (API + Web)

Use this when you've changed both the frontend and backend, or aren't sure:

```powershell
.\infra\deploy.ps1
```

This runs through 6 steps:
1. Checks AWS credentials and Docker
2. Logs in to AWS ECR (Docker registry)
3. Builds the API Docker image and pushes it
4. Builds the Web Docker image and pushes it
5. Registers new ECS task definitions
6. Forces new ECS deployments + waits for them to go stable

**Total time**: ~8–12 minutes

---

### Option B — Deploy API Only (Faster)

Use this when you've only changed backend code (`apps/api/`):

```powershell
.\deploy_api.ps1
```

**Total time**: ~4–6 minutes

---

### What the output looks like

```
[DEPLOY] Pre-flight checks...
[  OK  ] All tools found. AWS Account: 911229172121
[DEPLOY] --- Step 3/6: ECR Docker Login ---
[  OK  ] Logged in to ECR
[DEPLOY] --- Step 4/6: Build & Push API Image ---
[DEPLOY] Building API image (tag: 20260613-101523)...
 => [1/5] FROM python:3.12-slim
 => [2/5] RUN apt-get install tesseract-ocr poppler-utils ...
 => [3/5] COPY requirements.txt .
 => [4/5] RUN pip install -r requirements.txt
 => [5/5] COPY . .
[  OK  ] API image pushed
[DEPLOY] --- Step 6/6: Deploy to ECS ---
[DEPLOY] Waiting for ECS services to stabilize...
[  OK  ] ECS services are stable
================================================================
  Deployment Complete!
================================================================
  Web App:    http://bank-statement-alb-xxxxxxx.ap-south-1.elb.amazonaws.com
  API Health: http://bank-statement-alb-xxxxxxx.ap-south-1.elb.amazonaws.com/health
  API Docs:   http://bank-statement-alb-xxxxxxx.ap-south-1.elb.amazonaws.com/docs
  Image Tag:  20260613-101523
```

Copy the **Web App** URL — that's your live deployment.

---

## Part 7 — Verify Your Change is Live

### Check the API
Open in your browser:
```
http://<ALB_DNS>/health        → should return {"status": "healthy"}
http://<ALB_DNS>/docs          → Swagger UI with all endpoints
http://<ALB_DNS>/              → root response (has your "deployed_by" field)
```

### Check the Web App
Open in your browser:
```
http://<ALB_DNS>
```
Log in with your account credentials. Your UI changes will be visible here.

### Find the ALB URL any time
If you missed it from the deploy output, run:
```powershell
aws elbv2 describe-load-balancers `
    --query "LoadBalancers[0].DNSName" `
    --output text `
    --region ap-south-1
```

---

## Part 8 — Pull the Latest Code (Daily Workflow)

When someone else pushes changes and you want to get them:

```powershell
cd C:\Projects\Bank_statement_scanner

# Pull the latest
git pull origin main

# Make your changes, then deploy
.\infra\deploy.ps1
```

---

## Quick Reference

```powershell
# Get latest code
git pull origin main

# Make changes in VS Code
code .

# Deploy everything
.\infra\deploy.ps1

# Deploy API only (faster)
.\deploy_api.ps1

# Check live URL
aws elbv2 describe-load-balancers --query "LoadBalancers[0].DNSName" --output text --region ap-south-1
```

---

## Troubleshooting

### `docker: command not found` or Docker errors
Docker Desktop is not running. Open Docker Desktop from the Start Menu and wait
for the whale icon to show "Docker Desktop is running", then re-run the deploy.

### `aws: command not found`
AWS CLI is not installed or not on PATH. Reinstall from
https://awscli.amazonaws.com/AWSCLIV2.msi and restart PowerShell.

### `Unable to locate credentials`
Run `aws configure` and enter your Access Key ID and Secret Access Key.

### `Error: denied: Your authorization token has expired`
Re-run the deploy script. It refreshes the ECR login automatically at the start.

### ECS deployment times out
The deploy script waits up to 10 minutes for services to stabilize.
If it times out, check the AWS Console:
- Go to **ECS → Clusters → bank-statement-cluster**
- Click the service → **Events** tab to see what's wrong
- Check **CloudWatch Logs** under `/ecs/bank-statement` for container errors

### Changes not showing after deploy
- ECS caches the old task. Wait 2–3 minutes after "Deployment Complete" for
  the ALB to route to the new containers.
- Hard-refresh the browser (`Ctrl + Shift + R`).

### `python: command not found` in deploy script
Python is not on PATH. Reinstall Python and tick **"Add to PATH"** during install.
Then restart PowerShell.
