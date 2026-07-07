"""
PII masking for LLM prompt construction.

Replaces sensitive identifiers (account numbers, PAN, Aadhaar, card numbers,
phone numbers) in transaction narrations with neutral tokens before the text
is sent to any external LLM API.

PRD reference: Phase 1 Task 4 — "Financial data must not leave your
infrastructure unmasked. Required by PRD §11.4."

Usage:
    from core.pii_masker import mask_for_llm

    masked_text = mask_for_llm(narration, account_number="1234567890")
    # "UPI/9876543210/PHONEPE" -> "UPI/[PHONE]/PHONEPE"
"""
from __future__ import annotations

import re
from typing import Optional

# ─── Regex patterns ─────────────────────────────────────────

# Indian account numbers: 9-18 consecutive digits (standalone)
_ACCT_RE = re.compile(r"\b\d{9,18}\b")

# Indian PAN: 5 letters + 4 digits + 1 letter (e.g. ABCDE1234F)
_PAN_RE = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.IGNORECASE)

# Aadhaar: 12-digit number, optionally spaced in groups of 4
_AADHAAR_RE = re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b")

# Credit/debit card: 13-19 digits, optionally space/dash separated
_CARD_RE = re.compile(r"\b(?:\d[\s-]?){13,19}\b")

# Indian mobile numbers: +91 or 0 prefix + 10 digits, or standalone 10-digit
# starting with 6-9
_PHONE_RE = re.compile(
    r"(?:\+91[\s-]?|0)?[6-9]\d{9}\b"
)

# IFSC codes: 4 letters + 0 + 6 alphanumeric
_IFSC_RE = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b", re.IGNORECASE)


def mask_for_llm(
    narration: str,
    account_number: Optional[str] = None,
) -> str:
    """
    Return a version of `narration` safe to send to an external LLM.

    Substitution tokens:
      [ACCT]    — bank account numbers / long numeric sequences
      [PAN]     — Permanent Account Number
      [AADHAAR] — Aadhaar number
      [CARD]    — credit / debit card number
      [PHONE]   — mobile phone number
      [IFSC]    — IFSC code

    The specific account_number for this statement (if known) is masked
    first as an exact string before the generic regex pass.
    """
    text = narration

    # Exact match on the statement's own account number (most specific)
    if account_number:
        text = text.replace(account_number, "[ACCT]")

    # Generic passes ordered from most-specific to least-specific
    # (Card before generic digit runs to avoid over-masking)
    text = _CARD_RE.sub("[CARD]", text)
    text = _AADHAAR_RE.sub("[AADHAAR]", text)
    text = _PAN_RE.sub("[PAN]", text)
    text = _IFSC_RE.sub("[IFSC]", text)
    text = _PHONE_RE.sub("[PHONE]", text)
    text = _ACCT_RE.sub("[ACCT]", text)

    return text


def validate_no_pii(text: str) -> None:
    """
    Scan the text (usually the JSON payload sent to LLMs) for unmasked PII.
    Raises ValueError if any raw credit card, Aadhaar, PAN, phone number,
    or account number matches are found.
    """
    if _CARD_RE.search(text):
        raise ValueError("Safety check failed: Raw credit card number detected in prompt payload.")
    if _AADHAAR_RE.search(text):
        raise ValueError("Safety check failed: Raw Aadhaar number detected in prompt payload.")
    if _PAN_RE.search(text):
        raise ValueError("Safety check failed: Raw PAN detected in prompt payload.")
    if _PHONE_RE.search(text):
        raise ValueError("Safety check failed: Raw phone number detected in prompt payload.")
    if _ACCT_RE.search(text):
        raise ValueError("Safety check failed: Raw account number or long digit sequence detected in prompt payload.")

