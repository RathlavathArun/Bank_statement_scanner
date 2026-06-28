"""
Tests for the config-driven OCR engine selection logic.

Verifies that ``get_ocr_engine()`` returns the correct engine class based on
the ``OCR_ENGINE`` setting, credential availability, and Tesseract binary
presence — matching the Option C behaviour matrix in the implementation plan.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ── Helpers ──────────────────────────────────────────────────────

SETTINGS_PATH = "core.config.settings"


def _make_settings(**overrides):
    """Create a mock settings object with defaults + overrides."""
    defaults = {
        "OCR_ENGINE": "auto",
        "TEXTRACT_REGION": "ap-south-1",
        "TEXTRACT_S3_BUCKET": "",
        "TEXTRACT_ASYNC_ENABLED": False,
        "TEXTRACT_FEATURE_TYPES": "TABLES",
        "AWS_ACCESS_KEY_ID": "",
        "AWS_SECRET_ACCESS_KEY": "",
        "AWS_DEFAULT_REGION": "ap-south-1",
        "S3_BUCKET": "bank-statements",
    }
    defaults.update(overrides)
    mock = MagicMock()
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


# ── Test matrix ──────────────────────────────────────────────────


class TestGetOCREngine:
    """Engine selection test cases from the implementation plan."""

    @patch("statements.ocr_worker.shutil.which", return_value="/usr/bin/tesseract")
    @patch("statements.ocr_worker._textract_credentials_available", return_value=True)
    def test_textract_forced_with_creds(self, _mock_creds, _mock_which):
        """OCR_ENGINE=textract + AWS creds → TextractOCREngine."""
        from statements.ocr_worker import TextractOCREngine, get_ocr_engine

        with patch(SETTINGS_PATH, _make_settings(OCR_ENGINE="textract")):
            engine = get_ocr_engine()
        assert isinstance(engine, TextractOCREngine)

    @patch("statements.ocr_worker.shutil.which", return_value="/usr/bin/tesseract")
    @patch("statements.ocr_worker._textract_credentials_available", return_value=False)
    def test_textract_forced_no_creds_raises(self, _mock_creds, _mock_which):
        """OCR_ENGINE=textract + no AWS creds → RuntimeError."""
        from statements.ocr_worker import get_ocr_engine

        with patch(SETTINGS_PATH, _make_settings(OCR_ENGINE="textract")):
            with pytest.raises(RuntimeError, match="no valid AWS credentials"):
                get_ocr_engine()

    @patch("statements.ocr_worker.shutil.which", return_value="/usr/bin/tesseract")
    @patch("statements.ocr_worker._textract_credentials_available", return_value=True)
    def test_auto_with_creds(self, _mock_creds, _mock_which):
        """OCR_ENGINE=auto + AWS creds → TextractOCREngine (preferred)."""
        from statements.ocr_worker import TextractOCREngine, get_ocr_engine

        with patch(SETTINGS_PATH, _make_settings(OCR_ENGINE="auto")):
            engine = get_ocr_engine()
        assert isinstance(engine, TextractOCREngine)

    @patch("statements.ocr_worker.shutil.which", return_value="/usr/bin/tesseract")
    @patch("statements.ocr_worker._textract_credentials_available", return_value=False)
    def test_auto_no_creds_falls_back_to_tesseract(self, _mock_creds, _mock_which):
        """OCR_ENGINE=auto + no AWS creds → TesseractOCREngine (fallback)."""
        from statements.ocr_worker import TesseractOCREngine, get_ocr_engine

        with patch(SETTINGS_PATH, _make_settings(OCR_ENGINE="auto")):
            engine = get_ocr_engine()
        assert isinstance(engine, TesseractOCREngine)

    @patch("statements.ocr_worker.shutil.which", return_value="/usr/bin/tesseract")
    @patch("statements.ocr_worker._textract_credentials_available", return_value=True)
    def test_tesseract_forced(self, _mock_creds, _mock_which):
        """OCR_ENGINE=tesseract → TesseractOCREngine (ignores available creds)."""
        from statements.ocr_worker import TesseractOCREngine, get_ocr_engine

        with patch(SETTINGS_PATH, _make_settings(OCR_ENGINE="tesseract")):
            engine = get_ocr_engine()
        assert isinstance(engine, TesseractOCREngine)

    @patch("statements.ocr_worker.shutil.which", return_value=None)
    @patch("statements.ocr_worker._textract_credentials_available", return_value=False)
    def test_nothing_available_raises(self, _mock_creds, _mock_which):
        """OCR_ENGINE=auto + no creds + no Tesseract → RuntimeError."""
        from statements.ocr_worker import get_ocr_engine

        with patch(SETTINGS_PATH, _make_settings(OCR_ENGINE="auto")):
            with pytest.raises(RuntimeError, match="No OCR engine available"):
                get_ocr_engine()

    @patch("statements.ocr_worker.shutil.which", return_value="/usr/bin/tesseract")
    @patch("statements.ocr_worker._textract_credentials_available", return_value=True)
    def test_auto_with_async_enabled(self, _mock_creds, _mock_which):
        """OCR_ENGINE=auto + creds + TEXTRACT_ASYNC_ENABLED=True → TextractAsyncOCREngine."""
        from statements.ocr_worker import TextractAsyncOCREngine, get_ocr_engine

        with patch(
            SETTINGS_PATH,
            _make_settings(OCR_ENGINE="auto", TEXTRACT_ASYNC_ENABLED=True),
        ):
            engine = get_ocr_engine()
        assert isinstance(engine, TextractAsyncOCREngine)

    @patch("statements.ocr_worker.shutil.which", return_value=None)
    def test_tesseract_forced_no_binary_raises(self, _mock_which):
        """OCR_ENGINE=tesseract + no binary → RuntimeError."""
        from statements.ocr_worker import get_ocr_engine

        with patch(SETTINGS_PATH, _make_settings(OCR_ENGINE="tesseract")):
            with pytest.raises(RuntimeError, match="Tesseract binary not found"):
                get_ocr_engine()


class TestTextractCredentialsAvailable:
    """Tests for the _textract_credentials_available helper."""

    @patch("statements.ocr_worker.boto3")
    def test_returns_true_when_identity_succeeds(self, mock_boto3):
        """Valid STS GetCallerIdentity → True."""
        from statements.ocr_worker import _textract_credentials_available

        mock_sts = MagicMock()
        mock_boto3.client.return_value = mock_sts

        with patch(
            SETTINGS_PATH,
            _make_settings(AWS_ACCESS_KEY_ID="AKIA...", AWS_SECRET_ACCESS_KEY="secret"),
        ):
            assert _textract_credentials_available() is True

    @patch("statements.ocr_worker.boto3")
    def test_returns_false_when_identity_fails(self, mock_boto3):
        """STS raises → False."""
        from statements.ocr_worker import _textract_credentials_available

        mock_sts = MagicMock()
        mock_sts.get_caller_identity.side_effect = Exception("no creds")
        mock_boto3.client.return_value = mock_sts

        with patch(SETTINGS_PATH, _make_settings()):
            assert _textract_credentials_available() is False
