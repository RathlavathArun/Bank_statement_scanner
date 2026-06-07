# ── Bank Statement Extraction API ──────────────────────────────
# Production Dockerfile for FastAPI backend
# Requires build context that includes packages/bank-templates/

FROM python:3.12-slim AS base

# Install system dependencies:
#   - tesseract-ocr: OCR engine for scanned PDF extraction
#   - poppler-utils: pdf2image conversion (pdftotext, pdftoppm)
#   - libgl1: OpenCV headless runtime dependency
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    poppler-utils \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Install Python dependencies first (cache layer) ──────────
COPY apps/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Copy application code ────────────────────────────────────
COPY apps/api/ .

# ── Copy bank templates (YAML configs used by parser) ────────
COPY packages/bank-templates/ /app/bank-templates/

EXPOSE 8000

# Health check for ECS
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
