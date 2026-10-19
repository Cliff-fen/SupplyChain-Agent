import hashlib
from collections.abc import Iterable


class KnowledgeError(ValueError):
    pass


ALLOWED_TYPES = {
    "text/plain": "txt",
    "text/markdown": "md",
    "application/octet-stream": "txt",
    "application/pdf": "pdf",
}


def classify_document(filename: str, text: str) -> str:
    haystack = f"{filename} {text[:8000]}".lower()
    if any(keyword in haystack for keyword in ("指标", "公式", "口径", "metric", "kpi")):
        return "metric_definition"
    if any(keyword in haystack for keyword in ("制度", "规范", "policy", "compliance")):
        return "policy"
    if any(keyword in haystack for keyword in ("流程", "作业", "步骤", "process", "procedure")):
        return "process"
    return "other"


def extract_text(filename: str, content_type: str, payload: bytes) -> tuple[str, dict]:
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if content_type == "application/pdf" or suffix == "pdf":
        import io

        from pypdf import PdfReader

        try:
            pages = [page.extract_text() or "" for page in PdfReader(io.BytesIO(payload)).pages]
        except Exception as exc:  # pragma: no cover - parser-specific failure
            raise KnowledgeError("Unable to parse PDF document") from exc
        return "\n\n".join(pages), {"page_count": len(pages)}
    if content_type not in ALLOWED_TYPES and suffix not in {"txt", "md", "markdown"}:
        raise KnowledgeError("Only PDF, Markdown, and TXT documents are supported")
    try:
        return payload.decode("utf-8"), {}
    except UnicodeDecodeError as exc:
        raise KnowledgeError("Document must be UTF-8 encoded") from exc


def chunk_text(text: str, size: int = 1200, overlap: int = 120) -> Iterable[tuple[int, str, dict]]:
    normalized = " ".join(text.split())
    if not normalized:
        return
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")
    ordinal = 0
    start = 0
    while start < len(normalized):
        end = min(start + size, len(normalized))
        chunk = normalized[start:end].strip()
        if chunk:
            yield ordinal, chunk, {"start": start, "end": end}
            ordinal += 1
        if end == len(normalized):
            break
        start = end - overlap


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
