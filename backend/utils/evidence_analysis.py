import os
import mimetypes
import traceback
from typing import Dict, Any

LEGAL_NOTICE = "All extracted data is generated solely to assist investigation. Original evidence remains primary and unaltered."


def process_file(path: str) -> Dict[str, Any]:
    """Process a file and extract factual, verifiable data only.

    This function attempts safe extraction using optional libraries when available.
    It never infers or fabricates data. If an extractor is unavailable, the
    Notes field explains the limitation. Any recovered/corrupted data must be
    explicitly marked by higher-level callers; here we report failures clearly.
    """
    ext = os.path.splitext(path)[1].lower()
    file_type = ext.lstrip('.') or 'unknown'

    extraction = {
        "Evidence File Type": file_type,
        "Extraction Method Used": None,
        "Extracted Data": None,
        "Confidence Level": "Low",
        "Notes": "",
        "LEGAL_SAFETY_NOTICE": LEGAL_NOTICE,
    }

    try:
        if ext in (".txt", ".log", ".md"):
            extraction["Extraction Method Used"] = "Plain text read"
            with open(path, "rb") as f:
                raw = f.read()
            try:
                text = raw.decode("utf-8")
                extraction["Extracted Data"] = text
                extraction["Confidence Level"] = "High"
            except UnicodeDecodeError:
                text = raw.decode("latin-1", errors="replace")
                extraction["Extracted Data"] = text
                extraction["Confidence Level"] = "Medium"
            return extraction

        if ext in (".csv", ".tsv"):
            extraction["Extraction Method Used"] = "CSV parsing"
            try:
                import pandas as pd
                df = pd.read_csv(path, sep=None, engine="python")
                extraction["Extracted Data"] = df.to_dict(orient="records")
                extraction["Confidence Level"] = "High"
            except Exception:
                # Fallback to builtin csv reader
                try:
                    import csv
                    with open(path, newline='', encoding='utf-8', errors='replace') as f:
                        reader = csv.reader(f)
                        rows = [row for row in reader]
                    extraction["Extracted Data"] = rows
                    extraction["Confidence Level"] = "Medium"
                    extraction["Notes"] = "Used builtin csv fallback; install pandas for richer parsing."
                except Exception as e:
                    extraction["Notes"] = f"CSV reading failed: {e}"
                    extraction["Confidence Level"] = "Low"
            return extraction

        if ext in (".xls", ".xlsx"):
            extraction["Extraction Method Used"] = "Spreadsheet parsing"
            try:
                import pandas as pd
                df = pd.read_excel(path, sheet_name=0)
                extraction["Extracted Data"] = df.to_dict(orient="records")
                extraction["Confidence Level"] = "High"
            except Exception as e:
                extraction["Notes"] = f"Spreadsheet parsing failed: {e}"
                extraction["Confidence Level"] = "Low"
            return extraction

        if ext == ".pdf":
            extraction["Extraction Method Used"] = "PDF text extraction"
            try:
                from PyPDF2 import PdfReader
                reader = PdfReader(path)
                pages = []
                for p in reader.pages:
                    pages.append(p.extract_text() or "")
                text = "\n".join(pages)
                extraction["Extracted Data"] = text
                extraction["Confidence Level"] = "Medium" if text.strip() else "Low"
            except Exception as e:
                extraction["Notes"] = f"PDF extraction unavailable or failed: {e}"
                extraction["Confidence Level"] = "Low"
            return extraction

        if ext in (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff"):
            extraction["Extraction Method Used"] = "Image processing (OCR if available)"
            try:
                from PIL import Image
            except Exception as e:
                extraction["Notes"] = f"Pillow not available: {e}"
                extraction["Confidence Level"] = "Low"
                return extraction

            try:
                import pytesseract
                img = Image.open(path)
                text = pytesseract.image_to_string(img)
                extraction["Extracted Data"] = text
                extraction["Confidence Level"] = "Medium" if text.strip() else "Low"
            except Exception as e:
                extraction["Notes"] = f"OCR not available or failed: {e}"
                extraction["Confidence Level"] = "Low"
            return extraction

        # Audio/video and other types: provide metadata and note missing extractors
        extraction["Extraction Method Used"] = "Metadata and raw info"
        size = os.path.getsize(path)
        mime = mimetypes.guess_type(path)[0]
        extraction["Extracted Data"] = {"filename": os.path.basename(path), "size_bytes": size, "mimetype": mime}
        extraction["Notes"] = "No specialized extractor available for this file type in current environment. Install optional dependencies to enable rich extraction."
        extraction["Confidence Level"] = "Low"
        return extraction

    except Exception:
        extraction["Notes"] = traceback.format_exc()
        extraction["Confidence Level"] = "Low"
        return extraction
