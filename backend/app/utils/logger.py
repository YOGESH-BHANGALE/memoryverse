"""
Logging configuration for MemoryVerse AI backend.
"""

import logging
import sys


def setup_logger(name: str = "memoryverse", level: int = logging.INFO) -> logging.Logger:
    """Create and return a configured logger instance."""
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


# Default application logger
logger = setup_logger()
