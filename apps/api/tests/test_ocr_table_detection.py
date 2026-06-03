"""
Tests for OCR table grid detection, cell-by-cell OCR, quality-aware
preprocessing, and dynamic clustering thresholds.

All tests use synthetic images — no external files or Tesseract binary required.
"""

import statistics
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers to create synthetic images ─────────────────────────


def _make_table_image(
    rows: int = 5,
    cols: int = 4,
    cell_width: int = 150,
    cell_height: int = 40,
    line_thickness: int = 2,
):
    """Create a synthetic binary image containing a table grid.

    Returns a white image (255) with black (0) grid lines.
    """
    import cv2
    import numpy as np

    margin = 20
    width = margin * 2 + cols * cell_width
    height = margin * 2 + rows * cell_height
    img = np.ones((height, width), dtype=np.uint8) * 255

    # Draw horizontal lines
    for r in range(rows + 1):
        y = margin + r * cell_height
        cv2.line(img, (margin, y), (width - margin, y), 0, line_thickness)

    # Draw vertical lines
    for c in range(cols + 1):
        x = margin + c * cell_width
        cv2.line(img, (x, margin), (x, height - margin), 0, line_thickness)

    return img


def _make_blank_image(width: int = 800, height: int = 600):
    """Create a plain white image with no table lines."""
    import numpy as np

    return np.ones((height, width), dtype=np.uint8) * 255


def _make_text_only_image(width: int = 800, height: int = 600):
    """Create a white image with some scattered text-like marks but no table lines."""
    import cv2
    import numpy as np

    img = np.ones((height, width), dtype=np.uint8) * 255
    # Draw some small rectangles to simulate text blobs
    for y_offset in range(0, height - 40, 50):
        for x_offset in range(0, width - 100, 150):
            cv2.rectangle(img, (x_offset + 10, y_offset + 10), (x_offset + 80, y_offset + 25), 0, -1)
    return img


# ── Test: Table grid detection ──────────────────────────────────


class TestTableGridDetection:
    """Tests for TesseractOCREngine._detect_table_grid()."""

    def test_detects_grid_in_synthetic_table(self):
        from statements.ocr_worker import TesseractOCREngine

        img = _make_table_image(rows=5, cols=4)
        grid = TesseractOCREngine._detect_table_grid(img)

        assert grid is not None, "Should detect grid in a synthetic table image"
        assert len(grid) >= 4, f"Should detect at least 4 rows, got {len(grid)}"
        # Each row should have roughly 4 cells
        for row in grid:
            assert len(row) >= 3, f"Each row should have at least 3 cells, got {len(row)}"

    def test_no_grid_on_blank_image(self):
        from statements.ocr_worker import TesseractOCREngine

        img = _make_blank_image()
        grid = TesseractOCREngine._detect_table_grid(img)

        assert grid is None, "Should not detect grid in a blank image"

    def test_no_grid_on_text_only_image(self):
        from statements.ocr_worker import TesseractOCREngine

        img = _make_text_only_image()
        grid = TesseractOCREngine._detect_table_grid(img)

        assert grid is None, "Should not detect grid in text-only image"

    def test_grid_cell_bboxes_are_valid(self):
        from statements.ocr_worker import TesseractOCREngine

        img = _make_table_image(rows=3, cols=3, cell_width=200, cell_height=60)
        grid = TesseractOCREngine._detect_table_grid(img)

        assert grid is not None
        for row in grid:
            for cell in row:
                assert "x1" in cell and "y1" in cell
                assert "x2" in cell and "y2" in cell
                assert cell["x2"] > cell["x1"], "Cell width must be positive"
                assert cell["y2"] > cell["y1"], "Cell height must be positive"

    def test_detects_large_table(self):
        from statements.ocr_worker import TesseractOCREngine

        img = _make_table_image(rows=25, cols=8, cell_width=100, cell_height=30)
        grid = TesseractOCREngine._detect_table_grid(img)

        assert grid is not None
        assert len(grid) >= 20, f"Should detect at least 20 rows in 25-row table, got {len(grid)}"


# ── Test: Find line positions helper ────────────────────────────


class TestFindLinePositions:
    """Tests for TesseractOCREngine._find_line_positions()."""

    def test_finds_lines_from_projection(self):
        import numpy as np
        from statements.ocr_worker import TesseractOCREngine

        # Simulate a projection with spikes at y=50, y=100, y=150
        projection = np.zeros(200, dtype=np.float64)
        for pos in [50, 100, 150]:
            projection[pos - 1:pos + 2] = 500.0

        positions = TesseractOCREngine._find_line_positions(projection, threshold=100.0, min_gap=10)

        assert len(positions) == 3
        for pos, expected in zip(positions, [50, 100, 150]):
            assert abs(pos - expected) <= 2

    def test_empty_projection_returns_empty(self):
        import numpy as np
        from statements.ocr_worker import TesseractOCREngine

        projection = np.zeros(200, dtype=np.float64)
        positions = TesseractOCREngine._find_line_positions(projection, threshold=100.0)

        assert positions == []

    def test_min_gap_filtering(self):
        import numpy as np
        from statements.ocr_worker import TesseractOCREngine

        # Two spikes only 5px apart — should be merged/filtered
        projection = np.zeros(200, dtype=np.float64)
        projection[50] = 500.0
        projection[53] = 500.0
        projection[100] = 500.0

        positions = TesseractOCREngine._find_line_positions(projection, threshold=100.0, min_gap=10)

        assert len(positions) == 2, "Close spikes should be filtered by min_gap"


# ── Test: Quality detection ─────────────────────────────────────


class TestQualityDetection:
    """Tests for TesseractOCREngine._is_clean_screenshot()."""

    def test_high_contrast_image_is_screenshot(self):
        """A purely black-and-white image (like a screenshot) should be detected as clean."""
        import numpy as np
        from statements.ocr_worker import TesseractOCREngine

        # Create an image that's 60% white (255) and 40% black (0) — very bimodal
        img = np.zeros((100, 100), dtype=np.uint8)
        img[:60, :] = 255

        result = TesseractOCREngine._is_clean_screenshot(img)
        assert result == True, f"Expected screenshot detection to return True, got {result}"

    def test_noisy_image_is_not_screenshot(self):
        """A noisy grayscale image should not be detected as a clean screenshot."""
        import numpy as np
        from statements.ocr_worker import TesseractOCREngine

        # Create a noisy image with values spread across the histogram
        rng = np.random.default_rng(42)
        img = rng.integers(50, 200, size=(100, 100), dtype=np.uint8)

        result = TesseractOCREngine._is_clean_screenshot(img)
        assert result == False, f"Expected noisy image to return False, got {result}"


# ── Test: Image upscaling ───────────────────────────────────────


class TestEnsureMinResolution:
    """Tests for TesseractOCREngine._ensure_min_resolution()."""

    def test_small_image_is_upscaled(self):
        import numpy as np
        from statements.ocr_worker import TesseractOCREngine

        img = np.zeros((500, 800, 3), dtype=np.uint8)
        result = TesseractOCREngine._ensure_min_resolution(img, min_height=1500)

        assert result.shape[0] >= 1500

    def test_large_image_not_upscaled(self):
        import numpy as np
        from statements.ocr_worker import TesseractOCREngine

        img = np.zeros((2000, 3000, 3), dtype=np.uint8)
        result = TesseractOCREngine._ensure_min_resolution(img, min_height=1500)

        assert result.shape[0] == 2000, "Image already exceeds min_height, should not change"


# ── Test: Quality-aware preprocessing ──────────────────────────


class TestPreprocess:
    """Tests for TesseractOCREngine._preprocess()."""

    def test_screenshot_mode_uses_otsu(self):
        """Screenshot preprocessing should produce a binary image."""
        import numpy as np
        from statements.ocr_worker import TesseractOCREngine

        img = np.zeros((100, 100, 3), dtype=np.uint8)
        img[:50, :] = 255

        result = TesseractOCREngine._preprocess(img, is_screenshot=True)

        # Should be binary (only 0 and 255)
        unique_vals = set(np.unique(result))
        assert unique_vals.issubset({0, 255})

    def test_scan_mode_uses_adaptive_threshold(self):
        """Scan preprocessing should also produce a binary-ish image."""
        import numpy as np
        from statements.ocr_worker import TesseractOCREngine

        rng = np.random.default_rng(42)
        img = rng.integers(50, 200, size=(100, 100, 3), dtype=np.uint8)

        result = TesseractOCREngine._preprocess(img, is_screenshot=False)

        # Should still be a valid image
        assert result.shape[0] == 100
        assert result.shape[1] == 100


# ── Test: Dynamic clustering (word grouping fallback) ──────────


class TestDynamicClustering:
    """Tests for TesseractOCREngine._group_into_rows() with dynamic thresholds."""

    def test_groups_words_into_rows_by_y(self):
        from statements.ocr_worker import TesseractOCREngine

        words = [
            {"text": "10/01/2026", "confidence": 0.9, "x": 10, "y": 100, "w": 80, "h": 20},
            {"text": "NEFT", "confidence": 0.9, "x": 200, "y": 102, "w": 40, "h": 20},
            {"text": "500.00", "confidence": 0.85, "x": 400, "y": 98, "w": 60, "h": 20},
            # Second row — different y
            {"text": "11/01/2026", "confidence": 0.9, "x": 10, "y": 160, "w": 80, "h": 20},
            {"text": "UPI", "confidence": 0.9, "x": 200, "y": 162, "w": 30, "h": 20},
            {"text": "1000.00", "confidence": 0.8, "x": 400, "y": 158, "w": 60, "h": 20},
        ]

        rows = TesseractOCREngine._group_into_rows(words, page_number=1)

        assert len(rows) == 2, f"Should group into 2 rows, got {len(rows)}"
        assert rows[0].page_number == 1
        assert rows[1].page_number == 1

    def test_slightly_misaligned_words_same_row(self):
        """Words with small y-offset (within dynamic tolerance) should stay in same row."""
        from statements.ocr_worker import TesseractOCREngine

        words = [
            {"text": "Hello", "confidence": 0.9, "x": 10, "y": 100, "w": 50, "h": 30},
            {"text": "World", "confidence": 0.9, "x": 100, "y": 108, "w": 50, "h": 30},  # 8px offset
        ]

        rows = TesseractOCREngine._group_into_rows(words, page_number=1)

        # With dynamic tolerance = max(10, 30 * 0.6) = 18px, an 8px offset should stay together
        assert len(rows) == 1, "Slightly misaligned words should be in the same row"

    def test_empty_words_returns_empty(self):
        from statements.ocr_worker import TesseractOCREngine

        rows = TesseractOCREngine._group_into_rows([], page_number=1)
        assert rows == []


# ── Test: Cell-by-cell OCR from grid ───────────────────────────


class TestOcrCellsFromGrid:
    """Tests for TesseractOCREngine._ocr_cells_from_grid()."""

    @patch("pytesseract.image_to_data")
    def test_ocr_cells_produces_rows(self, mock_ocr):
        from statements.ocr_worker import TesseractOCREngine
        import pytesseract

        # Mock Tesseract to return a single word per cell
        mock_ocr.return_value = {
            "text": ["Hello"],
            "conf": [90],
            "left": [0],
            "top": [0],
            "width": [50],
            "height": [20],
        }

        img = _make_table_image(rows=3, cols=3, cell_width=100, cell_height=40)
        grid = TesseractOCREngine._detect_table_grid(img)
        assert grid is not None

        rows = TesseractOCREngine._ocr_cells_from_grid(img, grid, page_number=1)

        assert len(rows) > 0
        for row in rows:
            assert row.page_number == 1
            assert len(row.cells) > 0
            for cell in row.cells:
                assert cell.text == "Hello"
                assert cell.confidence == 0.9

    @patch("pytesseract.image_to_data")
    def test_empty_cells_skipped_in_confidence(self, mock_ocr):
        from statements.ocr_worker import TesseractOCREngine

        # Mock: first cell has text, second is empty
        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] % 2 == 0:
                return {"text": [""], "conf": [-1], "left": [0], "top": [0], "width": [0], "height": [0]}
            return {"text": ["Data"], "conf": [85], "left": [0], "top": [0], "width": [50], "height": [20]}

        mock_ocr.side_effect = side_effect

        img = _make_table_image(rows=2, cols=2, cell_width=150, cell_height=50)
        grid = TesseractOCREngine._detect_table_grid(img)
        assert grid is not None

        rows = TesseractOCREngine._ocr_cells_from_grid(img, grid, page_number=1)

        # Rows should exist — empty cells don't prevent row creation
        assert len(rows) > 0


# ── Test: Tesseract PSM configuration ──────────────────────────


class TestTesseractConfig:
    """Tests that Tesseract is called with correct PSM modes."""

    @patch("pytesseract.image_to_data")
    def test_run_tesseract_uses_psm_6(self, mock_ocr):
        from statements.ocr_worker import TesseractOCREngine
        import pytesseract

        mock_ocr.return_value = {
            "text": ["test"],
            "conf": [90],
            "left": [0],
            "top": [0],
            "width": [50],
            "height": [20],
        }

        TesseractOCREngine._run_tesseract(_make_blank_image(), psm=6)

        mock_ocr.assert_called_once()
        call_kwargs = mock_ocr.call_args
        config = call_kwargs.kwargs.get("config", "") or (call_kwargs.args[1] if len(call_kwargs.args) > 1 else "")
        # Config should be passed as keyword arg
        assert "--psm 6" in str(call_kwargs)

    @patch("pytesseract.image_to_data")
    def test_cell_ocr_uses_psm_7(self, mock_ocr):
        from statements.ocr_worker import TesseractOCREngine

        mock_ocr.return_value = {
            "text": ["Cell"],
            "conf": [92],
            "left": [0],
            "top": [0],
            "width": [50],
            "height": [20],
        }

        img = _make_table_image(rows=2, cols=2, cell_width=150, cell_height=50)
        grid = TesseractOCREngine._detect_table_grid(img)
        assert grid is not None

        TesseractOCREngine._ocr_cells_from_grid(img, grid, page_number=1)

        # All cell OCR calls should use --psm 7
        for call in mock_ocr.call_args_list:
            config_str = str(call)
            assert "--psm 7" in config_str, f"Cell OCR should use --psm 7, got: {config_str}"


# ── Test: Auto-detect OCR columns ──────────────────────────────


class TestAutoDetectOcrColumns:
    """Tests for _auto_detect_ocr_columns() in parser.py."""

    def test_detects_icici_like_layout(self):
        from statements.parser import _auto_detect_ocr_columns

        # Simulated ICICI OCR output: S.No, Date, Particulars, Withdrawal, Deposit, Balance
        rows = [
            ["S No.", "Date", "Particulars", "Chq Num", "Withdrawal", "Deposit", "Balance"],
            ["1", "13/03/2026", "UPIAR/9438565/DR/NAREND", "", "100.00", "", "30,775.75"],
            ["2", "13/03/2026", "MSB/0476/NEFT", "", "", "25.00", "30,800.75"],
            ["3", "14/03/2026", "UPI/AMAZON", "", "1,000.00", "", "29,800.75"],
            ["4", "15/03/2026", "SALARY CREDIT", "", "", "50,000.00", "79,800.75"],
        ]

        date_formats = ["%d/%m/%Y", "%d/%m/%y"]
        result = _auto_detect_ocr_columns(rows, date_formats)

        assert result["date"] == 1, f"Date should be column 1, got {result['date']}"
        assert result["narration"] is not None, "Should detect a narration column"
        assert result["debit"] is not None, "Should detect a debit column"
        assert result["credit"] is not None, "Should detect a credit column"
        assert result["balance"] is not None, "Should detect a balance column"

    def test_detects_simple_layout(self):
        from statements.parser import _auto_detect_ocr_columns

        # Simple 4-column layout: Date, Description, Amount, Balance
        rows = [
            ["Date", "Description", "Amount", "Balance"],
            ["01/01/2026", "Grocery Purchase", "500.00", "10,000.00"],
            ["02/01/2026", "Online Transfer", "1,200.00", "8,800.00"],
        ]

        result = _auto_detect_ocr_columns(rows, ["%d/%m/%Y"])

        assert result["date"] == 0
        assert result["narration"] is not None

    def test_handles_empty_rows(self):
        from statements.parser import _auto_detect_ocr_columns

        result = _auto_detect_ocr_columns([], ["%d/%m/%Y"])
        assert result == {}

    def test_handles_single_column(self):
        from statements.parser import _auto_detect_ocr_columns

        rows = [["only_one_column"], ["data"]]
        result = _auto_detect_ocr_columns(rows, ["%d/%m/%Y"])
        assert result == {}
