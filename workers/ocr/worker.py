"""
OCR Worker — consumes messages from the `ocr` queue, runs Tesseract / AWS
Textract on uploaded PDFs/images, and publishes structured page-text back
to the `parser` queue.

Queue message contract (JSON):
  {
    "statement_id": "<uuid>",
    "s3_key":        "<bucket/key>",
    "file_type":     "pdf" | "image",
    "ocr_engine":    "textract" | "tesseract" | "auto"
  }
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

logger = logging.getLogger(__name__)


async def process_message(message: dict) -> None:
    """Process a single OCR job message."""
    statement_id = message["statement_id"]
    s3_key = message["s3_key"]
    ocr_engine = message.get("ocr_engine", "auto")

    logger.info(
        "OCR worker processing statement=%s engine=%s s3_key=%s",
        statement_id,
        ocr_engine,
        s3_key,
    )

    # TODO: download from S3, run OCR, publish result to parser queue
    raise NotImplementedError("OCR worker is a stub — implement in Phase 2")


async def main() -> None:
    """Entry point: connect to Redis/SQS queue and consume messages."""
    queue_url = os.environ.get("OCR_QUEUE_URL", "redis://localhost:6379/1")
    logger.info("OCR worker starting, queue=%s", queue_url)

    # TODO: implement queue consumer loop
    await asyncio.sleep(0)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
