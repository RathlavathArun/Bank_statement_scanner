"""
OCR engine for scanned PDF bank statements.

Provides two backends:
  1. TesseractOCREngine – local OpenCV pre-processing + Tesseract OCR
  2. TextractOCREngine – AWS Textract (TABLE analysis)

The module picks the best available engine automatically via ``get_ocr_engine()``.
Entry point: ``process_scanned_pdf(file_path, on_progress)`` → ``OCRResult``.
"""
from __future__ import annotations

import abc
import logging
import shutil
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

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
    """OpenCV pre-processing + Tesseract OCR.

    Pipeline per page:
      1. ``pdf2image.convert_from_path`` → PIL images
      2. Grayscale → bilateral denoise → adaptive threshold → deskew
      3. ``pytesseract.image_to_data`` with per-word confidence
      4. Group words into rows (y-coordinate clustering) then cells (x-gap splitting)
    """

    # Pixels – words whose y-centres are within this tolerance are the same row.
    Y_CLUSTER_TOLERANCE = 10
    # Pixels – gap between consecutive words that triggers a new cell.
    X_GAP_THRESHOLD = 30

    def extract(self, file_path: Path, on_progress: Callable | None = None) -> OCRResult:
        import cv2
        import numpy as np
        import pytesseract
        from pdf2image import convert_from_path

        images = convert_from_path(str(file_path), dpi=300)
        all_rows: list[OCRRow] = []

        for page_idx, pil_image in enumerate(images, start=1):
            if on_progress:
                on_progress(page_idx, len(images))

            img = np.array(pil_image)
            processed = self._preprocess(img)
            words = self._run_tesseract(processed)
            rows = self._group_into_rows(words, page_number=page_idx)
            all_rows.extend(rows)

        return OCRResult(
            rows=all_rows,
            pages_processed=len(images),
            engine_used="tesseract",
            metadata={"dpi": 300},
        )

    # ── image pre-processing ────────────────────────────────────

    @staticmethod
    def _preprocess(img):
        """Grayscale → denoise → adaptive threshold → deskew."""
        import cv2
        import numpy as np

        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if len(img.shape) == 3 else img
        denoised = cv2.bilateralFilter(gray, d=9, sigmaColor=75, sigmaSpace=75)
        thresh = cv2.adaptiveThreshold(
            denoised, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=11,
            C=2,
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

    # ── Tesseract execution ─────────────────────────────────────

    @staticmethod
    def _run_tesseract(image) -> list[dict]:
        """Run Tesseract and return a list of word dicts with confidence + bbox."""
        import pytesseract

        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
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

    # ── Grouping words → rows → cells ───────────────────────────

    @classmethod
    def _group_into_rows(cls, words: list[dict], page_number: int) -> list[OCRRow]:
        """Cluster words by y-centre then split into cells by x-gap."""
        if not words:
            return []

        # Sort by y-centre
        for w in words:
            w["y_centre"] = w["y"] + w["h"] // 2
        words.sort(key=lambda w: (w["y_centre"], w["x"]))

        # Cluster into rows
        row_clusters: list[list[dict]] = []
        current_cluster: list[dict] = [words[0]]
        for w in words[1:]:
            if abs(w["y_centre"] - current_cluster[-1]["y_centre"]) <= cls.Y_CLUSTER_TOLERANCE:
                current_cluster.append(w)
            else:
                row_clusters.append(current_cluster)
                current_cluster = [w]
        row_clusters.append(current_cluster)

        ocr_rows: list[OCRRow] = []
        for cluster in row_clusters:
            cluster.sort(key=lambda w: w["x"])
            cells = cls._split_into_cells(cluster)
            if not cells:
                continue
            row_conf = statistics.mean(c.confidence for c in cells) if cells else 0.0
            ocr_rows.append(OCRRow(cells=cells, page_number=page_number, row_confidence=row_conf))

        return ocr_rows

    @classmethod
    def _split_into_cells(cls, sorted_words: list[dict]) -> list[OCRCell]:
        """Split a horizontal strip of words into cells based on x-gaps."""
        if not sorted_words:
            return []

        groups: list[list[dict]] = [[sorted_words[0]]]
        for w in sorted_words[1:]:
            prev = groups[-1][-1]
            gap = w["x"] - (prev["x"] + prev["w"])
            if gap > cls.X_GAP_THRESHOLD:
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


# ── Textract engine ─────────────────────────────────────────────


class TextractOCREngine(OCREngine):
    """AWS Textract TABLE analysis fallback.

    Sends the document to Textract with ``FeatureTypes=['TABLES']`` and
    maps the TABLE/CELL blocks into ``OCRResult``.
    """

    def extract(self, file_path: Path, on_progress: Callable | None = None) -> OCRResult:
        import boto3

        client = boto3.client("textract")

        with open(file_path, "rb") as f:
            doc_bytes = f.read()

        try:
            response = client.analyze_document(
                Document={"Bytes": doc_bytes},
                FeatureTypes=["TABLES"],
            )
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


# ── Engine selection & entry point ──────────────────────────────


def get_ocr_engine() -> OCREngine:
    """Return the best available OCR engine.

    Priority:
      1. Tesseract (local) – checked via ``shutil.which('tesseract')``
      2. AWS Textract       – checked via boto3 credential chain
    """
    if shutil.which("tesseract"):
        logger.info("Using Tesseract OCR engine (local).")
        return TesseractOCREngine()

    # Try Textract – verify credentials are usable
    try:
        import boto3
        sts = boto3.client("sts")
        sts.get_caller_identity()
        logger.info("Using AWS Textract OCR engine.")
        return TextractOCREngine()
    except Exception:
        pass

    raise RuntimeError(
        "No OCR engine available. Install Tesseract (apt install tesseract-ocr / brew install tesseract) "
        "or configure AWS credentials for Textract."
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
