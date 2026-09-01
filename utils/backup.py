"""Database backup utility for SQLite deployments."""

import os
import shutil
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from config import BACKUP_DIR, DATA_DIR, settings

logger = logging.getLogger(__name__)


def create_sqlite_backup() -> Optional[Path]:
    """Create a timestamped copy of the SQLite database.

    Returns:
        Path to backup file if successful, None otherwise.
    """
    if not settings.DATABASE_URL.startswith("sqlite"):
        logger.warning("Automated file backup is only supported for SQLite databases.")
        return None

    db_path = DATA_DIR / "bot.db"
    if not db_path.exists():
        logger.error(f"Database file not found at {db_path}")
        return None

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUP_DIR / f"bot_backup_{timestamp}.db"

    try:
        shutil.copy2(db_path, backup_file)
        logger.info(f"SQLite backup created successfully at: {backup_file}")
        return backup_file
    except Exception as e:
        logger.error(f"Failed to create SQLite backup: {e}", exc_info=True)
        return None
