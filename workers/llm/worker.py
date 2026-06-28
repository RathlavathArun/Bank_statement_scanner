"""
LLM Categorisation Worker — consumes transactions from the `llm` queue,
calls the Anthropic / OpenAI API to assign ledger categories, and writes
results back to the database.

Queue message contract (JSON):
  {
    "statement_id":    "<uuid>",
    "transaction_ids": ["<uuid>", ...],
    "firm_id":         "<uuid>"
  }
"""
from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger(__name__)


async def process_message(message: dict) -> None:
    """Process a single LLM categorisation job."""
    statement_id = message["statement_id"]
    tx_ids = message.get("transaction_ids", [])
    firm_id = message.get("firm_id")

    logger.info(
        "LLM worker processing statement=%s transactions=%d firm=%s",
        statement_id,
        len(tx_ids),
        firm_id,
    )

    # TODO: load transactions from DB, mask PII, call LLM, write results
    raise NotImplementedError("LLM worker is a stub — implement in Phase 2")


async def main() -> None:
    """Entry point: connect to Redis/SQS queue and consume messages."""
    queue_url = os.environ.get("LLM_QUEUE_URL", "redis://localhost:6379/2")
    logger.info("LLM worker starting, queue=%s", queue_url)

    # TODO: implement queue consumer loop
    await asyncio.sleep(0)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
