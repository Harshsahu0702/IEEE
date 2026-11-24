import os
import time
import logging
from pathlib import Path
from backend.config import settings

logger = logging.getLogger(__name__)


def cleanup_expired_evidence(retention_days: int = None) -> dict:
    """
    Enforces data retention policy:
    Automatically deletes snapshot evidence files older than N days.
    """
    days = retention_days if retention_days is not None else settings.DATA_RETENTION_DAYS
    evidence_dir = Path(settings.EVIDENCE_DIR)

    if not evidence_dir.exists():
        return {"deleted_files": 0, "bytes_freed": 0}

    cutoff_time = time.time() - (days * 86400)
    deleted_count = 0
    bytes_freed = 0

    for file_path in evidence_dir.glob("*.jpg"):
        try:
            mtime = file_path.stat().st_mtime
            if mtime < cutoff_time:
                file_size = file_path.stat().st_size
                file_path.unlink()
                deleted_count += 1
                bytes_freed += file_size
        except Exception as e:
            logger.warning(f"Failed to delete expired evidence file {file_path}: {e}")

    if deleted_count > 0:
        logger.info(f"Data Retention Cleanup: Removed {deleted_count} expired files ({bytes_freed} bytes freed).")

    return {"deleted_files": deleted_count, "bytes_freed": bytes_freed}
