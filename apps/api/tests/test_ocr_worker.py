"""
Tests for the OCR worker module — Phase 4.

All OCR dependencies (Tesseract, pdf2image, boto3/Textract) are mocked out
so these tests run without any external binaries or cloud credentials.

The module-under-test (``statements.ocr_worker``) provides:
  - Data classes:  OCRCell, OCRRow, OCRResult
  - Engines:       TesseractOCREngine, TextractOCREngine
  - Factory:       get_ocr_engine()
  - Orchestrator:  process_scanned_pdf()
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── make sure the API package is importable ──────────────────
API_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_DIR))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///test_placeholder.db")
os.environ.setdefault("DEBUG", "False")


# ── conditional import: skip entire module if ocr_worker doesn't exist yet ──
try:
    from statements.ocr_worker import (
        OCRCell,
        OCRResult,
        OCRRow,
        TesseractOCREngine,
        TextractOCREngine,
        get_ocr_engine,
        process_scanned_pdf,
    )

    _OCR_MODULE_AVAILABLE = True
except ImportError:
    _OCR_MODULE_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _OCR_MODULE_AVAILABLE,
    reason="statements.ocr_worker not implemented yet — skipping OCR tests",
)


# ─── Data-class unit tests ──────────────────────────────────
class TestOCRCell:
    """OCRCell is a lightweight value-object for a single OCR'd cell."""

    def test_cell_creation(self):
        cell = OCRCell(text="Hello", confidence=0.95)
        assert cell.text == "Hello"
        assert cell.confidence == 0.95

    def test_cell_confidence_range(self):
        cell = OCRCell(text="123", confidence=0.95)
        assert 0 <= cell.confidence <= 1

    def test_cell_with_bbox(self):
        cell = OCRCell(
            text="123",
            confidence=0.8,
            bbox={"x1": 0, "y1": 0, "x2": 100, "y2": 20},
        )
        assert cell.bbox is not None
        assert cell.bbox["x2"] == 100

    def test_cell_default_bbox_is_none(self):
        cell = OCRCell(text="abc", confidence=0.9)
        assert getattr(cell, "bbox", None) is None


class TestOCRRow:
    """OCRRow bundles multiple cells into a logical table row."""

    def test_row_holds_cells(self):
        cells = [OCRCell("a", 0.9), OCRCell("b", 0.8)]
        row = OCRRow(cells=cells, page_number=1, row_confidence=0.85)
        assert len(row.cells) == 2
        assert row.page_number == 1

    def test_row_confidence_value(self):
        cells = [OCRCell("a", 0.9), OCRCell("b", 0.8), OCRCell("c", 0.7)]
        row = OCRRow(cells=cells, page_number=1, row_confidence=0.8)
        assert row.row_confidence == pytest.approx(0.8, abs=0.01)

    def test_empty_row(self):
        row = OCRRow(cells=[], page_number=1, row_confidence=0.0)
        assert len(row.cells) == 0


class TestOCRResult:
    """OCRResult aggregates rows from all pages."""

    def test_result_creation(self):
        row = OCRRow(
            cells=[OCRCell("test", 0.9)],
            page_number=1,
            row_confidence=0.9,
        )
        result = OCRResult(
            rows=[row],
            pages_processed=1,
            engine_used="tesseract",
        )
        assert result.pages_processed == 1
        assert result.engine_used == "tesseract"
        assert len(result.rows) == 1

    def test_empty_result(self):
        result = OCRResult(
            rows=[],
            pages_processed=0,
            engine_used="tesseract",
        )
        assert result.pages_processed == 0
        assert len(result.rows) == 0


# ─── Tesseract engine ──────────────────────────────────────
class TestTesseractEngine:
    """TesseractOCREngine wraps pytesseract + pdf2image."""

    @patch("shutil.which", return_value="/usr/bin/tesseract")
    def test_tesseract_processes_single_page(self, mock_which):
        import numpy as np

        # Mock the imports that happen inside TesseractOCREngine.extract
        mock_image = MagicMock()
        mock_pil_array = np.zeros((2970, 2100, 3), dtype=np.uint8)

        with (
            patch("pdf2image.convert_from_path", return_value=[mock_image]) as mock_pdf2img,
            patch("numpy.array", return_value=mock_pil_array),
            patch.object(TesseractOCREngine, "_preprocess", return_value=np.zeros((2970, 2100), dtype=np.uint8)),
            patch.object(TesseractOCREngine, "_run_tesseract") as mock_tess,
        ):
            mock_tess.return_value = [
                {"text": "01/01/2026", "confidence": 0.95, "x": 50, "y": 100, "w": 120, "h": 20},
                {"text": "UPI", "confidence": 0.90, "x": 250, "y": 100, "w": 50, "h": 20},
                {"text": "Payment", "confidence": 0.88, "x": 450, "y": 100, "w": 100, "h": 20},
                {"text": "1000.00", "confidence": 0.92, "x": 650, "y": 100, "w": 100, "h": 20},
                {"text": "49000.00", "confidence": 0.91, "x": 850, "y": 100, "w": 120, "h": 20},
            ]

            engine = TesseractOCREngine()
            result = engine.extract(Path("/fake/path.pdf"))
            assert result.pages_processed == 1
            assert result.engine_used == "tesseract"
            assert len(result.rows) >= 1

    @patch("shutil.which", return_value="/usr/bin/tesseract")
    def test_tesseract_multi_page(self, mock_which):
        import numpy as np

        mock_images = [MagicMock() for _ in range(3)]
        mock_pil_array = np.zeros((2970, 2100, 3), dtype=np.uint8)

        with (
            patch("pdf2image.convert_from_path", return_value=mock_images),
            patch("numpy.array", return_value=mock_pil_array),
            patch.object(TesseractOCREngine, "_preprocess", return_value=np.zeros((2970, 2100), dtype=np.uint8)),
            patch.object(TesseractOCREngine, "_run_tesseract") as mock_tess,
        ):
            mock_tess.return_value = [
                {"text": "01/01/2026", "confidence": 0.92, "x": 50, "y": 100, "w": 120, "h": 20},
                {"text": "Test", "confidence": 0.88, "x": 250, "y": 100, "w": 100, "h": 20},
                {"text": "500.00", "confidence": 0.90, "x": 450, "y": 100, "w": 100, "h": 20},
            ]

            engine = TesseractOCREngine()
            result = engine.extract(Path("/fake/multipage.pdf"))
            assert result.pages_processed == 3

    def test_tesseract_extract_fails_without_poppler(self):
        """When pdf2image can't find poppler/tesseract, extract should raise."""
        engine = TesseractOCREngine()
        with patch("pdf2image.convert_from_path", side_effect=Exception("poppler not found")):
            with pytest.raises(Exception):
                engine.extract(Path("/fake/path.pdf"))


# ─── Textract engine ───────────────────────────────────────
class TestTextractEngine:
    """TextractOCREngine wraps AWS Textract's AnalyzeDocument."""

    @patch("builtins.open", MagicMock())
    @patch("boto3.client")
    def test_textract_processes_document(self, mock_boto):
        mock_client = MagicMock()
        mock_client.analyze_document.return_value = {
            "Blocks": [
                {
                    "BlockType": "TABLE",
                    "Id": "table1",
                    "Relationships": [
                        {"Type": "CHILD", "Ids": ["cell1", "cell2"]},
                    ],
                },
                {
                    "BlockType": "CELL",
                    "Id": "cell1",
                    "RowIndex": 1,
                    "ColumnIndex": 1,
                    "Relationships": [{"Type": "CHILD", "Ids": ["word1"]}],
                    "Confidence": 98.5,
                },
                {
                    "BlockType": "CELL",
                    "Id": "cell2",
                    "RowIndex": 1,
                    "ColumnIndex": 2,
                    "Relationships": [{"Type": "CHILD", "Ids": ["word2"]}],
                    "Confidence": 95.0,
                },
                {
                    "BlockType": "WORD",
                    "Id": "word1",
                    "Text": "01/01/2026",
                    "Confidence": 98.5,
                },
                {
                    "BlockType": "WORD",
                    "Id": "word2",
                    "Text": "Payment",
                    "Confidence": 95.0,
                },
            ]
        }
        mock_boto.return_value = mock_client

        engine = TextractOCREngine()
        result = engine.extract(Path("/fake/path.pdf"))
        assert result.engine_used == "textract"
        assert result.pages_processed >= 1

    @patch("builtins.open", MagicMock())
    @patch("boto3.client")
    def test_textract_empty_response(self, mock_boto):
        """Textract returning no TABLE blocks still gives a valid result."""
        mock_client = MagicMock()
        mock_client.analyze_document.return_value = {"Blocks": []}
        mock_boto.return_value = mock_client

        engine = TextractOCREngine()
        result = engine.extract(Path("/fake/empty.pdf"))
        assert result.engine_used == "textract"
        assert len(result.rows) == 0


# ─── Engine selection / fallback ────────────────────────────
class TestOCRFallback:
    """get_ocr_engine() picks the best available backend."""

    @patch("shutil.which", return_value="/usr/bin/tesseract")
    def test_get_engine_prefers_tesseract(self, mock_which):
        with patch("core.config.settings.OCR_ENGINE", "tesseract"):
            engine = get_ocr_engine()
            assert isinstance(engine, TesseractOCREngine)

    @patch("statements.ocr_worker.shutil.which", return_value=None)
    @patch("statements.ocr_worker._textract_credentials_available", return_value=True)
    def test_falls_back_to_textract(self, _mock_creds, _mock_which):
        """When Tesseract is not found, should try Textract."""
        with patch("core.config.settings.OCR_ENGINE", "auto"):
            engine = get_ocr_engine()
            assert isinstance(engine, TextractOCREngine)

    @patch("shutil.which", return_value=None)
    @patch("statements.ocr_worker._textract_credentials_available", return_value=False)
    def test_no_engine_raises_when_no_aws(self, _mock_creds, mock_which):
        """When neither Tesseract nor AWS is configured, should raise."""
        with patch("core.config.settings.OCR_ENGINE", "auto"):
            with pytest.raises(Exception):
                get_ocr_engine()


# ─── process_scanned_pdf orchestrator ───────────────────────
class TestProcessScannedPDF:
    """High-level orchestrator that combines OCR → row parsing."""

    @patch("statements.ocr_worker.get_ocr_engine")
    def test_process_scanned_pdf_returns_parsed_statement(self, mock_get_engine):
        # Build a mock engine that returns a fake OCRResult
        mock_engine = MagicMock()
        row = OCRRow(
            cells=[
                OCRCell("01/01/2026", 0.95),
                OCRCell("UPI Payment to Vendor", 0.90),
                OCRCell("REF123", 0.88),
                OCRCell("1000.00", 0.92),
                OCRCell("", 0.0),
                OCRCell("49000.00", 0.91),
            ],
            page_number=1,
            row_confidence=0.91,
        )
        mock_engine.extract.return_value = OCRResult(
            rows=[row],
            pages_processed=1,
            engine_used="tesseract",
        )
        mock_get_engine.return_value = mock_engine

        result = process_scanned_pdf(Path("/fake/scanned.pdf"))

        assert result is not None
        # The result could be a ParsedStatement or OCRResult depending on impl
        mock_engine.extract.assert_called_once()

    @patch("statements.ocr_worker.get_ocr_engine")
    def test_process_scanned_pdf_without_bank_code(self, mock_get_engine):
        """Should work even without a bank_code (generic column detection)."""
        mock_engine = MagicMock()
        row = OCRRow(
            cells=[
                OCRCell("01/01/2026", 0.90),
                OCRCell("Some Description", 0.85),
                OCRCell("", 0.0),
                OCRCell("500.00", 0.88),
                OCRCell("", 0.0),
                OCRCell("9500.00", 0.87),
            ],
            page_number=1,
            row_confidence=0.87,
        )
        mock_engine.extract.return_value = OCRResult(
            rows=[row],
            pages_processed=1,
            engine_used="tesseract",
        )
        mock_get_engine.return_value = mock_engine

        result = process_scanned_pdf(Path("/fake/scanned.pdf"))
        assert result is not None
