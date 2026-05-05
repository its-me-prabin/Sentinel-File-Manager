"""
retry_worker.py — Retry Queue Thread
======================================
Responsibility:
    Manages an in-memory queue of files that failed to move due to
    PermissionError or OSError (file locked by another process).
    A daemon thread polls every 5 seconds and re-attempts moves
    when their next_retry_at time has passed. After exhausting all
    retries, the task is logged as failed and discarded.
"""

import logging
import queue
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List

from logger import log_event


@dataclass
class RetryTask:
    """A single file-move that needs to be retried."""
    source: str
    destination: str
    match_type: str
    matched_rule: str
    matched_keyword: str
    file_size_bytes: int
    file_age_days: int
    attempt: int = 1
    next_retry_at: float = 0.0


class RetryWorker:
    """Background thread that processes the retry queue."""

    def __init__(self, backoff_seconds: List[int], max_attempts: int, logger: logging.Logger, gui_event_bus: queue.Queue | None = None):
        self._queue: List[RetryTask] = []
        self._lock = threading.Lock()
        self._backoff = backoff_seconds
        self._max_attempts = max_attempts
        self._logger = logger
        self.gui_event_bus = gui_event_bus
        self._running = False
        self._thread = None

    def enqueue(self, task: RetryTask) -> None:
        with self._lock:
            self._queue.append(task)

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="retry-worker")
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _run(self) -> None:
        while self._running:
            now = time.time()
            ready = []
            with self._lock:
                remaining = []
                for t in self._queue:
                    (ready if now >= t.next_retry_at else remaining).append(t)
                self._queue = remaining
            for task in ready:
                self._attempt_move(task)
            time.sleep(5)

    def _attempt_move(self, task: RetryTask) -> None:
        src = Path(task.source)
        if not src.exists():
            return
        dst = Path(task.destination)
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            log_event(self._logger, event="moved", match_type=task.match_type,
                      source=task.source, destination=task.destination,
                      matched_rule=task.matched_rule, matched_keyword=task.matched_keyword,
                      file_size_bytes=task.file_size_bytes, file_age_days=task.file_age_days,
                      engine="retry_worker")
            if self.gui_event_bus:
                from datetime import datetime
                filename = src.name
                self.gui_event_bus.put({
                    "type": "moved",
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "filename": filename[:30] + ("…" if len(filename) > 30 else ""),
                    "match_type": task.match_type,
                    "matched": task.matched_keyword or src.suffix,
                    "destination": dst.parent.name,
                    "engine": "retry_worker",
                })
        except (PermissionError, OSError) as exc:
            if task.attempt >= self._max_attempts:
                reason = f"Exhausted {self._max_attempts} attempts: {exc}"
                log_event(self._logger, event="retry_failed", match_type=task.match_type,
                          source=task.source, destination=task.destination,
                          matched_rule=task.matched_rule, file_size_bytes=task.file_size_bytes,
                          file_age_days=task.file_age_days, engine="retry_worker",
                          reason=reason)
                if self.gui_event_bus:
                    from datetime import datetime
                    filename = src.name
                    self.gui_event_bus.put({
                        "type": "retry_failed",
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "filename": filename[:30] + ("…" if len(filename) > 30 else ""),
                        "reason": reason,
                        "engine": "retry_worker",
                    })
            else:
                idx = min(task.attempt, len(self._backoff) - 1)
                task.attempt += 1
                task.next_retry_at = time.time() + self._backoff[idx]
                self.enqueue(task)
