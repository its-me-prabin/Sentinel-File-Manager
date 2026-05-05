"""
sweeper.py — APScheduler Temporal Sweep Job (Engine B)
=======================================================
Responsibility:
    Runs on a configurable interval (default: every 60 minutes) using
    APScheduler. Scans all watched folders for files older than
    ``archive_after_days`` and sends them through the pipeline with
    ``is_old=True``, forcing the temporal rule.
"""

import logging
import os
import queue
import time
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from config_loader import SentinelConfig
from pipeline import process_file
from retry_worker import RetryWorker


def _sweep(config: SentinelConfig, logger: logging.Logger,
           retry_worker: RetryWorker, gui_event_bus: queue.Queue | None = None) -> None:
    """Scan all watched folders for aged files and process them.

    Only files whose mtime is older than ``archive_after_days`` are
    sent through the pipeline with ``is_old=True`` (forcing temporal
    archiving).  Younger files are still processed but go through the
    normal keyword / extension / unclassified path.
    """
    logger.info("[Sweeper] Running temporal sweep...")
    count = 0
    archived = 0
    now = time.time()
    max_age_seconds = config.archive_after_days * 86400

    for folder in config.watched_folders:
        if not folder.exists():
            continue
        for entry in os.scandir(str(folder)):
            if entry.is_file() and not entry.name.startswith("."):
                try:
                    age_seconds = now - entry.stat().st_mtime
                    is_old = age_seconds > max_age_seconds
                except OSError:
                    is_old = False
                process_file(entry.path, config, logger,
                             retry_worker, gui_event_bus, engine="sweeper", is_old=is_old)
                count += 1
                if is_old:
                    archived += 1
    
    logger.info(f"[Sweeper] Sweep complete - {count} file(s) inspected, {archived} aged.")
    if gui_event_bus:
        gui_event_bus.put({
            "type": "sweep_complete",
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "count": count,
            "archived": archived
        })


def run_initial_sweep(config: SentinelConfig, logger: logging.Logger,
                      retry_worker: RetryWorker, gui_event_bus: queue.Queue | None = None) -> None:
    """Execute one immediate sweep at startup."""
    logger.info("[Sweeper] Initial startup sweep...")
    _sweep(config, logger, retry_worker, gui_event_bus)


def start_scheduler(config: SentinelConfig, logger: logging.Logger,
                    retry_worker: RetryWorker, gui_event_bus: queue.Queue | None = None) -> BackgroundScheduler:
    """Create and start the APScheduler background sweeper.

    Returns the running scheduler so the caller can shut it down.
    """
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        _sweep,
        trigger="interval",
        minutes=config.temporal_scan_interval_minutes,
        args=[config, logger, retry_worker, gui_event_bus],
        id="temporal_sweep",
        name="Temporal age sweep",
    )
    scheduler.start()
    logger.info(
        f"[Sweeper] Scheduled every {config.temporal_scan_interval_minutes} min"
    )
    return scheduler
