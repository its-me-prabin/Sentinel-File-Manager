"""
watcher.py — Watchdog Event Handler (Engine A)
================================================
Responsibility:
    Uses the ``watchdog`` library to monitor configured folders for
    FileCreatedEvent and FileModifiedEvent. Each detected event is
    passed through the processing pipeline.
"""

import logging
import queue

from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent
from watchdog.observers import Observer

from config_loader import SentinelConfig
from pipeline import process_file
from retry_worker import RetryWorker


class SentinelHandler(FileSystemEventHandler):
    """Handles filesystem events and dispatches them to the pipeline."""

    def __init__(self, config: SentinelConfig, logger: logging.Logger,
                 retry_worker: RetryWorker, gui_event_bus: queue.Queue | None = None):
        super().__init__()
        self.config = config
        self.logger = logger
        self.retry_worker = retry_worker
        self.gui_event_bus = gui_event_bus

    def on_created(self, event):
        if isinstance(event, FileCreatedEvent) and not event.is_directory:
            process_file(event.src_path, self.config, self.logger,
                         self.retry_worker, self.gui_event_bus, engine="watchdog")

    def on_modified(self, event):
        if isinstance(event, FileModifiedEvent) and not event.is_directory:
            process_file(event.src_path, self.config, self.logger,
                         self.retry_worker, self.gui_event_bus, engine="watchdog")


def start_observer(config: SentinelConfig, logger: logging.Logger,
                   retry_worker: RetryWorker, gui_event_bus: queue.Queue | None = None) -> Observer:
    """Create, configure, and start a watchdog Observer.

    Returns the running Observer instance so the caller can stop it
    on shutdown.
    """
    handler = SentinelHandler(config, logger, retry_worker, gui_event_bus)
    observer = Observer()

    for folder in config.watched_folders:
        if folder.exists():
            observer.schedule(handler, str(folder), recursive=False)
            logger.info(f"[Watchdog] Monitoring: {folder}")
        else:
            logger.warning(f"[Watchdog] Skipped (not found): {folder}")

    observer.daemon = True
    observer.start()
    return observer
