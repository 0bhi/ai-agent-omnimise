import re
from collections import Counter
from pathlib import Path

from docx import Document
from pypdf import PdfReader

STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "have",
    "has",
    "was",
    "were",
    "are",
    "been",
    "will",
    "your",
    "you",
    "our",
    "all",
    "any",
    "can",
    "not",
    "but",
    "into",
    "about",
    "also",
    "such",
    "their",
    "they",
    "them",
    "its",
    "using",
    "use",
    "used",
    "work",
    "project",
    "skills",
    "experience",
    "email",
    "phone",
    "address",
    "name",
    "date",
    "summary",
    "education",
    "university",
    "college",
    "india",
    "indian",
}


def _extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages:
        t = page.extract_text() or ""
        parts.append(t)
    return "\n".join(parts)


def _extract_docx_text(path: Path) -> str:
    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs if p.text)


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf_text(path)
    if suffix in {".docx", ".doc"}:
        if suffix == ".doc":
            raise ValueError("Legacy .doc is not supported; convert to .docx or PDF")
        return _extract_docx_text(path)
    raise ValueError("Unsupported file type; use PDF or DOCX")


def _tokenize(text: str) -> list[str]:
    text = text.lower()
    tokens = re.findall(r"[a-z0-9]{3,}", text)
    return [t for t in tokens if t not in STOPWORDS]


def extract_keywords(text: str, top_n: int = 40) -> list[str]:
    counts = Counter(_tokenize(text))
    return [w for w, _ in counts.most_common(top_n)]


def build_resume_extracted(path: Path) -> tuple[dict, str]:
    raw = extract_text(path)
    preview = raw[:4000]
    keywords = extract_keywords(raw)
    extracted = {
        "keywords": keywords,
        "char_count": len(raw),
    }
    return extracted, preview
