"""
logging_config.py
─────────────────
Single-call setup for structured logging:
  • File handler  → logs/trading_bot.log  (DEBUG and above, rotating)
  • Console handler → WARNING and above (keeps terminal clean)

Usage:
    from bot.logging_config import setup_logging
    setup_logging()            # call once at app startup
    logger = logging.getLogger(__name__)
"""

import logging
import logging.handlers
import os


LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
LOG_FILE = os.path.join(LOG_DIR, "trading_bot.log")

# Detailed format for file — every field we might need to debug an order
FILE_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
)
# Compact format for console — human-readable at a glance
CONSOLE_FORMAT = "%(levelname)-8s | %(message)s"

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(log_level: str = "DEBUG") -> None:
    """
    Initialise root logger with file + console handlers.
    Safe to call multiple times (idempotent — clears existing handlers first).

    Args:
        log_level: minimum level for the file handler (default DEBUG).
                   Console is always WARNING to avoid clutter.
    """
    os.makedirs(LOG_DIR, exist_ok=True)

    root = logging.getLogger()

    # Idempotency: remove handlers that were added by a previous call
    if root.handlers:
        root.handlers.clear()

    root.setLevel(logging.DEBUG)  # root must be ≤ the most verbose handler

    # ── File handler ──────────────────────────────────────────────────────────
    # Rotate at 5 MB, keep 3 back-ups — prevents unbounded disk growth
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(getattr(logging, log_level.upper(), logging.DEBUG))
    file_handler.setFormatter(logging.Formatter(FILE_FORMAT, datefmt=DATE_FORMAT))

    # ── Console handler ───────────────────────────────────────────────────────
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(logging.Formatter(CONSOLE_FORMAT))

    root.addHandler(file_handler)
    root.addHandler(console_handler)

    # Silence the very noisy urllib3 / httpx debug traffic
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    logging.getLogger(__name__).debug(
        "Logging initialised — file: %s | level: %s", LOG_FILE, log_level
    )
