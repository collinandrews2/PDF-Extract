from pathlib import Path

try:
    from PyPDF2 import PdfReader
except ImportError as exc:
    raise ImportError("PyPDF2 is required to inspect PDF text layers") from exc


def has_text_layer(pdf_path: str) -> bool:
    """Return True when a PDF contains an extractable text layer."""
    reader = PdfReader(pdf_path)
    for page in reader.pages:
        text = page.extract_text()
        if text and text.strip():
            return True
    return False


def is_born_digital(pdf_path: str) -> bool:
    """A PDF is considered born digital when it has an extractable text layer."""
    return has_text_layer(pdf_path)


def classify_pdf(pdf_path: str) -> str:
    """Classify a PDF as born digital or scanned."""
    return "born_digital" if is_born_digital(pdf_path) else "scanned"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Check whether a PDF is born digital or scanned by inspecting the text layer."
    )
    parser.add_argument("pdf", help="Path to the PDF file to inspect.")
    args = parser.parse_args()

    path = Path(args.pdf)
    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    result = classify_pdf(str(path))
    print(result)
