"""Validation utilities for input sanitization and security"""
import io
import re
import os
from pathlib import Path
from typing import Optional
import zipfile


def validate_password_strength(password: str) -> tuple[bool, Optional[str]]:
    """
    Enforce strong password complexity for law enforcement portal accounts:
    - Minimum 10 characters, maximum 128 characters
    - At least one uppercase letter, lowercase letter, digit, and symbol
    """
    if len(password) < 10:
        return False, "Password must be at least 10 characters long"
    if len(password) > 128:
        return False, "Password must not exceed 128 characters"
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r"\d", password):
        return False, "Password must contain at least one digit"
    if not re.search(r"[^A-Za-z0-9]", password):
        return False, "Password must contain at least one special character"
    return True, None


def sanitize_filename(filename: str, max_length: int = 255) -> str:
    """
    Sanitize filename to prevent directory traversal and injection attacks
    
    Args:
        filename: Original filename
        max_length: Maximum allowed filename length
        
    Returns:
        Sanitized filename
    """
    # Remove path components
    filename = os.path.basename(filename)
    
    # Remove dangerous characters (keep alphanumeric, spaces, dots, hyphens, underscores)
    filename = re.sub(r'[^\w\s.-]', '', filename)
    
    # Prevent directory traversal
    filename = filename.replace('..', '')
    
    # Remove leading/trailing spaces and dots
    filename = filename.strip('. ')
    
    # Prevent hidden files
    if filename.startswith('.'):
        filename = 'file_' + filename
    
    # Limit length
    if len(filename) > max_length:
        name, ext = os.path.splitext(filename)
        filename = name[:max_length - len(ext)] + ext
    
    # Prevent empty filename
    if not filename or filename == '':
        filename = 'unnamed_file'
    
    # Prevent Windows reserved names
    reserved_names = ['CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4', 
                      'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2', 
                      'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9']
    name_without_ext = os.path.splitext(filename)[0].upper()
    if name_without_ext in reserved_names:
        filename = 'file_' + filename
    
    return filename


def sanitize_text_input(text: str, max_length: int = 5000) -> str:
    """
    Sanitize text input to prevent XSS and injection attacks
    
    Args:
        text: Input text
        max_length: Maximum allowed length
        
    Returns:
        Sanitized text
    """
    if not text:
        return ""
    
    # Limit length
    text = text[:max_length]
    
    # Remove null bytes
    text = text.replace('\x00', '')
    
    # Remove control characters except newline, tab, carriage return
    text = ''.join(char for char in text if char.isprintable() or char in '\n\t\r')
    
    return text.strip()


def validate_mobile_number(mobile: str) -> tuple[bool, Optional[str]]:
    """
    Validate mobile number format (Indian format)
    
    Returns:
        (is_valid, error_message)
    """
    # Remove spaces, hyphens, parentheses
    cleaned = re.sub(r'[\s\-\(\)]', '', mobile)
    
    # Check for valid Indian mobile format
    # Accepts: +91XXXXXXXXXX, 91XXXXXXXXXX, XXXXXXXXXX (10 digits)
    pattern = r'^(\+91|91)?[6-9]\d{9}$'
    
    if not re.match(pattern, cleaned):
        return False, "Invalid mobile number format. Use 10-digit Indian mobile number"
    
    return True, None


def validate_fir_number(fir: str) -> tuple[bool, Optional[str]]:
    """
    Validate FIR number format
    
    Returns:
        (is_valid, error_message)
    """
    if not fir or len(fir) < 3:
        return False, "FIR number is too short"
    
    if len(fir) > 50:
        return False, "FIR number is too long"
    
    # Allow alphanumeric, slashes, hyphens
    if not re.match(r'^[A-Z0-9\-/]+$', fir.upper()):
        return False, "FIR number contains invalid characters"
    
    return True, None


MAX_ZIP_UNCOMPRESSED_BYTES = 50 * 1024 * 1024  # 50 MB
MAX_ZIP_FILES = 100


async def read_upload_with_limit(upload_file, max_bytes: int, chunk_size: int = 1024 * 1024) -> bytes:
    """Read an UploadFile in chunks and abort immediately with HTTP 413 if max_bytes is exceeded."""
    from fastapi import HTTPException

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload_file.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size: {max_bytes // (1024 * 1024)}MB",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def validate_file_magic_and_zip(content: bytes, ext: str) -> tuple[bool, Optional[str]]:
    """
    Verify file magic bytes match the declared extension and guard ZIP/OOXML archives against decompression bombs.
    Rejects renamed executables (MZ/ELF/Mach-O/shebang scripts disguised as documents/CSVs).
    """
    ext = (ext or "").lower()
    if not content:
        return False, "Uploaded file is empty"

    # Block obvious native executable magic bytes regardless of extension
    if content.startswith((b"MZ", b"\x7fELF", b"\xca\xfe\xba\xbe", b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf")):
        return False, "Executable binaries are strictly prohibited"

    if ext == ".pdf":
        if not content.lstrip().startswith(b"%PDF-"):
            return False, "Invalid PDF file header (magic bytes mismatch)"
    elif ext == ".png":
        if not content.startswith(b"\x89PNG\r\n\x1a\n"):
            return False, "Invalid PNG file header (magic bytes mismatch)"
    elif ext in (".jpg", ".jpeg"):
        if not content.startswith(b"\xff\xd8\xff"):
            return False, "Invalid JPEG file header (magic bytes mismatch)"
    elif ext in (".xlsx", ".docx", ".zip"):
        if not content.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
            return False, f"Invalid {ext} archive signature (magic bytes mismatch)"
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                infos = zf.infolist()
                if len(infos) > MAX_ZIP_FILES:
                    return False, f"Archive contains too many entries ({len(infos)} > {MAX_ZIP_FILES})"
                total_uncompressed = sum(max(0, info.file_size) for info in infos)
                if total_uncompressed > MAX_ZIP_UNCOMPRESSED_BYTES:
                    return False, "Archive uncompressed size exceeds 50 MB limit (potential decompression bomb)"
        except zipfile.BadZipFile:
            return False, f"Corrupted or invalid {ext} archive"
    elif ext in (".xls", ".doc"):
        is_ole2 = content.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
        is_pk = content.startswith(b"PK\x03\x04")
        if not (is_ole2 or is_pk):
            return False, f"Invalid legacy Office {ext} header (magic bytes mismatch)"
    elif ext == ".mp3":
        if not (content.startswith(b"ID3") or (len(content) >= 2 and content[0] == 0xFF and (content[1] & 0xE0) == 0xE0)):
            return False, "Invalid MP3 audio header"
    elif ext == ".mp4":
        if len(content) < 12 or content[4:8] != b"ftyp":
            return False, "Invalid MP4 container header"
    elif ext in (".csv", ".txt"):
        if b"\x00" in content[:4096]:
            return False, f"Binary content is not allowed in {ext} files"
        try:
            content[:8192].decode("utf-8")
        except UnicodeDecodeError:
            try:
                content[:8192].decode("latin-1")
            except UnicodeDecodeError:
                return False, f"File is not valid readable text for {ext}"
    return True, None
