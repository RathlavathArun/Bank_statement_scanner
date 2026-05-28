# Phase 1 Handoff README

This document explains what was completed in Phase 1, how to run and verify the current code, what remains for the next phase, and how to merge the pushed branch into `main`.

## Current Branch And PR

Phase 1 work is on:

```bash
phase1-upload-ui
```

Draft PR:

```text
https://github.com/RathlavathArun/Bank_statement_scanner/pull/1
```

Latest Phase 1 commit:

```text
37cf087 Complete phase 1 statement upload flow
```

## What Phase 1 Does

The app now supports a first upload-to-review flow:

1. User opens the dashboard.
2. User selects a bank chip: `HDFC`, `ICICI`, or `SBI`.
3. User uploads a statement file.
4. Frontend sends the file with `FormData`.
5. Backend saves the file locally in `apps/api/uploads`.
6. Backend creates a `Statement` row with a unique ID.
7. Backend parses supported files and saves rows into `Transaction`.
8. Frontend polls status by statement ID.
9. Frontend shows the statement in Recent Statements.
10. Frontend shows Extracted Transactions below Recent Statements.

## Important Files

```text
apps/api/statements/router.py
```

Defines:

- `POST /v1/statements/upload`
- `GET /v1/statements/{statement_id}/status`
- `GET /v1/statements/{statement_id}/result`

```text
apps/api/statements/parser.py
```

Parses CSV files and text-based PDFs into transaction rows. It uses bank templates from:

```text
packages/bank-templates/
```

```text
apps/api/tests/test_statements.py
```

Tests upload, status, result, and unsupported file handling.

```text
apps/web/src/app/dashboard/page.tsx
```

Contains the dashboard upload UI, Recent Statements list, polling logic, and Extracted Transactions table.

## Local Setup

From repo root:

```bash
cd /Users/gouthamnaroju/Desktop/ref/Bank_statement_scanner
```

Install backend dependencies:

```bash
cd apps/api
source venv/bin/activate
pip install -r requirements.txt
```

Start backend:

```bash
python main.py
```

Start frontend in another terminal:

```bash
cd /Users/gouthamnaroju/Desktop/ref/Bank_statement_scanner/apps/web
npm install
npm run dev
```

Open:

```text
http://localhost:3000/dashboard
```

## Manual Verification

Use the local sample file:

```text
sample-hdfc-statement.csv
```

Dashboard steps:

1. Log in.
2. Open dashboard.
3. Click `+ Upload Statement`.
4. Select `sample-hdfc-statement.csv`.
5. Select `HDFC`.
6. Click `Upload Statement`.

Expected:

- Recent Statements shows the uploaded file.
- Status becomes `READY_FOR_REVIEW`.
- Extracted Transactions appears below Recent Statements.
- Transactions match the CSV rows.

## Automated Verification

Backend tests:

```bash
cd /Users/gouthamnaroju/Desktop/ref/Bank_statement_scanner
apps/api/venv/bin/pytest apps/api/tests -q
```

Backend compile check:

```bash
apps/api/venv/bin/python -m compileall apps/api -q
```

Frontend lint:

```bash
cd apps/web
npm run lint
```

Note: lint currently reports two pre-existing warnings in login/signup about unused `err` variables.

Frontend build:

```bash
npm run build
```

## How To Merge The Branch

Recommended path: merge through GitHub.

1. Open the draft PR:

```text
https://github.com/RathlavathArun/Bank_statement_scanner/pull/1
```

2. Review the changed files and checks.
3. If everything looks good, click `Ready for review`.
4. Click `Merge pull request`.
5. After merging, update your local `main`:

```bash
cd /Users/gouthamnaroju/Desktop/ref/Bank_statement_scanner
git checkout main
git pull origin main
```

Alternative local merge:

```bash
cd /Users/gouthamnaroju/Desktop/ref/Bank_statement_scanner
git checkout main
git pull origin main
git merge phase1-upload-ui
git push origin main
```

Use the GitHub PR merge unless there is a specific reason to merge locally.

## Current Limitations

- Uploads are stored on local disk, not S3 or MinIO.
- Parser is synchronous inside the upload request.
- PDF parsing works only for text-based PDFs that expose extractable tables.
- XLS/XLSX parsing is not implemented yet.
- Dashboard does not yet reload statement history from the backend after page refresh.
- Uploads currently use a default client record instead of the authenticated user's real client context.

## Suggested Next Steps

1. Add `GET /v1/statements` to list persisted statements for the dashboard.
2. Connect uploads to authenticated user, firm, and selected client.
3. Add real client selection in the dashboard.
4. Improve parsers with real HDFC, ICICI, and SBI samples.
5. Add XLS/XLSX parsing.
6. Move parsing into a background worker.
7. Add transaction review/edit UI.
8. Store uploaded files in S3/MinIO.
