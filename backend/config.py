import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Environment
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Secrets - NO FALLBACKS IN PRODUCTION
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    if ENVIRONMENT == "production":
        raise ValueError("CRITICAL: SECRET_KEY must be set in production. Generate with: python3 -c \"import secrets; print(secrets.token_urlsafe(64))\"")
    # Development fallback only
    SECRET_KEY = "dev_insecure_key_for_development_only_09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
    print("⚠️  WARNING: Using development SECRET_KEY. NEVER use in production!")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

# Encryption - NO FALLBACKS IN PRODUCTION
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    if ENVIRONMENT == "production":
        raise ValueError("CRITICAL: ENCRYPTION_KEY must be set in production. Generate with: python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"")
    # Development fallback only
    ENCRYPTION_KEY = "dev_insecure_key_2gI5x3-5Q5k7Y8z9_1A2B3C4D5E6F7G8H9I0J1K2L3M="
    print("⚠️  WARNING: Using development ENCRYPTION_KEY. NEVER use in production!")
ENCRYPTION_KEY = ENCRYPTION_KEY.encode()

# File Uploads
ALLOWED_EXTENSIONS = {'.pdf', '.csv', '.xlsx', '.xls', '.jpg', '.jpeg', '.png', '.txt', '.doc', '.docx', '.zip', '.mp3', '.mp4'}
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", 50))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# CORS
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",")

