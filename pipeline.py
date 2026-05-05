"""
pipeline.py — The 7-Step Processing Pipeline
==============================================
Responsibility:
    Implements the deterministic file-processing pipeline that every
    detected file passes through — whether from the watchdog listener
    or the temporal sweeper. Steps are applied in strict order:

        1. Guard clause  2. Keyword match  3. Age check
        4. Extension sort  5. Unclassified  6. Move  7. Log
"""

import logging
import os
import platform
import queue
import shutil
import stat
import threading
import time
from datetime import datetime
from pathlib import Path

from config_loader import SentinelConfig
from logger import log_event
from retry_worker import RetryTask, RetryWorker

# Per-file locks to prevent race conditions between engines
_file_locks: dict[str, threading.Lock] = {}
_file_locks_guard = threading.Lock()

# Session-level dedup set (absolute paths already processed this run)
_processed_paths: set[str] = set()
_processed_lock = threading.Lock()


def _get_file_lock(filepath: str) -> threading.Lock:
    """Return a per-file lock, creating one if needed."""
    with _file_locks_guard:
        if filepath not in _file_locks:
            _file_locks[filepath] = threading.Lock()
        return _file_locks[filepath]


def process_file(
    filepath: str,
    config: SentinelConfig,
    logger: logging.Logger,
    retry_worker: RetryWorker,
    gui_event_bus: queue.Queue | None = None,
    engine: str = "watchdog",
    is_old: bool = False,
) -> None:
    """Run a file through the full 7-step pipeline.

    Parameters
    ----------
    filepath : str
        Absolute path to the file to process.
    config : SentinelConfig
        Loaded application configuration.
    logger : logging.Logger
        Structured Sentinel logger.
    retry_worker : RetryWorker
        Shared retry-queue worker.
    gui_event_bus : queue.Queue | None
        Queue for pushing lightweight events to the GUI.
    engine : str
        ``"watchdog"`` or ``"sweeper"`` — the engine that invoked this.
    is_old : bool
        If ``True`` (set by the sweeper), temporal archiving overrides
        keyword matching.
    """
    lock = _get_file_lock(filepath)
    if not lock.acquire(blocking=False):
        return  # Another engine is already processing this file
    try:
        _run_pipeline(filepath, config, logger, retry_worker, gui_event_bus, engine, is_old)
    finally:
        lock.release()


def _run_pipeline(
    filepath: str,
    config: SentinelConfig,
    logger: logging.Logger,
    retry_worker: RetryWorker,
    gui_event_bus: queue.Queue | None,
    engine: str,
    is_old: bool,
) -> None:
    path = Path(filepath)
    script_dir = Path(__file__).resolve().parent

    def push_gui_skip(reason: str):
        if gui_event_bus:
            filename = path.name
            gui_event_bus.put({
                "type": "skip",
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "filename": filename[:30] + ("…" if len(filename) > 30 else ""),
                "reason": reason,
                "engine": engine
            })

    # ── Step 1 — Guard Clause ────────────────────────────────────────
    # Skip hidden files
    if path.name.startswith("."):
        log_event(logger, event="skipped", match_type="guard",
                  source=filepath, engine=engine, reason="hidden_file")
        push_gui_skip("hidden_file")
        return

    # Skip directories
    if path.is_dir():
        log_event(logger, event="skipped", match_type="guard",
                  source=filepath, engine=engine, reason="is_directory")
        push_gui_skip("is_directory")
        return

    # Skip if file no longer exists
    if not path.exists():
        return

    # Skip system files (Windows FILE_ATTRIBUTE_SYSTEM)
    if platform.system() == "Windows":
        try:
            attrs = os.stat(filepath).st_file_attributes  # type: ignore[attr-defined]
            if attrs & stat.FILE_ATTRIBUTE_SYSTEM:  # type: ignore[attr-defined]
                log_event(logger, event="skipped", match_type="guard",
                          source=filepath, engine=engine, reason="system_file")
                push_gui_skip("system_file")
                return
        except (OSError, AttributeError):
            pass
    else:
        # Linux/macOS: skip /proc, /sys
        if filepath.startswith(("/proc", "/sys")):
            log_event(logger, event="skipped", match_type="guard",
                      source=filepath, engine=engine, reason="system_path")
            push_gui_skip("system_path")
            return

    # Skip files inside the script's own directory
    try:
        path.resolve().relative_to(script_dir)
        log_event(logger, event="skipped", match_type="guard",
                  source=filepath, engine=engine, reason="own_directory")
        push_gui_skip("own_directory")
        return
    except ValueError:
        pass  # Not inside script dir — good

    # Session-level deduplication
    abs_path = str(path.resolve())
    with _processed_lock:
        if abs_path in _processed_paths:
            log_event(logger, event="skipped", match_type="guard",
                      source=filepath, engine=engine, reason="already_processed")
            push_gui_skip("already_processed")
            return
        _processed_paths.add(abs_path)

    # ── Gather file metadata ─────────────────────────────────────────
    try:
        file_stat = path.stat()
        file_size = file_stat.st_size
        mtime = file_stat.st_mtime
    except OSError:
        return

    now_ts = time.time()
    age_days = int((now_ts - mtime) / 86400)
    stem = path.stem.lower()
    ext = path.suffix.lower()

    destination = ""
    match_type = ""
    matched_rule = ""
    matched_keyword = ""

    # ── Step 2 — Keyword Matching (Priority 1) ───────────────────────
    if not is_old:
        for folder_name, keywords in config.keyword_rules.items():
            for kw in keywords:
                if kw in stem:
                    destination = str(config.documents_base / folder_name / path.name)
                    match_type = "keyword"
                    matched_rule = folder_name
                    matched_keyword = kw
                    break
            if match_type:
                break

    # ── Step 3 — Age Check (Priority 2) ──────────────────────────────
    if not match_type or is_old:
        if age_days > config.archive_after_days or is_old:
            mtime_dt = datetime.fromtimestamp(mtime)
            year = str(mtime_dt.year)
            month_label = f"{mtime_dt.month:02d} - {mtime_dt.strftime('%B')}"
            destination = str(config.deep_storage / year / month_label / path.name)
            match_type = "temporal"
            matched_rule = "Deep Storage"
            matched_keyword = ""

    # ── Step 4 — Extension Sort (Priority 3) ─────────────────────────
    if not match_type:
        for folder_name, extensions in config.extension_rules.items():
            if ext in extensions:
                destination = str(config.documents_base / folder_name / path.name)
                match_type = "extension"
                matched_rule = folder_name
                break

    # ── Step 5 — Unclassified Fallback ───────────────────────────────
    if not match_type:
        destination = str(config.documents_base / "Unclassified" / path.name)
        match_type = "unclassified"
        matched_rule = "Unclassified"

    # ── Step 6 — Execute Move (with Retry Queue) ─────────────────────
    dst = Path(destination)
    # Handle name collisions
    if dst.exists():
        base = dst.stem
        suffix = dst.suffix
        counter = 1
        while dst.exists():
            dst = dst.parent / f"{base} ({counter}){suffix}"
            counter += 1
        destination = str(dst)

    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(filepath, destination)
        event_type = "archived" if match_type == "temporal" else "moved"

        # ── Step 7 — Log the Outcome ─────────────────────────────────
        log_event(logger, event=event_type, match_type=match_type,
                  source=filepath, destination=destination,
                  matched_rule=matched_rule, matched_keyword=matched_keyword,
                  file_size_bytes=file_size, file_age_days=age_days,
                  engine=engine)
                  
        if gui_event_bus:
            filename = path.name
            gui_event_bus.put({
                "type": "moved",
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "filename": filename[:30] + ("…" if len(filename) > 30 else ""),
                "match_type": match_type,
                "matched": matched_keyword or ext,
                "destination": dst.parent.name,
                "engine": engine,
            })

    except (PermissionError, OSError):
        # File is locked — add to retry queue
        backoff = config.retry_backoff_seconds
        task = RetryTask(
            source=filepath, destination=destination,
            match_type=match_type, matched_rule=matched_rule,
            matched_keyword=matched_keyword,
            file_size_bytes=file_size, file_age_days=age_days,
            attempt=1,
            next_retry_at=time.time() + backoff[0],
        )
        retry_worker.enqueue(task)
        log_event(logger, event="retry_queued", match_type=match_type,
                  source=filepath, destination=destination,
                  matched_rule=matched_rule, file_size_bytes=file_size,
                  file_age_days=age_days, engine=engine,
                  reason="file_locked")
