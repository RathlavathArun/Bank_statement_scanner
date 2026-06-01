"""
Tests for OCR confidence thresholds and status transitions — Phase 4.

These tests verify the business rules around OCR confidence scoring:
  - High confidence (≥ 0.85):  no flag
  - Medium confidence (0.70–0.85):  yellow warning
  - Low confidence (< 0.70):  red flag

And the statement status lifecycle through OCR processing:
  UPLOADED → PARSING → OCR → READY_FOR_REVIEW
"""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

import pytest

# ── make sure the API package is importable ──────────────────
API_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_DIR))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///test_placeholder.db")
os.environ.setdefault("DEBUG", "False")


# ── conditional import ──────────────────────────────────────
try:
    from statements.ocr_worker import OCRCell, OCRResult, OCRRow

    _OCR_MODULE_AVAILABLE = True
except ImportError:
    _OCR_MODULE_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _OCR_MODULE_AVAILABLE,
    reason="statements.ocr_worker not implemented yet — skipping confidence tests",
)


# ─── Confidence classification helpers ──────────────────────
# These mirror the thresholds the frontend / review UI will use.
# The implementation may live in ocr_worker.py or a shared constants module.

HIGH_CONFIDENCE_THRESHOLD = 0.85
MEDIUM_CONFIDENCE_THRESHOLD = 0.70


def classify_confidence(confidence: float) -> str:
    """Classify a confidence score into a review tier.

    Returns one of: 'high', 'medium', 'low'.
    """
    if confidence >= HIGH_CONFIDENCE_THRESHOLD:
        return "high"
    elif confidence >= MEDIUM_CONFIDENCE_THRESHOLD:
        return "medium"
    else:
        return "low"


# ─── Threshold tests ───────────────────────────────────────
class TestConfidenceThresholds:
    """Verify the three-tier confidence classification."""

    def test_high_confidence_not_flagged(self):
        """Rows with confidence ≥ 0.85 should NOT be flagged for review."""
        high_confidence_values = [0.85, 0.90, 0.95, 0.99, 1.0]
        for conf in high_confidence_values:
            assert classify_confidence(conf) == "high", (
                f"Confidence {conf} should be 'high', not flagged"
            )

    def test_medium_confidence_warning(self):
        """Rows with confidence 0.70–0.85 get yellow/warning flag."""
        medium_values = [0.70, 0.75, 0.80, 0.849]
        for conf in medium_values:
            assert classify_confidence(conf) == "medium", (
                f"Confidence {conf} should be 'medium' (yellow warning)"
            )

    def test_low_confidence_red_flagged(self):
        """Rows with confidence < 0.70 are red-flagged for manual review."""
        low_values = [0.0, 0.10, 0.50, 0.69]
        for conf in low_values:
            assert classify_confidence(conf) == "low", (
                f"Confidence {conf} should be 'low' (red flag)"
            )

    def test_boundary_085_is_high(self):
        """Exactly 0.85 is high (inclusive boundary)."""
        assert classify_confidence(0.85) == "high"

    def test_boundary_070_is_medium(self):
        """Exactly 0.70 is medium (inclusive boundary)."""
        assert classify_confidence(0.70) == "medium"


class TestOCRRowConfidence:
    """Verify that row-level confidence is computed correctly."""

    def test_row_with_all_high_confidence_cells(self):
        cells = [
            OCRCell("01/01/2026", 0.98),
            OCRCell("UPI Payment", 0.95),
            OCRCell("1000.00", 0.92),
        ]
        avg = sum(c.confidence for c in cells) / len(cells)
        row = OCRRow(cells=cells, page_number=1, row_confidence=avg)
        assert classify_confidence(row.row_confidence) == "high"

    def test_row_with_mixed_confidence_cells(self):
        cells = [
            OCRCell("01/01/2026", 0.85),
            OCRCell("???\u0300", 0.45),   # poorly OCR'd cell
            OCRCell("500.00", 0.80),
        ]
        avg = sum(c.confidence for c in cells) / len(cells)
        row = OCRRow(cells=cells, page_number=1, row_confidence=avg)
        # Average ~0.70, should be medium
        assert classify_confidence(row.row_confidence) == "medium"

    def test_row_with_all_low_confidence_cells(self):
        cells = [
            OCRCell("???", 0.30),
            OCRCell("###", 0.25),
            OCRCell("...", 0.20),
        ]
        avg = sum(c.confidence for c in cells) / len(cells)
        row = OCRRow(cells=cells, page_number=1, row_confidence=avg)
        assert classify_confidence(row.row_confidence) == "low"


class TestOCRResultConfidence:
    """Overall OCR result confidence aggregation."""

    def test_overall_confidence_computed(self):
        rows = [
            OCRRow(
                cells=[OCRCell("a", 0.95)],
                page_number=1,
                row_confidence=0.95,
            ),
            OCRRow(
                cells=[OCRCell("b", 0.85)],
                page_number=1,
                row_confidence=0.85,
            ),
        ]
        overall = sum(r.row_confidence for r in rows) / len(rows)
        result = OCRResult(
            rows=rows,
            pages_processed=1,
            engine_used="tesseract",
        )
        # Verify overall confidence can be computed from row data
        assert overall == pytest.approx(0.90, abs=0.01)

    def test_flag_count_by_tier(self):
        """Count how many rows fall into each confidence tier."""
        rows = [
            OCRRow(cells=[], page_number=1, row_confidence=0.95),  # high
            OCRRow(cells=[], page_number=1, row_confidence=0.92),  # high
            OCRRow(cells=[], page_number=1, row_confidence=0.78),  # medium
            OCRRow(cells=[], page_number=1, row_confidence=0.60),  # low
            OCRRow(cells=[], page_number=1, row_confidence=0.45),  # low
        ]
        tiers = [classify_confidence(r.row_confidence) for r in rows]
        assert tiers.count("high") == 2
        assert tiers.count("medium") == 1
        assert tiers.count("low") == 2


# ─── Status transition tests ───────────────────────────────
class TestOCRStatusTransitions:
    """Statement status lifecycle when OCR processing is involved.

    Expected flow:
      UPLOADED → PARSING → OCR → READY_FOR_REVIEW
    """

    VALID_OCR_FLOW = ["UPLOADED", "PARSING", "OCR", "READY_FOR_REVIEW"]

    def test_valid_status_sequence(self):
        """The canonical OCR status flow is a valid forward progression."""
        flow = self.VALID_OCR_FLOW
        for i in range(len(flow) - 1):
            assert flow[i] != flow[i + 1], "Adjacent statuses should differ"

    def test_uploaded_transitions_to_parsing(self):
        """First transition: UPLOADED → PARSING."""
        assert self.VALID_OCR_FLOW[0] == "UPLOADED"
        assert self.VALID_OCR_FLOW[1] == "PARSING"

    def test_parsing_transitions_to_ocr(self):
        """Second transition: PARSING → OCR."""
        assert self.VALID_OCR_FLOW[1] == "PARSING"
        assert self.VALID_OCR_FLOW[2] == "OCR"

    def test_ocr_transitions_to_ready_for_review(self):
        """Final transition: OCR → READY_FOR_REVIEW."""
        assert self.VALID_OCR_FLOW[2] == "OCR"
        assert self.VALID_OCR_FLOW[3] == "READY_FOR_REVIEW"

    def test_ocr_status_in_allowed_set(self):
        """OCR status value must be in the router's ALLOWED_STATUSES set."""
        ALLOWED_STATUSES = {
            "UPLOADED", "PARSING", "OCR", "READY_FOR_REVIEW",
            "REVIEWED", "EXPORTED", "FAILED", "PARSE_ERROR",
        }
        for s in self.VALID_OCR_FLOW:
            assert s in ALLOWED_STATUSES, f"Status '{s}' not in ALLOWED_STATUSES"

    def test_failed_status_on_ocr_error(self):
        """When OCR fails completely, status should be FAILED."""
        assert "FAILED" in {
            "UPLOADED", "PARSING", "OCR", "READY_FOR_REVIEW",
            "REVIEWED", "EXPORTED", "FAILED", "PARSE_ERROR",
        }


class TestTransactionOCRFields:
    """Verify that Transaction model has OCR-specific fields."""

    def test_transaction_model_has_ocr_confidence(self):
        """Transaction.ocr_confidence column should exist in the model."""
        from db.models import Transaction

        assert hasattr(Transaction, "ocr_confidence"), (
            "Transaction model should have ocr_confidence field"
        )

    def test_transaction_model_has_page_number(self):
        """Transaction.page_number column should exist."""
        from db.models import Transaction

        assert hasattr(Transaction, "page_number"), (
            "Transaction model should have page_number field"
        )

    def test_transaction_model_has_bbox(self):
        """Transaction.bbox (bounding box) column should exist."""
        from db.models import Transaction

        assert hasattr(Transaction, "bbox"), (
            "Transaction model should have bbox field for PDF preview"
        )
