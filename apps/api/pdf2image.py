"""Optional pdf2image compatibility shim for test and dev environments.

The real ``pdf2image`` package is declared in ``requirements.txt``. This shim
allows tests to patch ``pdf2image.convert_from_path`` even when optional OCR
dependencies are absent from the active Python environment.
"""


def convert_from_path(*args, **kwargs):
    raise RuntimeError(
        "pdf2image is not installed. Install apps/api requirements and Poppler "
        "before running live scanned-PDF OCR."
    )

