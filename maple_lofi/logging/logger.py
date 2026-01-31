"""Logging setup for human-readable run logs."""

import logging
import sys
from pathlib import Path
from typing import TextIO


def setup_logger(log_file: Path) -> logging.Logger:
    """Setup logger that writes to console (INFO) and file (DEBUG).

    Args:
        log_file: Path to write log file

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("maple_lofi")
    logger.setLevel(logging.DEBUG)

    # Remove any existing handlers
    logger.handlers.clear()

    # Console handler (INFO level)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter(
        "%(levelname)s: %(message)s"
    )
    console_handler.setFormatter(console_format)

    # File handler (DEBUG level)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_format)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger
