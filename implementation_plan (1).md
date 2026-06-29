# Migrate OCR from Local Tesseract → AWS Textract (Primary Engine)

## Background

The project currently picks its OCR engine via `get_ocr_engine()` in
[`ocr_worker.py`](file:///Users/gouthamnaroju/Desktop/ref/Bank_statement_scanner/apps/api/statements/ocr_worker.py).
The priority order today is:

1. **Tesseract** (local binary) — if `shutil.which('tesseract')` finds it → wins
2. **AWS Textract** — only used if Tesseract is absent AND valid AWS creds exist

The goal is to **invert this priority**: make AWS Textract the first-choice engine
and keep Tesseract as the graceful fallback (for local dev / offline use).

Additionally, the existing `TextractOCREngine` is a minimal synchronous wrapper
using only `analyze_document` (byte payload ≤ 10 MB). For production bank
statements this needs to be upgraded to support **async Textract jobs** (S3
upload → `start_document_analysis` → poll/SNS notify → retrieve results),
which handles files > 10 MB and is the recommended production pattern.

---

## User Review Required

> [!IMPORTANT]
> **Engine selection strategy** — choose one before implementation begins:
>
> | Option | Description |
> |--------|-------------|
> | **A – Always Textract (strict)** | Textract is always used. Tesseract is removed. Local dev requires AWS credentials. |
> | **B – Textract-first with Tesseract fallback (recommended)** | Textract is tried first. If AWS creds are unavailable, falls back to Tesseract. Good for hybrid dev/prod. |
> | **C – Config-driven override** | An env var `OCR_ENGINE=textract|tesseract|auto` controls which engine is used. Most flexible. |
>
> This plan assumes **Option C** as default (most flexible), with `OCR_ENGINE=textract` for production.

> [!WARNING]
> **AWS Textract pricing**: `analyze_document` (sync) = ~$0.015/page; `start_document_analysis` (async) = ~$0.015/page.
> Make sure the team is aware of per-page costs before switching all uploads to Textract.

> [!IMPORTANT]
> **Async job support**: The S3-based async flow requires an S3 bucket the Textract service role can read.
> The project already has S3 config (`S3_BUCKET`, `S3_ACCESS_KEY`, etc. in `config.py`).
> Confirm that the configured bucket is in the **same AWS region** as the Textract endpoint being used.

---

## Open Questions

> [!IMPORTANT]
> 1. Should the existing `TextractOCREngine` be upgraded to **async job mode** (`start_document_analysis`)?  
>    Sync mode (`analyze_document`) is simpler but limited to documents ≤ 10 MB.  
>    Async mode handles all sizes but requires polling or SNS notification.
>
> 2. Should Textract **FORMS** feature type be added alongside **TABLES**?  
>    Some bank statements use key-value pairs rather than structured tables.
>
> 3. Should a **per-statement cost estimate** (pages × $0.015) be stored in the DB / returned in the API response?
>
> 4. Is there a **specific AWS region** the Textract client should target, or should it read from the environment (`AWS_DEFAULT_REGION`)?

---

## Proposed Changes

### 1. Configuration — `core/config.py`

#### [MODIFY] [config.py](file:///Users/gouthamnaroju/Desktop/ref/Bank_statement_scanner/apps/api/core/config.py)

Add new settings under the existing AWS/S3 block:

```python
# ─── OCR Engine ─────────────────────────────────────────────────
OCR_ENGINE: str = "auto"          # "textract" | "tesseract" | "auto"
TEXTRACT_REGION: str = "us-east-1"
TEXTRACT_S3_BUCKET: str = ""      # bucket for async jobs; defaults to S3_BUCKET if blank
TEXTRACT_ASYNC_ENABLED: bool = False  # True = use start_document_analysis (S3 flow)
AWS_ACCESS_KEY_ID: str = ""
AWS_SECRET_ACCESS_KEY: str = ""
AWS_DEFAULT_REGION: str = "us-east-1"
```

#### [MODIFY] [.env.example](file:///Users/gouthamnaroju/Desktop/ref/Bank_statement_scanner/apps/api/.env.example)

Add the OCR and AWS credential variables so developers know what to set:

```dotenv
# ─── OCR Engine ──────────────────────────────────────────────────
OCR_ENGINE=textract          # textract | tesseract | auto
TEXTRACT_REGION=us-east-1
TEXTRACT_ASYNC_ENABLED=false # set true for async S3-based jobs (large files)
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_DEFAULT_REGION=us-east-1
```

---

### 2. OCR Worker — `statements/ocr_worker.py`

This is the primary file to change. All changes are within this single module.

#### [MODIFY] [ocr_worker.py](file:///Users/gouthamnaroju/Desktop/ref/Bank_statement_scanner/apps/api/statements/ocr_worker.py)

**a) Upgrade `TextractOCREngine` (sync path)**

- Pass `region_name` from `settings.TEXTRACT_REGION` to `boto3.client("textract", ...)`.
- Add `FORMS` to `FeatureTypes` list alongside `TABLES` (optional, see open questions).
- Add explicit `FeatureTypes` parameter from a constant so it can be extended easily.
- Add better error categorisation: throttle errors vs auth errors vs size errors with distinct messages.

**b) Add `TextractAsyncOCREngine` class (new)**

For documents > 10 MB or when `TEXTRACT_ASYNC_ENABLED=True`:

```
1. Upload PDF to S3 using boto3 (to TEXTRACT_S3_BUCKET or S3_BUCKET)
2. Call textract.start_document_analysis(S3Object=..., FeatureTypes=['TABLES'])
3. Poll get_document_analysis(JobId=...) with exponential back-off until status ≠ PROCESSING
4. Paginate through all result pages with NextToken
5. Feed pages through existing _parse_response() logic
6. Delete the S3 object after retrieval (clean up)
```

**c) Rewrite `get_ocr_engine()`**

New priority logic driven by `settings.OCR_ENGINE`:

```python
def get_ocr_engine() -> OCREngine:
    mode = settings.OCR_ENGINE.lower()  # "textract" | "tesseract" | "auto"

    if mode == "tesseract":
        # Force local Tesseract — raise if not found
        ...

    if mode == "textract" or mode == "auto":
        # Try Textract first
        if _textract_credentials_available():
            if settings.TEXTRACT_ASYNC_ENABLED:
                return TextractAsyncOCREngine()
            return TextractOCREngine()
        if mode == "textract":
            raise RuntimeError("OCR_ENGINE=textract but no AWS credentials found.")
        # mode == "auto": fall through to Tesseract

    # Fallback: local Tesseract
    if shutil.which("tesseract"):
        logger.warning("Falling back to local Tesseract OCR engine.")
        return TesseractOCREngine()

    raise RuntimeError("No OCR engine available. ...")
```

**d) Add `_textract_credentials_available()` helper**

Isolates the STS credential check into a small, testable function.

---

### 3. Docker — `Dockerfile`

#### [MODIFY] [Dockerfile](file:///Users/gouthamnaroju/Desktop/ref/Bank_statement_scanner/apps/api/Dockerfile)

When `OCR_ENGINE=textract`, the container no longer needs `tesseract-ocr` or
`libgl1` (OpenCV). The Dockerfile should be updated to make these **optional**:

```dockerfile
# Install system dependencies:
#   - poppler-utils: required by pdf2image for all PDF parsing
#   - tesseract-ocr + libgl1: only needed when OCR_ENGINE=tesseract or auto
ARG INSTALL_TESSERACT=false
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    $([ "$INSTALL_TESSERACT" = "true" ] && echo "tesseract-ocr libgl1") \
    && rm -rf /var/lib/apt/lists/*
```

Or, more pragmatically for the short term — keep both installed but document
that they will be removed once Textract is fully adopted.

---

### 4. Requirements — `requirements.txt`

#### [MODIFY] [requirements.txt](file:///Users/gouthamnaroju/Desktop/ref/Bank_statement_scanner/apps/api/requirements.txt)

- `boto3==1.35.0` is already present ✅
- Mark `pytesseract`, `opencv-python-headless`, `pdf2image`, and `Pillow` as
  **optional / fallback** in a comment block. No package removals yet — keep
  them for the fallback path.

---

### 5. Tests — `apps/api/tests/`

#### [NEW] `tests/test_ocr_engine_selection.py`

Unit tests for the new `get_ocr_engine()` logic:

| Test case | `OCR_ENGINE` | AWS creds | Tesseract | Expected engine |
|-----------|-------------|-----------|-----------|-----------------|
| Textract-forced, creds ok | `textract` | ✅ | ✅ | `TextractOCREngine` |
| Textract-forced, no creds | `textract` | ❌ | ✅ | `RuntimeError` |
| Auto, creds ok | `auto` | ✅ | ✅ | `TextractOCREngine` |
| Auto, no creds | `auto` | ❌ | ✅ | `TesseractOCREngine` (fallback) |
| Tesseract-forced | `tesseract` | ✅ | ✅ | `TesseractOCREngine` |
| Nothing available | `auto` | ❌ | ❌ | `RuntimeError` |

#### [NEW] `tests/test_textract_engine.py`

- Mock `boto3.client("textract")` to test `_parse_response()` with a sample Textract response dict
- Test async engine polling loop with mocked `get_document_analysis` status transitions

---

## Implementation Order

```
1. core/config.py          — add OCR settings (no-risk)
2. .env.example            — document new vars
3. ocr_worker.py           — main engine logic changes
4. Dockerfile              — update system deps comment/flag
5. requirements.txt        — annotate optional deps
6. tests/                  — add unit tests
```

---

## Verification Plan

### Automated Tests
```bash
cd apps/api
pytest tests/test_ocr_engine_selection.py -v
pytest tests/test_textract_engine.py -v
```

### Manual Verification

1. Set `OCR_ENGINE=textract`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` in `.env`.
2. Upload a scanned-PDF bank statement via `POST /v1/statements/upload`.
3. Confirm `metadata.ocr_engine == "textract"` in the API response.
4. Verify transactions are extracted with higher confidence than the Tesseract baseline.
5. Test fallback: unset AWS creds with `OCR_ENGINE=auto` → confirm `TesseractOCREngine` is selected and OCR still works.
6. For async path: set `TEXTRACT_ASYNC_ENABLED=True` and upload a > 5 MB PDF → confirm polling completes and results are returned.
