"""
Antivirus scanning via ClamAV daemon (clamd).

Every uploaded file is scanned before being written to disk or S3.
If a virus/malware is detected the upload is rejected with HTTP 422.
If ClamAV is unavailable and CLAMAV_ENABLED is True, the upload is
rejected conservatively (fail-closed). Set CLAMAV_ENABLED=false only
in environments that provably cannot receive malicious files (e.g. CI).

PRD reference: Phase 1 Task 3.
"""
from __future__ import annotations

import logging
from io import BytesIO

from fastapi import HTTPException, status

from core.config import settings

logger = logging.getLogger(__name__)


def _get_clamd_client():
    """Return a clamd network scanner connected to the configured daemon."""
    import clamd  # lazy import — only needed when scanning
    return clamd.ClamdNetworkSocket(
        host=settings.CLAMAV_HOST,
        port=settings.CLAMAV_PORT,
        timeout=30,
    )


async def scan_bytes(content: bytes, filename: str = "upload") -> None:
    """
    Scan `content` in-memory via ClamAV.

    Raises:
        HTTPException(422) if a virus/malware signature is found.
        HTTPException(503) if ClamAV is unreachable and CLAMAV_ENABLED=True.

    If CLAMAV_ENABLED=False this is a no-op (passthrough).
    """
    if not settings.CLAMAV_ENABLED:
        logger.debug("ClamAV disabled — skipping scan for %s", filename)
        return

    try:
        cd = _get_clamd_client()
        result = cd.instream(BytesIO(content))
    except Exception as exc:
        # ClamAV daemon is unreachable — fail-closed for security
        logger.error("ClamAV unreachable for %s: %s", filename, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Virus scanning service is temporarily unavailable. "
                "Your upload could not be processed. Please try again later."
            ),
        ) from exc

    # result is a dict like: {"stream": ("FOUND", "Eicar-Test-Signature")}
    stream_result = result.get("stream", ("OK", None))
    scan_status, virus_name = stream_result[0], stream_result[1]

    if scan_status == "FOUND":
        logger.warning(
            "VIRUS DETECTED in upload '%s': %s — upload rejected",
            filename,
            virus_name,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Uploaded file failed virus scan and was rejected ({virus_name}). "
                   "Please ensure the file is not infected and try again.",
        )

    if scan_status == "ERROR":
        logger.error("ClamAV scan error for %s: %s", filename, virus_name)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Virus scanner returned an error. Please try again.",
        )

    # scan_status == "OK" — file is clean
    logger.info("ClamAV: clean — %s (%d bytes)", filename, len(content))
