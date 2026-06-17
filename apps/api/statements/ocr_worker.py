"""
OCR engine for scanned PDF bank statements.

Provides three backends:
  1. TesseractOCREngine     – local OpenCV pre-processing + Tesseract OCR
  2. TextractOCREngine      – AWS Textract synchronous TABLE analysis (≤ 10 MB)
  3. TextractAsyncOCREngine – AWS Textract async S3-based analysis (any size)

Engine selection is controlled by the ``OCR_ENGINE`` setting:
  - ``textract``  → always use Textract (raises if no AWS credentials)
  - ``tesseract`` → always use local Tesseract
  - ``auto``      → try Textract first, fall back to Tesseract

Entry point: ``process_scanned_pdf(file_path, on_progress)`` → ``OCRResult``.
"""
from __future__ import annotations

import abc
import logging
import shutil
import statistics
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import boto3

logger = logging.getLogger(__name__)


# ── Data classes ────────────────────────────────────────────────


@dataclass
class OCRCell:
    """A single table cell extracted by OCR."""
    text: str
    confidence: float  # 0.0 to 1.0
    bbox: dict | None = None  # {x1, y1, x2, y2}


@dataclass
class OCRRow:
    """A row of cells extracted from a single page."""
    cells: list[OCRCell]
    page_number: int
    row_confidence: float  # average of cell confidences


@dataclass
class OCRResult:
    """Complete OCR output for a document."""
    rows: list[OCRRow]
    pages_processed: int
    engine_used: str  # 'tesseract' or 'textract'
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Abstract base ───────────────────────────────────────────────


class OCREngine(abc.ABC):
    """Interface every OCR backend must implement."""

    @abc.abstractmethod
    def extract(self, file_path: Path, on_progress: Callable | None = None) -> OCRResult:
        """Extract tabular data from *file_path* and return an ``OCRResult``."""


# ── Tesseract engine ───────────────────────────────────────────


class TesseractOCREngine(OCREngine):
    """OpenCV pre-processing + Tesseract OCR with table-grid awareness.

    Pipeline per page:
      1. ``pdf2image.convert_from_path`` → PIL images
      2. Quality-aware pre-processing (screenshot vs noisy scan)
      3. Attempt table grid detection via morphological line analysis
      4a. If grid found → crop individual cells → OCR each cell with ``--psm 7``
      4b. If no grid  → full-page ``image_to_data`` with ``--psm 6`` → dynamic
          word clustering into rows/cells
    """

    # Minimum pixels for a line to be considered a table border.
    MIN_LINE_LENGTH_RATIO = 0.03  # fraction of image width/height

    def extract(self, file_path: Path, on_progress: Callable | None = None) -> OCRResult:
        import numpy as np
        from pdf2image import convert_from_path

        images = convert_from_path(str(file_path), dpi=300)
        all_rows: list[OCRRow] = []

        for page_idx, pil_image in enumerate(images, start=1):
            if on_progress:
                on_progress(page_idx, len(images))

            img = np.array(pil_image)
            img = self._ensure_min_resolution(img)
            is_screenshot = self._is_clean_screenshot(img)
            processed = self._preprocess(img, is_screenshot=is_screenshot)

            # Try table-grid detection first
            grid_cells = self._detect_table_grid(processed)

            if grid_cells:
                logger.info(
                    "Page %d: detected table grid with %d cells across %d rows",
                    page_idx, sum(len(r) for r in grid_cells), len(grid_cells),
                )
                rows = self._ocr_cells_from_grid(processed, grid_cells, page_number=page_idx)
            else:
                logger.info("Page %d: no table grid detected, using word-clustering fallback", page_idx)
                words = self._run_tesseract(processed, psm=6)
                rows = self._group_into_rows(words, page_number=page_idx)

            all_rows.extend(rows)

        return OCRResult(
            rows=all_rows,
            pages_processed=len(images),
            engine_used="tesseract",
            metadata={"dpi": 300},
        )

    # ── Image quality detection ─────────────────────────────────

    @staticmethod
    def _is_clean_screenshot(img) -> bool:
        """Detect if the image is a clean digital screenshot vs a noisy scan.

        Clean screenshots have:
          - Very high contrast (bimodal histogram — mostly white/black)
          - Very low noise (small standard deviation in smooth regions)
        """
        import cv2
        import numpy as np

        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if len(img.shape) == 3 else img

        # Check contrast via histogram bimodality
        hist = cv2.calcHist([gray], [0], None, [256], [0, 256]).flatten()
        total_pixels = gray.shape[0] * gray.shape[1]

        # Fraction of pixels that are near-white (>240) or near-black (<15)
        extreme_ratio = (hist[:15].sum() + hist[240:].sum()) / total_pixels

        # Check noise level via Laplacian variance
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()

        # Screenshots: high contrast, moderate laplacian (sharp text, no noise)
        # Scans: lower contrast, higher noise in smooth areas
        is_clean = extreme_ratio > 0.45 and laplacian_var < 5000

        logger.debug(
            "Image quality: extreme_ratio=%.3f, laplacian_var=%.1f → %s",
            extreme_ratio, laplacian_var, "screenshot" if is_clean else "scan",
        )
        return is_clean

    # ── Image pre-processing ────────────────────────────────────

    @staticmethod
    def _ensure_min_resolution(img, min_height: int = 1500):
        """Upscale images that are too small for accurate OCR."""
        import cv2

        h, w = img.shape[:2]
        if h < min_height:
            scale = min_height / h
            img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            logger.debug("Upscaled image from %dx%d to %dx%d", w, h, img.shape[1], img.shape[0])
        return img

    @staticmethod
    def _preprocess(img, is_screenshot: bool = False):
        """Quality-aware pre-processing.

        - Screenshots (clean digital): light processing to preserve detail
        - Scans (noisy): heavier denoising + adaptive threshold
        """
        import cv2

        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if len(img.shape) == 3 else img

        if is_screenshot:
            # Clean screenshots: simple Otsu threshold — preserves table lines
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        else:
            # Noisy scans: denoise + adaptive threshold
            denoised = cv2.bilateralFilter(gray, d=9, sigmaColor=75, sigmaSpace=75)
            thresh = cv2.adaptiveThreshold(
                denoised, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                blockSize=15,
                C=4,
            )

        return TesseractOCREngine._deskew(thresh)

    @staticmethod
    def _deskew(image):
        """Straighten a slightly rotated scan using minAreaRect."""
        import cv2
        import numpy as np

        coords = np.column_stack(np.where(image > 0))
        if len(coords) < 5:
            return image
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
        if abs(angle) < 0.5:
            return image
        h, w = image.shape[:2]
        centre = (w // 2, h // 2)
        matrix = cv2.getRotationMatrix2D(centre, angle, 1.0)
        return cv2.warpAffine(
            image, matrix, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )

    # ── Table grid detection ────────────────────────────────────

    @classmethod
    def _detect_table_grid(cls, thresh_image) -> list[list[dict]] | None:
        """Detect table grid lines and return cell bounding boxes grouped by row.

        Uses morphological operations to find horizontal and vertical lines,
        then computes their intersections to derive cell boundaries.

        Returns:
            list of rows, each row is a list of cell dicts with {x1, y1, x2, y2}
            Returns None if no convincing table grid is found.
        """
        import cv2
        import numpy as np

        h, w = thresh_image.shape[:2]

        # Invert so lines become white (foreground)
        inverted = cv2.bitwise_not(thresh_image)

        # ── Detect horizontal lines ─────────────────────────────
        horiz_kernel_len = max(w // 20, 40)
        horiz_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (horiz_kernel_len, 1))
        horiz_mask = cv2.morphologyEx(inverted, cv2.MORPH_OPEN, horiz_kernel, iterations=2)

        # ── Detect vertical lines ───────────────────────────────
        vert_kernel_len = max(h // 20, 40)
        vert_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, vert_kernel_len))
        vert_mask = cv2.morphologyEx(inverted, cv2.MORPH_OPEN, vert_kernel, iterations=2)

        # ── Find line positions ─────────────────────────────────
        # Project horizontally and vertically to find line y/x positions
        horiz_proj = np.sum(horiz_mask, axis=1)
        vert_proj = np.sum(vert_mask, axis=0)

        # Threshold: a row/col has a line if projection exceeds 20% of dimension
        horiz_threshold = w * 0.15
        vert_threshold = h * 0.10

        horiz_line_ys = cls._find_line_positions(horiz_proj, horiz_threshold, min_gap=10)
        vert_line_xs = cls._find_line_positions(vert_proj, vert_threshold, min_gap=10)

        logger.debug(
            "Grid detection: %d horizontal lines, %d vertical lines",
            len(horiz_line_ys), len(vert_line_xs),
        )

        # Need at least 3 horizontal lines (top border, 1+ row divider, bottom border)
        # and at least 3 vertical lines (left border, 1+ column divider, right border)
        if len(horiz_line_ys) < 3 or len(vert_line_xs) < 3:
            return None

        # ── Build cell grid from line intersections ─────────────
        grid_rows: list[list[dict]] = []
        for row_idx in range(len(horiz_line_ys) - 1):
            y1 = horiz_line_ys[row_idx]
            y2 = horiz_line_ys[row_idx + 1]

            # Skip rows that are too thin (< 10px) — probably double-lines
            if y2 - y1 < 10:
                continue

            row_cells: list[dict] = []
            for col_idx in range(len(vert_line_xs) - 1):
                x1 = vert_line_xs[col_idx]
                x2 = vert_line_xs[col_idx + 1]

                # Skip columns that are too narrow (< 10px)
                if x2 - x1 < 10:
                    continue

                row_cells.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2})

            if row_cells:
                grid_rows.append(row_cells)

        if len(grid_rows) < 2:
            return None

        logger.info(
            "Table grid: %d rows × %d columns detected",
            len(grid_rows),
            len(grid_rows[0]) if grid_rows else 0,
        )
        return grid_rows

    @staticmethod
    def _find_line_positions(projection, threshold: float, min_gap: int = 10) -> list[int]:
        """Find the centre positions of lines from a 1D projection.

        Groups consecutive above-threshold positions and returns their midpoints,
        ensuring a minimum gap between detected lines.
        """
        import numpy as np

        above = np.where(projection > threshold)[0]
        if len(above) == 0:
            return []

        # Group consecutive positions
        groups: list[list[int]] = [[above[0]]]
        for pos in above[1:]:
            if pos - groups[-1][-1] <= 2:  # allow small gaps in the line
                groups[-1].append(pos)
            else:
                groups.append([pos])

        # Get midpoint of each group
        positions = [int(np.mean(group)) for group in groups]

        # Enforce minimum gap
        if len(positions) <= 1:
            return positions

        filtered = [positions[0]]
        for pos in positions[1:]:
            if pos - filtered[-1] >= min_gap:
                filtered.append(pos)

        return filtered

    # ── Cell-by-cell OCR from detected grid ─────────────────────

    @classmethod
    def _ocr_cells_from_grid(
        cls,
        thresh_image,
        grid_rows: list[list[dict]],
        page_number: int,
    ) -> list[OCRRow]:
        """OCR each cell individually for much higher accuracy.

        Each cell is cropped with padding, then run through Tesseract
        with ``--psm 7`` (single text line) for optimal recognition.
        """
        import cv2
        import pytesseract

        h, w = thresh_image.shape[:2]
        ocr_rows: list[OCRRow] = []
        padding = 4  # pixels of padding around each cell crop

        for row_cells in grid_rows:
            cells: list[OCRCell] = []
            for cell_bbox in row_cells:
                # Crop with padding, clamped to image bounds
                y1 = max(0, cell_bbox["y1"] + padding)
                y2 = min(h, cell_bbox["y2"] - padding)
                x1 = max(0, cell_bbox["x1"] + padding)
                x2 = min(w, cell_bbox["x2"] - padding)

                if y2 <= y1 or x2 <= x1:
                    cells.append(OCRCell(text="", confidence=0.0, bbox=cell_bbox))
                    continue

                cell_crop = thresh_image[y1:y2, x1:x2]

                # Add white border around the crop for better Tesseract accuracy
                border_size = 10
                cell_crop = cv2.copyMakeBorder(
                    cell_crop, border_size, border_size, border_size, border_size,
                    cv2.BORDER_CONSTANT, value=255,
                )

                # OCR this single cell with PSM 7 (single text line)
                try:
                    data = pytesseract.image_to_data(
                        cell_crop,
                        config="--psm 7 --oem 3",
                        output_type=pytesseract.Output.DICT,
                    )

                    # Extract words and confidence from this cell
                    words = []
                    confs = []
                    n_items = len(data["text"])
                    for i in range(n_items):
                        text = (data["text"][i] or "").strip()
                        conf = int(data["conf"][i])
                        if text and conf >= 0:
                            words.append(text)
                            confs.append(max(0.0, min(conf / 100.0, 1.0)))

                    cell_text = " ".join(words)
                    cell_conf = statistics.mean(confs) if confs else 0.0
                except Exception as exc:
                    logger.warning("Cell OCR failed at (%d,%d): %s", x1, y1, exc)
                    cell_text = ""
                    cell_conf = 0.0

                cells.append(OCRCell(
                    text=cell_text,
                    confidence=cell_conf,
                    bbox=cell_bbox,
                ))

            # Skip rows where all cells are empty (likely header borders, etc.)
            if any(c.text.strip() for c in cells):
                row_conf = statistics.mean(c.confidence for c in cells if c.text.strip()) if cells else 0.0
                ocr_rows.append(OCRRow(cells=cells, page_number=page_number, row_confidence=row_conf))

        return ocr_rows

    # ── Tesseract execution ─────────────────────────────────────

    @staticmethod
    def _run_tesseract(image, psm: int = 6) -> list[dict]:
        """Run Tesseract and return a list of word dicts with confidence + bbox."""
        import pytesseract

        config = f"--psm {psm} --oem 3"
        data = pytesseract.image_to_data(image, config=config, output_type=pytesseract.Output.DICT)
        words: list[dict] = []
        n_items = len(data["text"])
        for i in range(n_items):
            text = (data["text"][i] or "").strip()
            conf = int(data["conf"][i])
            if not text or conf < 0:
                continue
            words.append({
                "text": text,
                "confidence": max(0.0, min(conf / 100.0, 1.0)),
                "x": data["left"][i],
                "y": data["top"][i],
                "w": data["width"][i],
                "h": data["height"][i],
            })
        return words

    # ── Grouping words → rows → cells (fallback path) ──────────

    @classmethod
    def _group_into_rows(cls, words: list[dict], page_number: int) -> list[OCRRow]:
        """Cluster words by y-centre then split into cells by x-gap.

        Uses dynamic thresholds based on actual word metrics instead of
        fixed pixel values.
        """
        if not words:
            return []

        # Compute y-centre for each word
        for w in words:
            w["y_centre"] = w["y"] + w["h"] // 2
        words.sort(key=lambda w: (w["y_centre"], w["x"]))

        # Compute dynamic Y tolerance from median word height
        word_heights = [w["h"] for w in words]
        median_height = statistics.median(word_heights) if word_heights else 20
        y_tolerance = max(10, int(median_height * 0.6))

        # Compute dynamic X gap threshold from median word width
        word_widths = [w["w"] for w in words]
        median_width = statistics.median(word_widths) if word_widths else 30
        x_gap_threshold = max(20, int(median_width * 0.8))

        logger.debug(
            "Dynamic thresholds: y_tolerance=%d (median_h=%d), x_gap=%d (median_w=%d)",
            y_tolerance, median_height, x_gap_threshold, median_width,
        )

        # Cluster into rows
        row_clusters: list[list[dict]] = []
        current_cluster: list[dict] = [words[0]]
        for w in words[1:]:
            if abs(w["y_centre"] - current_cluster[-1]["y_centre"]) <= y_tolerance:
                current_cluster.append(w)
            else:
                row_clusters.append(current_cluster)
                current_cluster = [w]
        row_clusters.append(current_cluster)

        ocr_rows: list[OCRRow] = []
        for cluster in row_clusters:
            cluster.sort(key=lambda w: w["x"])
            cells = cls._split_into_cells(cluster, x_gap_threshold)
            if not cells:
                continue
            row_conf = statistics.mean(c.confidence for c in cells) if cells else 0.0
            ocr_rows.append(OCRRow(cells=cells, page_number=page_number, row_confidence=row_conf))

        return ocr_rows

    @classmethod
    def _split_into_cells(cls, sorted_words: list[dict], x_gap_threshold: int = 30) -> list[OCRCell]:
        """Split a horizontal strip of words into cells based on x-gaps."""
        if not sorted_words:
            return []

        groups: list[list[dict]] = [[sorted_words[0]]]
        for w in sorted_words[1:]:
            prev = groups[-1][-1]
            gap = w["x"] - (prev["x"] + prev["w"])
            if gap > x_gap_threshold:
                groups.append([w])
            else:
                groups[-1].append(w)

        cells: list[OCRCell] = []
        for group in groups:
            text = " ".join(w["text"] for w in group)
            conf = statistics.mean(w["confidence"] for w in group) if group else 0.0
            x1 = group[0]["x"]
            y1 = min(w["y"] for w in group)
            x2 = max(w["x"] + w["w"] for w in group)
            y2 = max(w["y"] + w["h"] for w in group)
            cells.append(OCRCell(text=text, confidence=conf, bbox={"x1": x1, "y1": y1, "x2": x2, "y2": y2}))

        return cells


# ── Textract engine (synchronous — ≤ 10 MB) ────────────────────


def _get_textract_feature_types() -> list[str]:
    """Parse the TEXTRACT_FEATURE_TYPES setting into a list."""
    from core.config import settings
    raw = settings.TEXTRACT_FEATURE_TYPES
    return [ft.strip().upper() for ft in raw.split(",") if ft.strip()]


class TextractOCREngine(OCREngine):
    """AWS Textract synchronous TABLE/FORMS analysis.

    Sends the document to Textract with ``analyze_document`` (sync API).
    Limited to documents ≤ 10 MB. For larger files use ``TextractAsyncOCREngine``.
    """

    def extract(self, file_path: Path, on_progress: Callable | None = None) -> OCRResult:
        from botocore.exceptions import ClientError
        from core.config import settings

        client = boto3.client(
            "textract",
            region_name=settings.TEXTRACT_REGION or settings.AWS_DEFAULT_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
        )

        with open(file_path, "rb") as f:
            doc_bytes = f.read()

        feature_types = _get_textract_feature_types()

        try:
            response = client.analyze_document(
                Document={"Bytes": doc_bytes},
                FeatureTypes=feature_types,
            )
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code == "ThrottlingException":
                raise RuntimeError(
                    "AWS Textract throttled — too many concurrent requests. "
                    "Retry after a short delay or reduce concurrency."
                ) from exc
            elif error_code in ("AccessDeniedException", "UnrecognizedClientException"):
                raise RuntimeError(
                    f"AWS Textract auth error ({error_code}). "
                    "Check AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY."
                ) from exc
            elif error_code == "DocumentTooLargeException":
                raise RuntimeError(
                    "Document exceeds 10 MB sync limit. "
                    "Enable TEXTRACT_ASYNC_ENABLED=true to use async S3-based processing."
                ) from exc
            else:
                raise RuntimeError(
                    f"AWS Textract analysis failed ({error_code}): {exc}."
                ) from exc
        except Exception as exc:
            raise RuntimeError(
                f"AWS Textract analysis failed: {exc}. "
                "Ensure valid AWS credentials are configured and the document is ≤ 10 MB."
            ) from exc

        return self._parse_response(response)

    # ── response parsing ────────────────────────────────────────

    @staticmethod
    def _parse_response(response: dict) -> OCRResult:
        """Walk Textract blocks and build OCRRows from TABLE → CELL hierarchy."""
        blocks_by_id: dict[str, dict] = {b["Id"]: b for b in response.get("Blocks", [])}

        table_blocks = [b for b in response["Blocks"] if b["BlockType"] == "TABLE"]
        all_rows: list[OCRRow] = []

        for table in table_blocks:
            page_number = table.get("Page", 1)
            # Collect cells grouped by RowIndex
            rows_map: dict[int, list[dict]] = {}
            for rel in table.get("Relationships", []):
                if rel["Type"] != "CHILD":
                    continue
                for child_id in rel["Ids"]:
                    cell = blocks_by_id.get(child_id)
                    if cell and cell["BlockType"] == "CELL":
                        row_idx = cell.get("RowIndex", 0)
                        rows_map.setdefault(row_idx, []).append(cell)

            for row_idx in sorted(rows_map):
                cells_raw = sorted(rows_map[row_idx], key=lambda c: c.get("ColumnIndex", 0))
                ocr_cells: list[OCRCell] = []
                for cell_block in cells_raw:
                    text = TextractOCREngine._cell_text(cell_block, blocks_by_id)
                    # Textract confidence is 0-100; normalise to 0-1
                    conf = cell_block.get("Confidence", 0.0) / 100.0
                    bbox_raw = cell_block.get("Geometry", {}).get("BoundingBox", {})
                    bbox = {
                        "x1": bbox_raw.get("Left", 0),
                        "y1": bbox_raw.get("Top", 0),
                        "x2": bbox_raw.get("Left", 0) + bbox_raw.get("Width", 0),
                        "y2": bbox_raw.get("Top", 0) + bbox_raw.get("Height", 0),
                    } if bbox_raw else None
                    ocr_cells.append(OCRCell(text=text, confidence=conf, bbox=bbox))

                if ocr_cells:
                    row_conf = statistics.mean(c.confidence for c in ocr_cells)
                    all_rows.append(OCRRow(cells=ocr_cells, page_number=page_number, row_confidence=row_conf))

        return OCRResult(
            rows=all_rows,
            pages_processed=response.get("DocumentMetadata", {}).get("Pages", 1),
            engine_used="textract",
            metadata={"request_id": response.get("ResponseMetadata", {}).get("RequestId")},
        )

    @staticmethod
    def _cell_text(cell_block: dict, blocks_by_id: dict[str, dict]) -> str:
        """Concatenate WORD children of a CELL block."""
        parts: list[str] = []
        for rel in cell_block.get("Relationships", []):
            if rel["Type"] != "CHILD":
                continue
            for child_id in rel["Ids"]:
                word = blocks_by_id.get(child_id)
                if word and word["BlockType"] == "WORD":
                    parts.append(word.get("Text", ""))
        return " ".join(parts)


# ── Textract async engine (S3-based — any size) ────────────────


class TextractAsyncOCREngine(OCREngine):
    """AWS Textract asynchronous S3-based analysis.

    For documents of any size — uploads to S3, starts an async analysis job,
    polls for completion with exponential back-off, then retrieves and
    paginates through results.

    Pipeline:
      1. Upload PDF to S3 (TEXTRACT_S3_BUCKET or S3_BUCKET)
      2. start_document_analysis → get JobId
      3. Poll get_document_analysis until status != IN_PROGRESS
      4. Paginate all result pages via NextToken
      5. Parse through shared _parse_response() logic
      6. Delete the S3 object (clean up)
    """

    # Polling configuration
    INITIAL_WAIT_SECONDS = 5
    MAX_WAIT_SECONDS = 60
    MAX_POLL_ATTEMPTS = 60  # ~15 min with exponential backoff

    def extract(self, file_path: Path, on_progress: Callable | None = None) -> OCRResult:
        from core.config import settings

        region = settings.TEXTRACT_REGION or settings.AWS_DEFAULT_REGION
        s3_bucket = settings.TEXTRACT_S3_BUCKET or settings.S3_BUCKET
        feature_types = _get_textract_feature_types()

        s3_client = boto3.client(
            "s3",
            region_name=region,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
        )
        textract_client = boto3.client(
            "textract",
            region_name=region,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
        )

        # 1. Upload to S3
        s3_key = f"textract-jobs/{uuid.uuid4().hex}/{file_path.name}"
        logger.info("Uploading %s to s3://%s/%s for async Textract", file_path.name, s3_bucket, s3_key)
        s3_client.upload_file(str(file_path), s3_bucket, s3_key)

        try:
            # 2. Start async analysis
            start_resp = textract_client.start_document_analysis(
                DocumentLocation={"S3Object": {"Bucket": s3_bucket, "Name": s3_key}},
                FeatureTypes=feature_types,
            )
            job_id = start_resp["JobId"]
            logger.info("Textract async job started: %s", job_id)

            # 3. Poll with exponential back-off
            wait = self.INITIAL_WAIT_SECONDS
            for attempt in range(self.MAX_POLL_ATTEMPTS):
                time.sleep(wait)
                poll_resp = textract_client.get_document_analysis(JobId=job_id)
                status = poll_resp["JobStatus"]

                if status == "SUCCEEDED":
                    logger.info("Textract job %s succeeded on poll attempt %d", job_id, attempt + 1)
                    break
                elif status == "FAILED":
                    msg = poll_resp.get("StatusMessage", "Unknown error")
                    raise RuntimeError(f"Textract async job failed: {msg}")
                elif status == "IN_PROGRESS":
                    if on_progress:
                        on_progress(attempt + 1, self.MAX_POLL_ATTEMPTS)
                    wait = min(wait * 1.5, self.MAX_WAIT_SECONDS)
                else:
                    raise RuntimeError(f"Unexpected Textract job status: {status}")
            else:
                raise RuntimeError(
                    f"Textract async job {job_id} timed out after {self.MAX_POLL_ATTEMPTS} polls."
                )

            # 4. Paginate through all result pages
            all_blocks: list[dict] = poll_resp.get("Blocks", [])
            doc_metadata = poll_resp.get("DocumentMetadata", {})
            next_token = poll_resp.get("NextToken")

            while next_token:
                page_resp = textract_client.get_document_analysis(
                    JobId=job_id, NextToken=next_token
                )
                all_blocks.extend(page_resp.get("Blocks", []))
                next_token = page_resp.get("NextToken")

            # 5. Build a synthetic response dict matching sync format
            combined_response = {
                "Blocks": all_blocks,
                "DocumentMetadata": doc_metadata,
                "ResponseMetadata": {"RequestId": job_id},
            }
            result = TextractOCREngine._parse_response(combined_response)
            result.metadata["async"] = True
            result.metadata["job_id"] = job_id
            return result

        finally:
            # 6. Clean up S3 object
            try:
                s3_client.delete_object(Bucket=s3_bucket, Key=s3_key)
                logger.info("Cleaned up s3://%s/%s", s3_bucket, s3_key)
            except Exception as cleanup_exc:
                logger.warning("Failed to clean up S3 object %s: %s", s3_key, cleanup_exc)


# ── Credential check helper ─────────────────────────────────────


def _textract_credentials_available() -> bool:
    """Check whether usable AWS credentials exist for Textract.

    Uses STS GetCallerIdentity as a lightweight credential probe.
    Returns True if credentials are valid, False otherwise.
    """
    try:
        from core.config import settings

        sts = boto3.client(
            "sts",
            region_name=settings.AWS_DEFAULT_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
        )
        sts.get_caller_identity()
        return True
    except Exception as exc:
        logger.debug("AWS credential check failed: %s", exc)
        return False


# ── Engine selection & entry point ──────────────────────────────


def get_ocr_engine() -> OCREngine:
    """Return the OCR engine based on the ``OCR_ENGINE`` setting.

    Selection logic (Option C — config-driven):
      - ``textract``  → force Textract; raise if no credentials
      - ``tesseract`` → force local Tesseract; raise if binary not found
      - ``auto``      → try Textract first, fall back to Tesseract

    When Textract is selected and ``TEXTRACT_ASYNC_ENABLED`` is True,
    returns a ``TextractAsyncOCREngine`` instead of the sync variant.
    """
    from core.config import settings

    mode = settings.OCR_ENGINE.lower().strip()

    if mode == "tesseract":
        if shutil.which("tesseract"):
            logger.info("Using Tesseract OCR engine (forced via OCR_ENGINE=tesseract).")
            return TesseractOCREngine()
        raise RuntimeError(
            "OCR_ENGINE=tesseract but Tesseract binary not found. "
            "Install it: apt install tesseract-ocr / brew install tesseract"
        )

    if mode in ("textract", "auto"):
        if _textract_credentials_available():
            if settings.TEXTRACT_ASYNC_ENABLED:
                logger.info("Using TextractAsync OCR engine (S3-based, async).")
                return TextractAsyncOCREngine()
            logger.info("Using Textract OCR engine (sync).")
            return TextractOCREngine()
        if mode == "textract":
            raise RuntimeError(
                "OCR_ENGINE=textract but no valid AWS credentials found. "
                "Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY, or use OCR_ENGINE=auto."
            )
        # mode == "auto": fall through to Tesseract
        logger.info("Textract credentials unavailable, falling back to Tesseract.")

    # Fallback: local Tesseract
    if shutil.which("tesseract"):
        logger.warning("Falling back to local Tesseract OCR engine.")
        return TesseractOCREngine()

    raise RuntimeError(
        "No OCR engine available. Set AWS credentials for Textract "
        "or install Tesseract (apt install tesseract-ocr / brew install tesseract)."
    )


def process_scanned_pdf(
    file_path: Path,
    on_progress: Callable | None = None,
) -> OCRResult:
    """Main entry point for OCR processing of scanned PDF bank statements.

    Selects the best available engine and extracts tabular data.
    """
    engine = get_ocr_engine()
    logger.info("OCR processing %s with engine=%s", file_path.name, engine.__class__.__name__)
    return engine.extract(file_path, on_progress=on_progress)
