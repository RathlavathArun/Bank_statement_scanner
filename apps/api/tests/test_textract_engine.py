"""
Tests for the Textract OCR engine — response parsing and async polling.

Uses mock boto3 clients so no real AWS calls are made.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from statements.ocr_worker import (
    TextractOCREngine,
    TextractAsyncOCREngine,
    OCRResult,
    _get_textract_feature_types,
)

SETTINGS_PATH = "core.config.settings"

# ── Fixtures / sample data ──────────────────────────────────────

SAMPLE_TEXTRACT_RESPONSE = {
    "DocumentMetadata": {"Pages": 1},
    "ResponseMetadata": {"RequestId": "test-req-123"},
    "Blocks": [
        # PAGE block
        {
            "BlockType": "PAGE",
            "Id": "page-1",
            "Page": 1,
        },
        # TABLE block
        {
            "BlockType": "TABLE",
            "Id": "table-1",
            "Page": 1,
            "Relationships": [
                {
                    "Type": "CHILD",
                    "Ids": ["cell-1-1", "cell-1-2", "cell-2-1", "cell-2-2"],
                }
            ],
        },
        # Row 1, Cell 1
        {
            "BlockType": "CELL",
            "Id": "cell-1-1",
            "RowIndex": 1,
            "ColumnIndex": 1,
            "Confidence": 99.5,
            "Geometry": {"BoundingBox": {"Left": 0.0, "Top": 0.0, "Width": 0.3, "Height": 0.05}},
            "Relationships": [{"Type": "CHILD", "Ids": ["word-1"]}],
        },
        # Row 1, Cell 2
        {
            "BlockType": "CELL",
            "Id": "cell-1-2",
            "RowIndex": 1,
            "ColumnIndex": 2,
            "Confidence": 98.0,
            "Geometry": {"BoundingBox": {"Left": 0.3, "Top": 0.0, "Width": 0.3, "Height": 0.05}},
            "Relationships": [{"Type": "CHILD", "Ids": ["word-2"]}],
        },
        # Row 2, Cell 1
        {
            "BlockType": "CELL",
            "Id": "cell-2-1",
            "RowIndex": 2,
            "ColumnIndex": 1,
            "Confidence": 97.0,
            "Geometry": {"BoundingBox": {"Left": 0.0, "Top": 0.05, "Width": 0.3, "Height": 0.05}},
            "Relationships": [{"Type": "CHILD", "Ids": ["word-3"]}],
        },
        # Row 2, Cell 2
        {
            "BlockType": "CELL",
            "Id": "cell-2-2",
            "RowIndex": 2,
            "ColumnIndex": 2,
            "Confidence": 96.5,
            "Geometry": {"BoundingBox": {"Left": 0.3, "Top": 0.05, "Width": 0.3, "Height": 0.05}},
            "Relationships": [{"Type": "CHILD", "Ids": ["word-4"]}],
        },
        # WORD blocks
        {"BlockType": "WORD", "Id": "word-1", "Text": "Date", "Confidence": 99.5},
        {"BlockType": "WORD", "Id": "word-2", "Text": "Amount", "Confidence": 98.0},
        {"BlockType": "WORD", "Id": "word-3", "Text": "01/01/2025", "Confidence": 97.0},
        {"BlockType": "WORD", "Id": "word-4", "Text": "1500.00", "Confidence": 96.5},
    ],
}


def _make_settings(**overrides):
    """Create a mock settings object with defaults + overrides."""
    defaults = {
        "OCR_ENGINE": "auto",
        "TEXTRACT_REGION": "ap-south-1",
        "TEXTRACT_S3_BUCKET": "test-bucket",
        "TEXTRACT_ASYNC_ENABLED": False,
        "TEXTRACT_FEATURE_TYPES": "TABLES",
        "AWS_ACCESS_KEY_ID": "AKIA...",
        "AWS_SECRET_ACCESS_KEY": "secret",
        "AWS_DEFAULT_REGION": "ap-south-1",
        "S3_BUCKET": "bank-statements",
    }
    defaults.update(overrides)
    mock = MagicMock()
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


# ── Sync engine — parse_response tests ──────────────────────────


class TestTextractParseResponse:
    """Tests for TextractOCREngine._parse_response()."""

    def test_parses_table_rows(self):
        """Basic response with 2 rows × 2 cells is parsed correctly."""
        result = TextractOCREngine._parse_response(SAMPLE_TEXTRACT_RESPONSE)

        assert isinstance(result, OCRResult)
        assert result.engine_used == "textract"
        assert result.pages_processed == 1
        assert len(result.rows) == 2

        # Row 1: "Date" | "Amount"
        row1 = result.rows[0]
        assert row1.page_number == 1
        assert len(row1.cells) == 2
        assert row1.cells[0].text == "Date"
        assert row1.cells[1].text == "Amount"

        # Row 2: "01/01/2025" | "1500.00"
        row2 = result.rows[1]
        assert row2.cells[0].text == "01/01/2025"
        assert row2.cells[1].text == "1500.00"

    def test_confidence_normalised(self):
        """Confidence values are normalised from 0-100 to 0.0-1.0."""
        result = TextractOCREngine._parse_response(SAMPLE_TEXTRACT_RESPONSE)
        assert result.rows[0].cells[0].confidence == pytest.approx(0.995, abs=0.001)

    def test_bbox_computed(self):
        """Bounding boxes are computed from Left/Top/Width/Height."""
        result = TextractOCREngine._parse_response(SAMPLE_TEXTRACT_RESPONSE)
        bbox = result.rows[0].cells[0].bbox
        assert bbox is not None
        assert bbox["x1"] == 0.0
        assert bbox["y1"] == 0.0
        assert bbox["x2"] == pytest.approx(0.3)
        assert bbox["y2"] == pytest.approx(0.05)

    def test_empty_response(self):
        """Empty Blocks list → empty result."""
        result = TextractOCREngine._parse_response({
            "Blocks": [],
            "DocumentMetadata": {"Pages": 0},
        })
        assert len(result.rows) == 0
        assert result.pages_processed == 0

    def test_metadata_includes_request_id(self):
        """Response metadata includes the RequestId."""
        result = TextractOCREngine._parse_response(SAMPLE_TEXTRACT_RESPONSE)
        assert result.metadata["request_id"] == "test-req-123"


# ── Feature types helper ────────────────────────────────────────


class TestGetTextractFeatureTypes:
    """Tests for _get_textract_feature_types()."""

    def test_single_feature(self):
        """'TABLES' → ['TABLES']."""
        with patch(SETTINGS_PATH, _make_settings(TEXTRACT_FEATURE_TYPES="TABLES")):
            assert _get_textract_feature_types() == ["TABLES"]

    def test_multiple_features(self):
        """'TABLES,FORMS' → ['TABLES', 'FORMS']."""
        with patch(SETTINGS_PATH, _make_settings(TEXTRACT_FEATURE_TYPES="TABLES,FORMS")):
            result = _get_textract_feature_types()
            assert "TABLES" in result
            assert "FORMS" in result

    def test_whitespace_handling(self):
        """' TABLES , FORMS ' → ['TABLES', 'FORMS']."""
        with patch(SETTINGS_PATH, _make_settings(TEXTRACT_FEATURE_TYPES=" TABLES , FORMS ")):
            result = _get_textract_feature_types()
            assert result == ["TABLES", "FORMS"]


# ── Async engine — polling tests ────────────────────────────────


class TestTextractAsyncPolling:
    """Tests for TextractAsyncOCREngine poll loop with mocked boto3."""

    @patch("statements.ocr_worker.time.sleep")  # skip actual waits
    @patch("statements.ocr_worker.boto3")
    def test_successful_async_job(self, mock_boto3, mock_sleep):
        """Async job: IN_PROGRESS → SUCCEEDED → results returned."""
        mock_settings = _make_settings()

        # S3 client
        mock_s3 = MagicMock()

        # Textract client
        mock_textract = MagicMock()
        mock_textract.start_document_analysis.return_value = {"JobId": "job-123"}
        mock_textract.get_document_analysis.side_effect = [
            # First poll: still processing
            {"JobStatus": "IN_PROGRESS"},
            # Second poll: succeeded
            {
                "JobStatus": "SUCCEEDED",
                "Blocks": SAMPLE_TEXTRACT_RESPONSE["Blocks"],
                "DocumentMetadata": {"Pages": 1},
            },
        ]

        def client_factory(service, **kwargs):
            if service == "s3":
                return mock_s3
            return mock_textract

        mock_boto3.client.side_effect = client_factory

        engine = TextractAsyncOCREngine()
        engine.INITIAL_WAIT_SECONDS = 0.01  # speed up test

        with patch(SETTINGS_PATH, mock_settings):
            result = engine.extract(Path("/tmp/test.pdf"))

        assert isinstance(result, OCRResult)
        assert result.engine_used == "textract"
        assert result.metadata.get("async") is True
        assert result.metadata.get("job_id") == "job-123"
        assert len(result.rows) == 2

        # Verify S3 cleanup was called
        mock_s3.delete_object.assert_called_once()

    @patch("statements.ocr_worker.time.sleep")
    @patch("statements.ocr_worker.boto3")
    def test_failed_async_job_raises(self, mock_boto3, mock_sleep):
        """Async job that fails → RuntimeError."""
        mock_settings = _make_settings()
        mock_s3 = MagicMock()
        mock_textract = MagicMock()
        mock_textract.start_document_analysis.return_value = {"JobId": "job-fail"}
        mock_textract.get_document_analysis.return_value = {
            "JobStatus": "FAILED",
            "StatusMessage": "Invalid document format",
        }

        def client_factory(service, **kwargs):
            if service == "s3":
                return mock_s3
            return mock_textract

        mock_boto3.client.side_effect = client_factory

        engine = TextractAsyncOCREngine()
        engine.INITIAL_WAIT_SECONDS = 0.01

        with patch(SETTINGS_PATH, mock_settings):
            with pytest.raises(RuntimeError, match="Textract async job failed"):
                engine.extract(Path("/tmp/test.pdf"))

        # S3 cleanup should still happen (in finally block)
        mock_s3.delete_object.assert_called_once()

    @patch("statements.ocr_worker.time.sleep")
    @patch("statements.ocr_worker.boto3")
    def test_pagination_collects_all_blocks(self, mock_boto3, mock_sleep):
        """Async job with multiple result pages (NextToken) collects all blocks."""
        mock_settings = _make_settings()
        mock_s3 = MagicMock()
        mock_textract = MagicMock()
        mock_textract.start_document_analysis.return_value = {"JobId": "job-pag"}

        # First poll succeeds but has NextToken
        page1_blocks = SAMPLE_TEXTRACT_RESPONSE["Blocks"][:6]  # first half
        page2_blocks = SAMPLE_TEXTRACT_RESPONSE["Blocks"][6:]  # second half

        mock_textract.get_document_analysis.side_effect = [
            # First poll: SUCCEEDED with NextToken
            {
                "JobStatus": "SUCCEEDED",
                "Blocks": page1_blocks,
                "DocumentMetadata": {"Pages": 1},
                "NextToken": "token-2",
            },
            # Paginated fetch
            {
                "Blocks": page2_blocks,
                # No NextToken = done
            },
        ]

        def client_factory(service, **kwargs):
            if service == "s3":
                return mock_s3
            return mock_textract

        mock_boto3.client.side_effect = client_factory

        engine = TextractAsyncOCREngine()
        engine.INITIAL_WAIT_SECONDS = 0.01

        with patch(SETTINGS_PATH, mock_settings):
            result = engine.extract(Path("/tmp/test.pdf"))

        assert isinstance(result, OCRResult)
        # Verify get_document_analysis was called twice (poll + pagination)
        assert mock_textract.get_document_analysis.call_count == 2
