"""Extract plain text from a CV file (PDF / DOCX / TXT / MD).

Local-only, like everything CV-related. The extracted text never leaves your machine —
it's read, matched against job descriptions in memory, and discarded. PDF/DOCX support
needs extra libraries (pypdf, python-docx); they're in requirements.txt but not
requirements-core.txt, since the cloud scan never touches CVs.
"""

from __future__ import annotations

from pathlib import Path


class CVTextError(RuntimeError):
    pass


def _from_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise CVTextError(
            f"reading {path.name} needs pypdf: pip install -r requirements.txt"
        ) from None
    try:
        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:  # malformed/encrypted PDF
        raise CVTextError(f"could not read {path.name}: {exc}") from exc


def _from_docx(path: Path) -> str:
    try:
        import docx
    except ImportError:
        raise CVTextError(
            f"reading {path.name} needs python-docx: pip install -r requirements.txt"
        ) from None
    try:
        doc = docx.Document(str(path))
    except Exception as exc:
        raise CVTextError(f"could not read {path.name}: {exc}") from exc
    return "\n".join(p.text for p in doc.paragraphs)


def extract_text(path) -> str:
    p = Path(path)
    if not p.exists():
        raise CVTextError(f"{p} does not exist")
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        text = _from_pdf(p)
    elif suffix in (".docx",):
        text = _from_docx(p)
    elif suffix in (".txt", ".md", ".markdown"):
        text = p.read_text(encoding="utf-8", errors="replace")
    else:
        raise CVTextError(f"unsupported CV format {suffix!r} ({p.name}); use PDF, DOCX, TXT or MD")

    if not text.strip():
        # A scanned/image PDF extracts to nothing — flag it rather than silently
        # matching against an empty document.
        raise CVTextError(
            f"{p.name} produced no text — is it a scanned image? (OCR isn't supported)"
        )
    return text
