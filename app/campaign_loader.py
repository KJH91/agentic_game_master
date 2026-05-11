from __future__ import annotations
import io

MAX_CHARS = 8000  # ~2k tokens — leaves headroom for game state + history


def from_pdf(uploaded_file) -> str:
    """Extract text from a Streamlit UploadedFile PDF. Returns extracted text."""
    try:
        import pdfplumber
        parts: list[str] = []
        with pdfplumber.open(io.BytesIO(uploaded_file.read())) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    parts.append(text.strip())
        full = "\n\n".join(parts)
    except Exception as e:
        return f"[Failed to read PDF: {e}]"

    if len(full) > MAX_CHARS:
        full = full[:MAX_CHARS] + "\n\n[Document truncated to fit context window]"
    return full


def from_text(text: str) -> str:
    if len(text) > MAX_CHARS:
        return text[:MAX_CHARS] + "\n\n[Text truncated to fit context window]"
    return text
