# ── Bank Statement Extraction API ──────────────────────────────
# Production Dockerfile for FastAPI backend
# Requires build context that includes packages/bank-templates/

FROM python:3.12-slim AS base

# Install system dependencies:
#   - poppler-utils: required by pdf2image for all PDF parsing
#   - tesseract-ocr + libgl1: only needed when OCR_ENGINE=tesseract or auto
#     Pass --build-arg INSTALL_TESSERACT=false to skip (OCR_ENGINE=textract)
ARG INSTALL_TESSERACT=true
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    $([ "$INSTALL_TESSERACT" = "true" ] && echo "tesseract-ocr libgl1") \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Install Python dependencies first (cache layer) ──────────
COPY apps/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Create non-root user for SOC2 compliance ─────────────────
RUN groupadd -g 10001 appgroup && useradd -u 10001 -g appgroup -s /bin/false -m appuser

# ── Copy application code ────────────────────────────────────
COPY --chown=appuser:appgroup apps/api/ .

# ── Copy bank templates (YAML configs used by parser) ────────
COPY --chown=appuser:appgroup packages/bank-templates/ /app/bank-templates/

RUN mkdir -p /app/uploads && chown -R appuser:appgroup /app

USER 10001:10001

EXPOSE 8000

# Health check for ECS
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
