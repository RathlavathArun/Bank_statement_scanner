"""Optional pytesseract compatibility shim for test and dev environments.

The real ``pytesseract`` package is declared in ``requirements.txt``. This
module keeps imports patchable in environments where optional OCR dependencies
have not been installed yet.
"""


class Output:
    DICT = "dict"


def image_to_data(*args, **kwargs):
    raise RuntimeError(
        "pytesseract is not installed. Install apps/api requirements and the "
        "Tesseract system binary before running live OCR."
    )

