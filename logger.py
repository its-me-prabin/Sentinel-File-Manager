"""
logger.py — JSON Lines Structured Logger Setup
================================================
Responsibility:
    Configures Python's logging module to write structured JSON objects
    (one per line) to a rotating log file. Every file operation — move,
    skip, retry, or failure — is recorded as a machine-readable JSON
    line in ``sentinel_history.jsonl``.

    Uses ``RotatingFileHandler`` to cap file size (default 5 MB) and
    keep a configurable number of backups.
"""

import json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path


class JsonLineFormatter(logging.Formatter):
    """Custom formatter that outputs each log record as a single JSON line.

    Only records that carry an ``event_data`` attribute (set via
    ``logger.info("...", extra={"event_data": {...}})``) are formatted
    as JSON.  All other records fall back to a plain-text format so that
    standard Python log messages still render properly.
    """

    def format(self, record: logging.LogRecord) -> str:
        event_data = getattr(record, "event_data", None)
        if event_data is not None:
            return json.dumps(event_data, ensure_ascii=False)
        # Fallback for non-structured messages
        return super().format(record)


def setup_logger(
    log_file: str = "sentinel_history.jsonl",
    max_bytes: int = 5_242_880,
    backup_count: int = 3,
) -> logging.Logger:
    """Create and return the application-wide Sentinel logger.

    Parameters
    ----------
    log_file : str
        Path to the JSON Lines log file.
    max_bytes : int
        Maximum size (in bytes) before log rotation triggers.
    backup_count : int
        Number of rotated backup files to keep.

    Returns
    -------
    logging.Logger
        Configured logger instance named ``"sentinel"``.
    """
    logger = logging.getLogger("sentinel")
    logger.setLevel(logging.INFO)

    # Prevent duplicate handlers on repeated calls
    if logger.handlers:
        return logger

    # Ensure the log directory exists
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Rotating file handler for JSON Lines (structured events only)
    file_handler = RotatingFileHandler(
        str(log_path),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(JsonLineFormatter())
    file_handler.addFilter(lambda record: hasattr(record, "event_data"))
    logger.addHandler(file_handler)

    # Console handler for human-readable status
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s", datefmt="%H:%M:%S")
    )
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)

    return logger


def log_event(
    logger: logging.Logger,
    *,
    event: str,
    match_type: str,
    source: str,
    destination: str = "",
    matched_rule: str = "",
    matched_keyword: str = "",
    file_size_bytes: int = 0,
    file_age_days: int = 0,
    engine: str = "watchdog",
    reason: str = "",
) -> None:
    """Write a single structured JSON event to the log.

    Parameters
    ----------
    event : str
        One of ``"moved"``, ``"skipped"``, ``"retry_queued"``,
        ``"retry_failed"``, ``"archived"``.
    match_type : str
        One of ``"keyword"``, ``"temporal"``, ``"extension"``,
        ``"unclassified"``.
    source : str
        Absolute path of the original file.
    destination : str
        Absolute path the file was (or would be) moved to.
    matched_rule : str
        Name of the rule category that matched (e.g. ``"Finance"``).
    matched_keyword : str
        The specific keyword substring that triggered the match.
    file_size_bytes : int
        Size of the file in bytes.
    file_age_days : int
        Age of the file in days based on its mtime.
    engine : str
        One of ``"watchdog"``, ``"sweeper"``, ``"retry_worker"``.
    reason : str
        Human-readable reason for skips or failures.
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "match_type": match_type,
        "source": source,
        "destination": destination,
        "matched_rule": matched_rule,
        "matched_keyword": matched_keyword,
        "file_size_bytes": file_size_bytes,
        "file_age_days": file_age_days,
        "engine": engine,
    }
    if reason:
        entry["reason"] = reason

    # Remove empty optional fields to keep logs tidy
    entry = {k: v for k, v in entry.items() if v != "" and v != 0 or k in ("timestamp", "event", "match_type", "source", "engine")}

    logger.info(
        f"{event}: {os.path.basename(source)} -> {matched_rule or match_type}",
        extra={"event_data": entry},
    )
