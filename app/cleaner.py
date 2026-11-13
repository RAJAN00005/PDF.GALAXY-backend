import asyncio
import time
import os
import logging
from pathlib import Path
from .config import UPLOAD_DIR, PROCESSED_DIR, RETENTION_SECONDS

logger = logging.getLogger("cleaner")

def cleanup_old_files():
    """Removes files in uploads and processed folders older than RETENTION_SECONDS."""
    now = time.time()
    deleted_count = 0
    
    for directory in [UPLOAD_DIR, PROCESSED_DIR]:
        if not directory.exists():
            continue
        for root, dirs, files in os.walk(directory):
            for file_name in files:
                file_path = Path(root) / file_name
                try:
                    file_age = now - file_path.stat().st_mtime
                    if file_age > RETENTION_SECONDS:
                        file_path.unlink()
                        deleted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete {file_path}: {e}")
                    
    if deleted_count > 0:
        logger.info(f"Cleanup executed: removed {deleted_count} expired files.")

async def start_cleanup_loop(interval_seconds: int = 600):
    """Periodically runs the file cleanup loop in the background."""
    while True:
        try:
            cleanup_old_files()
        except Exception as e:
            logger.error(f"Error during cleanup loop: {e}")
        await asyncio.sleep(interval_seconds)
