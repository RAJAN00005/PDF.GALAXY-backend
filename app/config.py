import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
STORAGE_DIR = BASE_DIR / "storage"
UPLOAD_DIR = STORAGE_DIR / "uploads"
PROCESSED_DIR = STORAGE_DIR / "processed"

# Create storage directories if they do not exist
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# 60-minute automatic deletion window (in seconds)
RETENTION_SECONDS = int(os.getenv("PDF_RETENTION_SECONDS", 3600))
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE_BYTES", 100 * 1024 * 1024)) # 100 MB

# 100% Keyless Architecture: No external paid or secret API keys required.
# All operations (OCR, PDF processing, translation, summaries) run self-contained and free.
