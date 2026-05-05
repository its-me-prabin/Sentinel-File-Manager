"""
config_loader.py — Configuration Loader & Validator
=====================================================
Responsibility:
    Loads ``config.yaml``, validates that all required sections and keys
    are present, expands ``~`` in every path to an absolute path, and
    returns a typed ``SentinelConfig`` dataclass that the rest of the
    application consumes.

    If the file is missing, unreadable, or structurally invalid, the
    loader prints a clear error message and calls ``sys.exit(1)``.
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

import yaml


@dataclass
class SentinelConfig:
    """Fully validated and path-expanded configuration for Sentinel."""

    # --- Paths ---
    watched_folders: List[Path] = field(default_factory=list)
    deep_storage: Path = field(default_factory=lambda: Path.home() / "Documents" / "Deep Storage")
    documents_base: Path = field(default_factory=lambda: Path.home() / "Documents")

    # --- Rules ---
    keyword_rules: Dict[str, List[str]] = field(default_factory=dict)
    extension_rules: Dict[str, List[str]] = field(default_factory=dict)

    # --- Settings ---
    archive_after_days: int = 30
    retry_attempts: int = 3
    retry_backoff_seconds: List[int] = field(default_factory=lambda: [5, 30, 300])
    temporal_scan_interval_minutes: int = 60
    log_file: str = "sentinel_history.jsonl"
    log_max_bytes: int = 5_242_880
    log_backup_count: int = 3

    # --- GUI ---
    theme: str = "dark"
    color_accent: str = "blue"
    activity_feed_limit: int = 200
    window_width: int = 960
    window_height: int = 660


def _expand_path(raw: str) -> Path:
    """Expand ``~`` and resolve to an absolute path."""
    return Path(raw).expanduser().resolve()


def _validate_section(data: dict, section: str, required_keys: list) -> dict:
    """Ensure a top-level section exists and contains required keys."""
    block = data.get(section)
    if block is None:
        print(f"[ERROR] config.yaml is missing the '{section}' section.")
        sys.exit(1)
    for key in required_keys:
        if key not in block:
            print(f"[ERROR] config.yaml: '{section}' section is missing key '{key}'.")
            sys.exit(1)
    return block


def load_config(config_path: str = "config.yaml") -> SentinelConfig:
    """Load, validate, and return a ``SentinelConfig`` from *config_path*.

    Parameters
    ----------
    config_path : str
        Path to the YAML configuration file (relative or absolute).

    Returns
    -------
    SentinelConfig
        A fully validated configuration dataclass.

    Raises
    ------
    SystemExit
        If the config file is missing, unreadable, or malformed.
    """
    path = Path(config_path)
    if not path.exists():
        print(f"[ERROR] Configuration file not found: {path.resolve()}")
        print("        Please create a config.yaml alongside sentinel.py.")
        sys.exit(1)

    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        print(f"[ERROR] Failed to parse config.yaml:\n{exc}")
        sys.exit(1)

    if not isinstance(data, dict):
        print("[ERROR] config.yaml must be a YAML mapping at the top level.")
        sys.exit(1)

    # --- Validate sections ---
    paths_block = _validate_section(data, "paths", ["watched", "deep_storage"])
    settings_block = _validate_section(data, "settings", [
        "archive_after_days",
        "retry_attempts",
        "retry_backoff_seconds",
        "temporal_scan_interval_minutes",
        "log_file",
        "log_max_bytes",
        "log_backup_count",
    ])
    gui_block = _validate_section(data, "gui", [
        "theme",
        "color_accent",
        "activity_feed_limit",
        "window_width",
        "window_height",
    ])

    # keyword_rules and extension_rules are optional but expected
    keyword_rules = data.get("keyword_rules", {})
    extension_rules = data.get("extension_rules", {})

    if not isinstance(keyword_rules, dict):
        print("[ERROR] config.yaml: 'keyword_rules' must be a mapping.")
        sys.exit(1)
    if not isinstance(extension_rules, dict):
        print("[ERROR] config.yaml: 'extension_rules' must be a mapping.")
        sys.exit(1)

    # --- Build config ---
    watched_raw = paths_block["watched"]
    if not isinstance(watched_raw, list) or len(watched_raw) == 0:
        print("[ERROR] config.yaml: 'paths.watched' must be a non-empty list of directories.")
        sys.exit(1)

    watched_folders = [_expand_path(p) for p in watched_raw]
    deep_storage = _expand_path(paths_block["deep_storage"])
    documents_base = deep_storage.parent  # Deep Storage lives inside ~/Documents

    # Normalise extension rules: ensure all extensions start with a dot and are lowercase
    normalised_ext = {}
    for folder_name, extensions in extension_rules.items():
        normalised_ext[folder_name] = [
            ext.lower() if ext.startswith(".") else f".{ext.lower()}"
            for ext in extensions
        ]

    # Normalise keyword rules: lowercase all keywords
    normalised_kw = {}
    for folder_name, keywords in keyword_rules.items():
        normalised_kw[folder_name] = [kw.lower() for kw in keywords]

    config = SentinelConfig(
        watched_folders=watched_folders,
        deep_storage=deep_storage,
        documents_base=documents_base,
        keyword_rules=normalised_kw,
        extension_rules=normalised_ext,
        archive_after_days=settings_block["archive_after_days"],
        retry_attempts=settings_block["retry_attempts"],
        retry_backoff_seconds=settings_block["retry_backoff_seconds"],
        temporal_scan_interval_minutes=settings_block["temporal_scan_interval_minutes"],
        log_file=settings_block["log_file"],
        log_max_bytes=settings_block["log_max_bytes"],
        log_backup_count=settings_block["log_backup_count"],
        theme=gui_block["theme"],
        color_accent=gui_block["color_accent"],
        activity_feed_limit=gui_block["activity_feed_limit"],
        window_width=gui_block["window_width"],
        window_height=gui_block["window_height"],
    )

    # --- Pre-create destination folders ---
    _ensure_directories(config)

    return config


def _ensure_directories(config: SentinelConfig) -> None:
    """Create all destination directories if they do not already exist."""
    # Deep Storage
    config.deep_storage.mkdir(parents=True, exist_ok=True)

    # Keyword-rule destinations
    for folder_name in config.keyword_rules:
        (config.documents_base / folder_name).mkdir(parents=True, exist_ok=True)

    # Extension-rule destinations
    for folder_name in config.extension_rules:
        (config.documents_base / folder_name).mkdir(parents=True, exist_ok=True)

    # Unclassified fallback
    (config.documents_base / "Unclassified").mkdir(parents=True, exist_ok=True)
