PRODUCT REQUIREMENTS DOCUMENT
Bank Statement Extraction & Conversion Engine
AI-Powered PDF/Excel to Structured Ledger Data Pipeline
Version 1.0
Status: Ready for Implementation
Target: AI Coding Agent Build
Document Date: May 2026
1. Executive Summary
This document specifies a Bank Statement Extraction feature modeled on Vyapar TaxOne (formerly Suvit). The product converts bank statements (PDF, Excel, images, scanned documents) into structured, categorized transaction data that can be reviewed, edited, and exported as Tally-compatible vouchers or generic ledger entries.
1.1 Problem Statement
Chartered Accountants and accounting teams spend 40 to 60 percent of their workday manually transcribing bank statements into accounting software.
Each Indian bank uses a different PDF layout (HDFC, ICICI, SBI, Axis, Kotak, Yes Bank, IDFC, IndusInd, RBL, etc.), making generic parsers unreliable.
Manual entry produces a 5 to 15 percent error rate in ledger tagging, which propagates into GST reconciliation and audit issues.
Existing OCR tools extract text but do not understand accounting semantics (debit/credit, narration parsing, counterparty identification, ledger mapping).
1.2 Solution Overview
A multi-stage extraction pipeline that combines deterministic PDF parsing, OCR fallback for scanned documents, and an LLM-based reasoning layer for narration categorization and ledger mapping. The system learns from user corrections to improve auto-mapping accuracy over time.
1.3 Success Metrics
Metric
Target
Measurement Method
Extraction accuracy (row level)
>= 98%
Random audit of 500 transactions/week
Auto-categorization accuracy
>= 85% by month 3
User edit rate per session
Average processing time
< 30s for 100-page statement
P95 latency dashboard
Manual entry time saved
>= 80%
Time-on-task user studies
Supported banks at GA
>= 30 Indian banks
Coverage test suite
Monthly active CA firms
500 by month 6
Product analytics

2. Scope
2.1 In Scope (V1)
Upload of bank statements in PDF (text-based and scanned), Excel (.xlsx, .xls), CSV, and image formats (JPG, PNG).
Automatic detection of bank, account number, statement period, opening/closing balance.
Transaction extraction: date, narration, reference number, debit, credit, running balance.
AI-powered narration parsing to identify counterparty, transaction type (UPI, NEFT, RTGS, IMPS, cheque, cash, charges, interest).
Smart ledger suggestion based on past mappings and global patterns.
In-product review UI with side-by-side PDF preview and editable transaction grid.
Bulk export to Tally XML, Excel, JSON, and CSV.
Per-client transaction history and ledger memory.
Role-based access (firm owner, team member, view-only).
2.2 Out of Scope (V1)
Direct bank API/account aggregator integration (planned V2).
Multi-currency statements (V2).
Credit card statement support beyond bank statements (V2).
GST reconciliation (separate module).
Loan and EMI schedules (V2).
3. Target Users & Personas
Persona 1: Practicing Chartered Accountant (Primary)
Solo or small-firm CA handling 50 to 300 client books.
Pain: Hours wasted on bank statement entry per client per month.
Goal: Push reviewed transactions into Tally in one click.
Persona 2: Articled Clerk / Junior Accountant
Does the actual data entry under CA supervision.
Pain: Repetitive typing, errors get blamed on them.
Goal: Finish month-end work in 1 day instead of 5.
Persona 3: SME Business Owner
Maintains own books in Tally or Excel.
Pain: Cannot afford full-time accountant for transaction entry.
Goal: Self-serve bank statement upload with auto-categorization.
4. User Journeys
4.1 Primary Flow: Upload, Extract, Review, Export
User logs in and selects a client from the client list (or creates a new one).
User clicks "Upload Bank Statement" and drags a PDF or selects from device.
System detects bank, displays a confirmation chip: "HDFC Bank, A/C XXXX1234, Apr 1 to Apr 30 2026".
User confirms or corrects detected metadata.
Background job extracts transactions. Progress bar shows pages parsed.
On completion, user lands on a review screen: PDF preview on left, editable table on right.
Each row shows AI-suggested ledger with a confidence score. Low-confidence rows highlighted yellow.
User edits ledger mappings inline. Bulk-edit by selecting multiple similar rows.
User clicks "Push to Tally" or "Export as Excel". A Tally XML or .xlsx file is generated and synced.
System stores the mappings to improve future suggestions for this client.
4.2 Edge Case Flow: Scanned/Image PDF
User uploads a scanned PDF (image-based).
System detects no extractable text layer and routes to OCR pipeline.
User sees "OCR in progress" with estimated time.
Extracted rows show OCR confidence; rows below 80 percent confidence flagged red.
User reviews flagged rows against the PDF preview and corrects them before export.
5. Functional Requirements
5.1 File Ingestion Module
ID
Requirement
Priority
FR-1.1
Accept PDF, XLSX, XLS, CSV, JPG, PNG. Max file size 50 MB.
P0
FR-1.2
Validate file type by magic bytes, not extension.
P0
FR-1.3
Detect password-protected PDFs and prompt user for password.
P0
FR-1.4
Virus scan via ClamAV before processing.
P0
FR-1.5
Support multi-file upload (up to 10 statements at once).
P1
FR-1.6
Auto-stitch multi-part statements for the same account and period.
P2

5.2 Bank Detection & Template Matching
ID
Requirement
Priority
FR-2.1
Auto-detect bank from logo, header text, IFSC, or watermark.
P0
FR-2.2
Maintain bank template library for at least 30 Indian banks at GA.
P0
FR-2.3
Extract account number, IFSC, account holder name, statement period.
P0
FR-2.4
Extract opening and closing balance, validate sum of transactions matches.
P0
FR-2.5
Fall back to generic parser when template not found, flag to user.
P0
FR-2.6
Allow admin to add new bank templates without code deploy.
P1

5.3 Transaction Extraction
ID
Requirement
Priority
FR-3.1
Extract every transaction row with: date, narration, ref no, debit, credit, balance.
P0
FR-3.2
Handle multi-line narrations (common in HDFC, ICICI).
P0
FR-3.3
Detect and discard headers, footers, page numbers, sub-totals.
P0
FR-3.4
Use OCR (Tesseract or AWS Textract) for scanned PDFs, with confidence per cell.
P0
FR-3.5
Validate balance arithmetic: prev_balance +/- amount = current_balance.
P0
FR-3.6
Flag rows that fail balance check for user review.
P0

5.4 AI Categorization & Ledger Mapping
ID
Requirement
Priority
FR-4.1
Parse narration to identify: counterparty name, payment mode, reference.
P0
FR-4.2
Suggest ledger using (a) client-specific history, (b) firm-wide patterns, (c) global LLM.
P0
FR-4.3
Return confidence score (0 to 1) for each suggestion.
P0
FR-4.4
Learn from user edits, update mapping memory for the client.
P0
FR-4.5
Detect recurring transactions (rent, salary, EMI) and pre-fill.
P1
FR-4.6
Support custom rules: "if narration contains X then ledger Y".
P1

5.5 Review & Edit UI
ID
Requirement
Priority
FR-5.1
Side-by-side: PDF preview (left) and transaction grid (right).
P0
FR-5.2
Clicking a transaction row scrolls PDF preview to source.
P0
FR-5.3
Inline editing of every field. Undo/redo support.
P0
FR-5.4
Bulk-select and bulk-update ledger mapping.
P0
FR-5.5
Filter by: amount range, date range, ledger, confidence level.
P0
FR-5.6
Mark rows as "ignore" (exclude from export).
P1

5.6 Export & Integration
ID
Requirement
Priority
FR-6.1
Export as Tally XML (Day Book Voucher format).
P0
FR-6.2
Export as Excel with configurable column mapping.
P0
FR-6.3
Export as CSV and JSON.
P0
FR-6.4
Direct push to Tally via Tally HTTP/ODBC connector.
P1
FR-6.5
Push to Zoho Books, QuickBooks, Vyapar via API connectors.
P2
FR-6.6
Idempotent exports: re-export does not duplicate.
P0

6. System Architecture
6.1 High-Level Architecture
The system follows a microservices pattern with an API gateway, separate ingestion and processing workers, a primary relational store, blob storage for documents, and a vector store for narration-similarity search.
Architecture Diagram (Text Representation)
+--------------------------------------------------------------+
|                       CLIENT (Browser)                       |
|         Next.js 14 (App Router) + React + TypeScript         |
+----------------------------+---------------------------------+
                             |
                             v  HTTPS / JWT
+--------------------------------------------------------------+
|                    API GATEWAY (Nginx + JWT)                 |
+----------------------------+---------------------------------+
                             |
          +------------------+------------------+
          v                  v                  v
  +---------------+  +---------------+  +---------------+
  |  Auth Svc     |  | Statement API |  | Export Svc    |
  | (FastAPI)     |  |  (FastAPI)    |  | (FastAPI)     |
  +-------+-------+  +-------+-------+  +-------+-------+
          |                  |                  |
          v                  v                  v
  +----------------------------------------------------+
  |   PostgreSQL 16  |  Redis 7  |  S3/MinIO Storage   |
  +----------------------------------------------------+
                             |
                             v   Job queued in Redis (BullMQ / Celery)
  +----------------------------------------------------+
  |              WORKER POOL (Celery + Python)         |
  |  +----------+ +----------+ +----------+ +--------+ |
  |  | Parser   | | OCR      | | LLM      | | Export | |
  |  | (pdf-    | | (Tessract| | (Claude/ | | Worker | |
  |  | plumber) | | + Textr) | | GPT-4o)  | |        | |
  |  +----------+ +----------+ +----------+ +--------+ |
  +-------+-----------+----------+-----------+--------+
          |           |          |           |
          v           v          v           v
  +----------------------------------------------------+
  |    Vector DB (Qdrant) for narration similarity     |
  +----------------------------------------------------+

6.2 Component Responsibilities
Component
Responsibility
Web Client
File upload, review UI, export controls, client management.
API Gateway
Routing, rate-limiting, JWT validation, request logging.
Auth Service
Signup/login, OTP, JWT issuance, RBAC for firms and teams.
Statement API
CRUD on statements/transactions, triggers worker jobs, serves results.
Parser Worker
Bank detection, PDF text extraction (pdfplumber, Camelot), table normalization.
OCR Worker
Scanned PDF processing (Tesseract for cost, Textract for accuracy).
LLM Worker
Narration parsing, ledger suggestion, confidence scoring.
Export Worker
Tally XML, Excel, CSV, JSON generation; pushes to integrations.
PostgreSQL
Structured data: users, firms, clients, statements, transactions, ledgers.
Redis
Job queue, session cache, rate-limit counters.
S3 / MinIO
Original PDF/Excel files, exported artifacts.
Qdrant
Vector embeddings of narrations for similarity-based mapping.

6.3 Data Flow
Client uploads file to POST /v1/statements/upload (multipart). File saved to S3, statement record created in DB with status=UPLOADED.
Statement API enqueues parse_statement job to Redis.
Parser Worker downloads from S3, runs bank detection, attempts text extraction. If scanned, hands off to OCR Worker.
Parser Worker writes raw transactions to DB with status=EXTRACTED.
LLM Worker is enqueued. Pulls transactions, runs categorization in batches of 50, writes back with confidence scores. Status moves to READY_FOR_REVIEW.
Frontend polls or subscribes via WebSocket for status updates. Once READY_FOR_REVIEW, the review UI loads.
User edits and clicks Export. Export Worker generates the requested format, uploads to S3, returns signed URL. Status becomes EXPORTED.
7. Tech Stack
7.1 Frontend
Layer
Choice
Rationale
Framework
Next.js 14 (App Router)
SSR for SEO landing, RSC for fast data fetching.
Language
TypeScript 5
Type safety across full stack.
UI Library
shadcn/ui + Radix
Accessible, customizable, modern.
Styling
Tailwind CSS 3
Utility-first, fast iteration.
State
Zustand + TanStack Query
Local state + server cache.
Forms
React Hook Form + Zod
Validated, performant forms.
Table grid
TanStack Table v8 + AG Grid Community
Virtualized rows for 10k+ transactions.
PDF preview
react-pdf (pdfjs-dist)
Native rendering, page-by-page.
File upload
Uppy + tus
Resumable uploads for large PDFs.

7.2 Backend
Layer
Choice
Rationale
API Framework
FastAPI (Python 3.12)
Async, OpenAPI auto-docs, Pydantic validation.
Workers
Celery + Redis broker
Mature, well-supported, retries built-in.
ORM
SQLAlchemy 2 + Alembic
Migrations, async support.
Auth
JWT + Argon2id
Stateless, secure password hashing.
API Docs
OpenAPI 3.1 (auto from FastAPI)
Contract-first, generated SDKs.
Validation
Pydantic v2
Fast, declarative schemas.

7.3 Data Layer
Service
Choice
Purpose
Primary DB
PostgreSQL 16
Relational data, ACID, JSONB for flexible fields.
Cache / Queue
Redis 7
Session, rate limit, Celery broker.
Object Storage
AWS S3 (or MinIO self-hosted)
PDFs, exports, audit copies.
Vector Store
Qdrant
Narration similarity search for ledger mapping.
Search
PostgreSQL full-text (pg_trgm)
Transaction search, no separate Elastic.
Analytics
ClickHouse (optional V2)
Aggregation across millions of transactions.

7.4 ML / AI Stack
Capability
Choice
Purpose
PDF text extraction
pdfplumber, Camelot, PyMuPDF
Layout-aware table extraction.
OCR (cheap)
Tesseract 5 + OpenCV preprocessing
Bulk scanned PDFs, low cost.
OCR (accurate)
AWS Textract / Azure Document Intelligence
Premium tier, high accuracy on poor scans.
LLM (categorization)
Claude Sonnet 4.5 (Anthropic API) - primary; GPT-4o-mini - fallback
Narration parsing, ledger suggestion.
Embeddings
OpenAI text-embedding-3-small or BGE-large
Vector store for similar narrations.
Rule engine
Custom (Python) with YAML rules
Deterministic overrides per firm.

7.5 Infrastructure & DevOps
Layer
Choice
Purpose
Container
Docker + Docker Compose (dev), Kubernetes (prod)
Portability, scaling.
Cloud
AWS (preferred) or GCP
EKS, RDS, S3, ElastiCache.
IaC
Terraform + Helm charts
Reproducible infra.
CI/CD
GitHub Actions + ArgoCD
Test, build, deploy on PR merge.
Monitoring
Prometheus + Grafana + Loki
Metrics, logs, alerts.
Error tracking
Sentry
Production exceptions.
APM
OpenTelemetry + Jaeger
Distributed tracing.
Secrets
AWS Secrets Manager / HashiCorp Vault
API keys, DB creds.

8. Data Model
Core relational entities. Field types shown for PostgreSQL.
8.1 Entity-Relationship Overview
User --< FirmMember >-- Firm --< Client --< Statement --< Transaction
                                                              |
                                                              v
                                                         LedgerMapping
                                                              ^
                                                              |
                                                          Ledger

8.2 Table: firms
id              UUID         PRIMARY KEY
name            VARCHAR(255) NOT NULL
gstin           VARCHAR(15)
subscription    VARCHAR(50)  NOT NULL DEFAULT 'free'
created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()

8.3 Table: users
id              UUID         PRIMARY KEY
email           VARCHAR(255) UNIQUE NOT NULL
phone           VARCHAR(15)  UNIQUE
password_hash   VARCHAR(255) NOT NULL
full_name       VARCHAR(255)
email_verified  BOOLEAN      NOT NULL DEFAULT false
created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()

8.4 Table: firm_members
id              UUID         PRIMARY KEY
firm_id         UUID         REFERENCES firms(id) ON DELETE CASCADE
user_id         UUID         REFERENCES users(id) ON DELETE CASCADE
role            VARCHAR(50)  NOT NULL  -- owner | admin | member | viewer
UNIQUE(firm_id, user_id)

8.5 Table: clients
id              UUID         PRIMARY KEY
firm_id         UUID         REFERENCES firms(id) ON DELETE CASCADE
name            VARCHAR(255) NOT NULL
gstin           VARCHAR(15)
pan             VARCHAR(10)
metadata        JSONB        NOT NULL DEFAULT '{}'
created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()

8.6 Table: statements
id              UUID         PRIMARY KEY
client_id       UUID         REFERENCES clients(id) ON DELETE CASCADE
uploaded_by     UUID         REFERENCES users(id)
file_url        TEXT         NOT NULL  -- S3 key
file_type       VARCHAR(20)  NOT NULL
bank_code       VARCHAR(50)  -- e.g., HDFC, ICICI, SBI
account_number  VARCHAR(50)
account_holder  VARCHAR(255)
period_start    DATE
period_end      DATE
opening_balance NUMERIC(18,2)
closing_balance NUMERIC(18,2)
status          VARCHAR(30)  NOT NULL  -- UPLOADED | PARSING | OCR |
                              --       READY_FOR_REVIEW | EXPORTED | FAILED
error_message   TEXT
metadata        JSONB        NOT NULL DEFAULT '{}'
created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()

8.7 Table: transactions
id                UUID         PRIMARY KEY
statement_id      UUID         REFERENCES statements(id) ON DELETE CASCADE
row_number        INT          NOT NULL
txn_date          DATE         NOT NULL
value_date        DATE
narration         TEXT         NOT NULL
narration_clean   TEXT         -- LLM-cleaned version
reference_no      VARCHAR(100)
debit             NUMERIC(18,2)
credit            NUMERIC(18,2)
balance           NUMERIC(18,2)
payment_mode      VARCHAR(20)  -- UPI | NEFT | RTGS | IMPS | CHEQUE | CASH
counterparty      VARCHAR(255)
suggested_ledger  VARCHAR(255)
confirmed_ledger  VARCHAR(255)
confidence        NUMERIC(4,3) -- 0.000 to 1.000
is_ignored        BOOLEAN      NOT NULL DEFAULT false
ocr_confidence    NUMERIC(4,3)
page_number       INT
bbox              JSONB        -- bounding box for PDF preview
created_at        TIMESTAMPTZ  NOT NULL DEFAULT now()

8.8 Table: ledger_mappings (learning memory)
id              UUID         PRIMARY KEY
client_id       UUID         REFERENCES clients(id) ON DELETE CASCADE
pattern         TEXT         NOT NULL  -- narration substring or regex
ledger_name     VARCHAR(255) NOT NULL
hit_count       INT          NOT NULL DEFAULT 1
last_used_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
created_by      UUID         REFERENCES users(id)
UNIQUE(client_id, pattern)

8.9 Table: ledgers
id              UUID         PRIMARY KEY
client_id       UUID         REFERENCES clients(id) ON DELETE CASCADE
name            VARCHAR(255) NOT NULL
group_name      VARCHAR(255) NOT NULL  -- Tally group: Sundry Creditors, etc.
tally_id        VARCHAR(100) -- external Tally GUID if synced
UNIQUE(client_id, name)

8.10 Indexes
CREATE INDEX idx_txn_statement      ON transactions(statement_id);
CREATE INDEX idx_txn_date           ON transactions(txn_date);
CREATE INDEX idx_txn_narration_trgm ON transactions USING gin (narration gin_trgm_ops);
CREATE INDEX idx_stmt_client_status ON statements(client_id, status);
CREATE INDEX idx_ledger_map_client  ON ledger_mappings(client_id, pattern);

9. API Specification
All endpoints are versioned under /v1. Authentication via Bearer JWT. Responses are JSON with consistent envelope.
9.1 Standard Response Envelope
{
  "success": true,
  "data": { ... },
  "error": null,
  "meta": { "request_id": "...", "timestamp": "..." }
}

9.2 Authentication
POST /v1/auth/signup          -> { email, phone, password, full_name }
POST /v1/auth/login           -> { email, password }   returns access_token + refresh_token
POST /v1/auth/refresh         -> { refresh_token }
POST /v1/auth/otp/send        -> { phone }
POST /v1/auth/otp/verify      -> { phone, otp }

9.3 Clients
GET    /v1/clients                   List clients in firm
POST   /v1/clients                   Create client
GET    /v1/clients/{id}              Get client
PATCH  /v1/clients/{id}              Update client
DELETE /v1/clients/{id}              Soft delete

9.4 Statements (Core)
POST   /v1/clients/{client_id}/statements/upload
       multipart/form-data: file, optional password
       returns { statement_id, status }
 
GET    /v1/statements/{id}
       returns metadata + status + counts
 
GET    /v1/statements/{id}/transactions
       query: page, page_size, filter, sort
       returns paginated transactions
 
PATCH  /v1/statements/{id}/transactions/{txn_id}
       body: { confirmed_ledger, narration_clean, is_ignored }
 
POST   /v1/statements/{id}/transactions/bulk-update
       body: { ids: [...], updates: { confirmed_ledger: '...' } }
 
DELETE /v1/statements/{id}                Hard delete (with audit log)

9.5 Export
POST   /v1/statements/{id}/export
       body: { format: 'tally_xml' | 'excel' | 'csv' | 'json', options: {...} }
       returns { export_id, status, download_url (when ready) }
 
GET    /v1/exports/{id}                 Status + download URL
POST   /v1/statements/{id}/push-to-tally  Direct sync if connector enabled

9.6 Real-time Updates
WS  /v1/ws/statements/{id}
    Server pushes: { event: 'status_changed', status, progress_percent }

10. Extraction Pipeline (Detailed)
10.1 Stage 1: Pre-processing
Magic-byte validation of file type.
If PDF: check for text layer using pdfminer. If text layer exists, route to Stage 2a. Otherwise route to Stage 2b (OCR).
If Excel: route to Stage 2c.
If image: route to Stage 2b (OCR).
Decrypt password-protected PDFs using pikepdf if password provided.
10.2 Stage 2a: Text-Based PDF Extraction
Use pdfplumber to extract text and table structure per page.
Detect bank via fingerprint: presence of bank name in header, IFSC pattern, logo image hash.
Load bank-specific template (column positions, header rows to skip, balance column position).
If no template matches, run heuristic table detection using Camelot lattice and stream modes.
Normalize date formats: DD/MM/YYYY, DD-MMM-YYYY, YYYY-MM-DD all map to ISO 8601.
Parse amounts handling Indian number format (1,00,000.00) and Cr/Dr suffixes.
10.3 Stage 2b: OCR Pipeline
Pre-process image: deskew (OpenCV), denoise, increase contrast, binarize.
Run Tesseract with --psm 6 (single uniform block) and Indian language data if needed.
If overall confidence < 70 percent or premium tier, fall back to AWS Textract AnalyzeDocument with TABLES feature.
Map Textract table output to transaction schema.
Persist per-cell OCR confidence so the UI can highlight low-confidence cells.
10.4 Stage 2c: Excel Extraction
Use openpyxl for .xlsx, xlrd for .xls.
Detect header row by looking for known headers: Date, Narration, Description, Debit, Credit, Balance, Withdrawal, Deposit.
Auto-map columns even if order differs.
Handle merged cells and multi-sheet workbooks.
10.5 Stage 3: Validation
Balance arithmetic: for each row, verify previous balance +/- amount = current balance. Tolerance 0.01 INR.
Date monotonicity: transactions should be in chronological order.
Sum check: opening balance + sum(credits) - sum(debits) = closing balance.
Duplicate detection: identical date + amount + narration + ref no flagged.
Failures attached to transactions as validation_warnings JSONB for UI to surface.
10.6 Stage 4: LLM Categorization
Batched calls to Claude Sonnet 4.5 (primary) with structured output schema. 50 transactions per call, max 4 concurrent calls per statement.
Prompt Template (Pseudocode)
System: You are an Indian accountant. For each bank transaction,
        identify the counterparty, payment mode, and suggest a Tally
        ledger from the provided ledger list. Return JSON.
 
User:   ledgers: ["Sundry Creditors", "Salaries", "Rent", ...]
        client_history: [
          { narration: "UPI/SWIGGY/...", ledger: "Staff Welfare" },
          ...
        ]
        transactions: [
          { id: 1, narration: "NEFT-CR-HDFC0000123-ACME PVT LTD-...",
            debit: null, credit: 50000 },
          ...
        ]
 
Output: [
  { id: 1, counterparty: "Acme Pvt Ltd", payment_mode: "NEFT",
    suggested_ledger: "Sundry Debtors - Acme", confidence: 0.92 },
  ...
]

10.7 Stage 5: Mapping Memory Update
On user confirmation/edit, extract narration pattern (first 30 chars or key tokens).
Upsert into ledger_mappings with incremented hit_count.
Generate embedding of narration_clean, store in Qdrant with payload {client_id, ledger}.
Next batch first queries Qdrant for top-5 similar narrations, includes them in LLM prompt as few-shot examples.
11. Security & Compliance
11.1 Data Security
All data in transit over TLS 1.3.
At-rest encryption: AES-256 for S3 (SSE-KMS), AES-256 for RDS.
PDFs deleted from S3 after 90 days unless user pins; signed URLs expire in 15 minutes.
Account numbers masked in UI (XXXX1234) unless user clicks reveal.
Password storage: Argon2id, never plaintext.
11.2 Authentication & Authorization
JWT access tokens (15 min) + refresh tokens (7 days, rotating).
RBAC at firm level: owner, admin, member, viewer.
Row-level security: every query scoped to firm_id from JWT.
MFA via TOTP or SMS OTP for admin actions.
11.3 Audit & Compliance
Immutable audit log of every read/write on statements and transactions (append-only table).
DPDP Act 2023 compliance: data residency in India, user consent flow, right to erasure within 30 days.
SOC 2 Type II readiness: access reviews, change management, incident response runbook.
ISO 27001 alignment for enterprise tier.
11.4 LLM Safety
Prompts never include PII beyond what is necessary (mask account numbers before sending to LLM).
Use API providers with zero-retention agreements (Anthropic ZDR, OpenAI Enterprise).
Cache LLM outputs by content hash to reduce cost and exposure.
12. Non-Functional Requirements
Category
Requirement
Availability
99.5% monthly uptime SLA (V1), 99.9% (V2 enterprise).
Latency (P95)
Upload to extraction start: < 2 seconds. 100-page PDF end-to-end: < 30 seconds.
Throughput
1000 concurrent uploads, 50000 statements/day.
Scalability
Horizontal scaling on workers, partition tables by firm_id.
Data retention
Transaction data 7 years (income tax law), original PDFs 90 days default.
Browser support
Latest 2 versions of Chrome, Edge, Firefox, Safari.
Mobile
Responsive web only in V1, native apps V2.
Localization
English at GA; Hindi, Gujarati, Tamil in V2.
Accessibility
WCAG 2.1 AA for review UI.

13. Roadmap & Milestones
Phase
Timeline
Deliverables
M0 - Foundation
Weeks 1-3
Repo setup, CI/CD, auth, DB schema, basic UI shell.
M1 - MVP Extraction
Weeks 4-7
PDF upload, parsing for top 5 banks (HDFC, ICICI, SBI, Axis, Kotak), review UI.
M2 - AI Layer
Weeks 8-10
LLM categorization, mapping memory, confidence scores.
M3 - OCR + Excel
Weeks 11-13
Scanned PDF support, Excel/CSV ingestion.
M4 - Export
Weeks 14-15
Tally XML, Excel, CSV exports.
M5 - Polish & Beta
Weeks 16-18
Closed beta with 20 CA firms, NPS targeting.
M6 - GA Launch
Weeks 19-20
30+ banks supported, pricing live, marketing site.
V2 (Post-GA)
Months 6-9
Tally direct push, Zoho/QB connectors, mobile app, multi-currency.

14. Risks & Mitigations
Risk
Impact
Mitigation
Bank PDF format changes silently
High
Automated regression test suite per bank, alerting on extraction failures > 5%.
LLM API outage
High
Multi-provider fallback (Claude -> GPT-4o -> rule-based).
OCR accuracy poor on low-quality scans
Medium
Premium tier with Textract; user-facing confidence indicators.
DPDP compliance gaps
High
Legal review pre-launch; data residency in Mumbai (ap-south-1).
Tally export format edge cases
Medium
Round-trip testing with sample company files; user-reported issue fast-track.
Cost of LLM calls at scale
Medium
Aggressive caching (narration hash), use cheaper model (Haiku) for high-confidence patterns.
Competition from incumbents
Medium
Faster iteration; deeper learning per client; better UX.
Hallucinated ledger names
Medium
Constrain LLM output to client's ledger list via function calling; reject novel names.

15. Acceptance Criteria for V1 GA
Successfully extract transactions from at least 30 distinct Indian bank PDF formats with row-level accuracy >= 98%.
Auto-categorization accuracy >= 80% on a curated test set of 5000 transactions across 10 industries.
End-to-end processing of a 100-page statement in under 30 seconds at P95.
Tally XML export validates against Tally Prime import without manual fixes for 95% of statements.
All P0 functional requirements (FR-*) implemented and verified by QA.
Security pen test passed; no high or critical findings open.
Documentation: user guide, API docs, runbooks for ops, all complete.
20 paid beta customers retained at 60-day mark.
16. Build Instructions for AI Coding Agent
This section is intended to be passed directly to an AI agent (Claude Code, Cursor, etc.) along with this PRD.
16.1 Repository Layout
bank-statement-extractor/
  apps/
    web/                 # Next.js frontend
    api/                 # FastAPI gateway
  workers/
    parser/              # PDF/Excel parsing worker
    ocr/                 # OCR worker
    llm/                 # LLM categorization worker
    exporter/            # Export generation worker
  packages/
    schemas/             # Shared Pydantic + Zod schemas
    bank-templates/      # YAML templates per bank
    tally-xml/           # Tally XML generator library
  infra/
    terraform/           # AWS infra
    helm/                # K8s manifests
    docker-compose.yml   # Local dev
  docs/
    api/                 # OpenAPI specs
    architecture/        # ADRs

16.2 Recommended Build Order
Phase A - Foundations: docker-compose with Postgres + Redis + MinIO + Qdrant. Alembic migrations for all tables in section 8. Auth service. Frontend shell with login.
Phase B - Upload pipeline: /v1/statements/upload endpoint. S3 upload. Parser worker for HDFC and ICICI only. Status polling.
Phase C - Review UI: PDF preview with react-pdf. Transaction grid with TanStack Table. Inline edit. Save to API.
Phase D - LLM layer: Claude API integration. Batched calls. Mapping memory upsert.
Phase E - Add banks: SBI, Axis, Kotak, then 25 more via YAML templates.
Phase F - OCR fallback: Tesseract worker, then Textract as premium.
Phase G - Export: Tally XML generator with golden-file tests. Excel export.
Phase H - Hardening: rate limits, audit logs, security review, load tests.
16.3 Critical Implementation Notes
Use UUIDv7 (sortable) for primary keys, not UUIDv4.
Every API endpoint must have an OpenAPI schema and a contract test.
All money fields are NUMERIC(18,2), never float.
Bank templates are YAML, hot-reloadable without redeploy.
LLM calls must use structured output (JSON mode) with Pydantic validation.
Workers should be idempotent; retries should not duplicate transactions.
Never log PII (account numbers, narrations) at INFO level; use DEBUG with redaction.
Frontend never receives raw PDF; always signed URLs from S3.
16.4 Definition of Done (per feature)
Unit tests with >= 80% line coverage.
Integration test exercising the API contract.
OpenAPI docs updated.
Migration scripts reviewed and reversible.
Logged metrics and alerts wired into Grafana.
PR description references the requirement ID (FR-X.Y) it implements.
Appendix A: Reference Inspiration
This product is modeled on Vyapar TaxOne (formerly Suvit), the AI accounting platform used by 10,000+ practicing firms and 30,000+ CAs in India. Their data entry automation converts bank statements, sales invoices, and purchase invoices into Tally-ready ledgers.
This PRD takes the bank-statement extraction subset of that platform and specifies it as a standalone, buildable system. It is not affiliated with Vyapar TaxOne; it draws on publicly described capabilities to define an analogous product.
Appendix B: Glossary
Term
Definition
Narration
The free-text description on a bank transaction (e.g., "NEFT-CR-...").
Ledger
An accounting head in Tally or similar (e.g., "Sundry Creditors").
Voucher
A Tally entry representing one or more transactions.
UPI/NEFT/RTGS/IMPS
Indian payment systems.
GSTIN
15-character GST identification number.
DPDP Act
Digital Personal Data Protection Act, 2023 (India).
Tally
Most widely used accounting software in Indian SME segment.
CA
Chartered Accountant.