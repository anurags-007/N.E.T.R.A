"""Validation utilities for input sanitization and security"""
import re
import os
from pathlib import Path
from typing import Optional


def validate_password_strength(password: str) -> tuple[bool, Optional[str]]:
    """
    Simplified password validation
    Accepts:
    - Numeric PIN (e.g., 1234, 999999)
    - Alphabets only (e.g., abcd, Police)
    - Alphanumeric (e.g., abc123, Officer99)
    
    Minimum requirement: 4 characters
    
    Returns:
        (is_valid, error_message)
    """
    # Minimum length check
    if len(password) < 4:
        return False, "Password/PIN must be at least 4 characters long"
    
    # Maximum length check (reasonable limit)
    if len(password) > 20:
        return False, "Password/PIN must not exceed 20 characters"
    
    # Allow only alphanumeric (no special characters required)
    if not re.match(r'^[A-Za-z0-9]+$', password):
        return False, "Password/PIN must contain only letters and numbers (no special characters)"
    
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
