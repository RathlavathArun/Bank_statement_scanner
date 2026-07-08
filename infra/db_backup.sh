#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# Bank Statement Scanner — Automated Database Backup Script
# PRD reference: Task 25 (daily pg_dump to S3/MinIO with rotation)
# ──────────────────────────────────────────────────────────────
set -euo pipefail

# ── Configuration & Defaults ─────────────────────────────────
POSTGRES_HOST="${POSTGRES_HOST:-postgres}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-bse_admin}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-bse_secret_2026}"
POSTGRES_DB="${POSTGRES_DB:-bank_statements}"

S3_ENDPOINT="${S3_ENDPOINT:-http://minio:9000}"
S3_ACCESS_KEY="${S3_ACCESS_KEY:-minioadmin}"
S3_SECRET_KEY="${S3_SECRET_KEY:-minioadmin123}"
S3_BUCKET="${S3_BUCKET:-bank-statements}"
BACKUP_PREFIX="${BACKUP_PREFIX:-backups/}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILENAME="pg_backup_${POSTGRES_DB}_${TIMESTAMP}.dump"
BACKUP_PATH="/tmp/${BACKUP_FILENAME}"

echo "[$(date +'%Y-%m-%d %H:%M:%S')] Starting automated database backup for ${POSTGRES_DB}..."

# 1. Perform PostgreSQL pg_dump (custom compressed format)
export PGPASSWORD="${POSTGRES_PASSWORD}"
pg_dump -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -F c -b -v -f "${BACKUP_PATH}" "${POSTGRES_DB}"
echo "[$(date +'%Y-%m-%d %H:%M:%S')] Database dump created successfully at ${BACKUP_PATH} ($(du -h "${BACKUP_PATH}" | cut -f1))"

# 2. Upload to MinIO / S3 Storage & Rotate Old Backups
if command -v mc &>/dev/null; then
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] MinIO client (mc) detected. Configuring host..."
    mc alias set bse_store "${S3_ENDPOINT}" "${S3_ACCESS_KEY}" "${S3_SECRET_KEY}" --api S3v4
    
    # Ensure bucket and prefix exist
    mc mb --ignore-existing "bse_store/${S3_BUCKET}"
    
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] Uploading backup to bse_store/${S3_BUCKET}/${BACKUP_PREFIX}${BACKUP_FILENAME}..."
    mc cp "${BACKUP_PATH}" "bse_store/${S3_BUCKET}/${BACKUP_PREFIX}${BACKUP_FILENAME}"
    
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] Pruning backups older than ${BACKUP_RETENTION_DAYS} days..."
    mc rm --force --older-than "${BACKUP_RETENTION_DAYS}d" "bse_store/${S3_BUCKET}/${BACKUP_PREFIX}" || true
    
elif command -v aws &>/dev/null; then
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] AWS CLI detected. Uploading backup..."
    export AWS_ACCESS_KEY_ID="${S3_ACCESS_KEY}"
    export AWS_SECRET_ACCESS_KEY="${S3_SECRET_KEY}"
    export AWS_DEFAULT_REGION="${AWS_REGION:-ap-south-1}"
    
    ENDPOINT_ARG=""
    if [[ "${S3_ENDPOINT}" != *"amazonaws.com"* ]]; then
        ENDPOINT_ARG="--endpoint-url ${S3_ENDPOINT}"
    fi
    
    aws s3 cp ${ENDPOINT_ARG} "${BACKUP_PATH}" "s3://${S3_BUCKET}/${BACKUP_PREFIX}${BACKUP_FILENAME}"
    
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] Pruning backups older than ${BACKUP_RETENTION_DAYS} days..."
    # Calculate cutoff date in seconds
    CUTOFF=$(date -d "${BACKUP_RETENTION_DAYS} days ago" +%s)
    aws s3 ls ${ENDPOINT_ARG} "s3://${S3_BUCKET}/${BACKUP_PREFIX}" | while read -r line; do
        FILE_DATE=$(echo "$line" | awk '{print $1" "$2}')
        FILE_NAME=$(echo "$line" | awk '{print $4}')
        if [[ -n "$FILE_NAME" && "$FILE_NAME" == pg_backup_* ]]; then
            FILE_TS=$(date -d "$FILE_DATE" +%s 2>/dev/null || echo 0)
            if [[ $FILE_TS -gt 0 && $FILE_TS -lt $CUTOFF ]]; then
                echo "Deleting old backup: $FILE_NAME"
                aws s3 rm ${ENDPOINT_ARG} "s3://${S3_BUCKET}/${BACKUP_PREFIX}${FILE_NAME}" || true
            fi
        fi
    done
else
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: Neither 'mc' nor 'aws' CLI tool found. Cannot upload backup."
    exit 1
fi

# 3. Cleanup local temp file
rm -f "${BACKUP_PATH}"
echo "[$(date +'%Y-%m-%d %H:%M:%S')] Automated database backup process completed successfully."
