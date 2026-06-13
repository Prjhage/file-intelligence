import os

MAX_CHARS = 1000
SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".txt", ".md", ".py", ".js", ".ts", ".jsx", ".tsx", 
    ".csv", ".xlsx", ".json", ".yaml", ".yml", ".html", ".htm", ".xml",
    ".c", ".cpp", ".h", ".hpp", ".java", ".go", ".rs", ".sql",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp",
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"
}

def extract_text(filepath: str) -> str:
    """
    Extract text content from a file.
    Returns up to MAX_CHARS characters or empty string on failure.
    """
    try:
        ext = os.path.splitext(filepath)[1].lower()

        if ext not in SUPPORTED_EXTENSIONS:
            return ""

        if ext == ".pdf":
            return _read_pdf(filepath)
        elif ext == ".docx":
            return _read_docx(filepath)
        elif ext == ".xlsx":
            return _read_xlsx(filepath)
        else:
            return _read_text(filepath)

    except Exception as e:
        print(f"[file_reader] Error reading {filepath}: {e}")
        return ""

def _read_pdf(filepath: str) -> str:
    try:
        import fitz  # pymupdf
        doc = fitz.open(filepath)
        if doc.is_encrypted:
            doc.close()
            return ""
        text = ""
        for page in doc:
            text += page.get_text()
            if len(text) >= MAX_CHARS:
                break
        doc.close()
        return text[:MAX_CHARS].strip()
    except Exception as e:
        print(f"[file_reader] PDF error {filepath}: {e}")
        return ""

def _read_docx(filepath: str) -> str:
    try:
        from docx import Document
        doc = Document(filepath)
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        return text[:MAX_CHARS].strip()
    except Exception as e:
        print(f"[file_reader] DOCX error {filepath}: {e}")
        return ""

def _read_xlsx(filepath: str) -> str:
    try:
        import openpyxl
        wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
        lines = []
        for sheet in wb.worksheets:
            for row in sheet.iter_rows(values_only=True):
                row_text = " | ".join(str(c) for c in row if c is not None)
                if row_text.strip():
                    lines.append(row_text)
                if len("\n".join(lines)) >= MAX_CHARS:
                    break
        wb.close()
        return "\n".join(lines)[:MAX_CHARS].strip()
    except Exception as e:
        print(f"[file_reader] XLSX error {filepath}: {e}")
        return ""

def _read_text(filepath: str) -> str:
    try:
        # Try different encodings for better reliability globally
        for enc in ["utf-8", "latin-1", "cp1252"]:
            try:
                with open(filepath, "r", encoding=enc, errors="ignore") as f:
                    return f.read(MAX_CHARS).strip()
            except:
                continue
        return ""
    except Exception as e:
        print(f"[file_reader] Text error {filepath}: {e}")
        return ""

def is_supported(filepath: str) -> bool:
    """Return True if the file extension is supported."""
    ext = os.path.splitext(filepath)[1].lower()
    return ext in SUPPORTED_EXTENSIONS
