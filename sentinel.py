"""
sentinel.py — Entry Point
===========================
Responsibility:
    Bootstraps the entire Sentinel application:
      1. Ensures user config exists in %APPDATA%/Sentinel/
      2. Loads and validates config.yaml
      3. Sets up the structured JSON Lines logger
      4. Launches the CustomTkinter GUI Dashboard
"""

import os
import shutil
import sys
from pathlib import Path

from config_loader import load_config
from gui.dashboard import DashboardApp
from logger import setup_logger

BANNER = r"""
  ____            _   _            _
 / ___| ___ _ __ | |_(_)_ __   ___| |
 \___ \/ _ \ '_ \| __| | '_ \ / _ \ |
  ___) |  __/ | | | |_| | | | |  __/ |
 |____/ \___|_| |_|\__|_|_| |_|\___|_|

  Automated Intelligent File Manager (GUI Mode)
"""


# ── AppData config bootstrapping ────────────────────────────────────────
# On first launch the bundled config.yaml is copied to %APPDATA%\Sentinel\.
# Subsequent launches always read from the user's copy, so user settings
# survive application updates.

def _get_base_path() -> Path:
    """Return the base path for bundled resources.

    When running from a PyInstaller bundle, ``sys._MEIPASS`` points to
    the temporary directory where the bundle was extracted.  In normal
    development mode, return the directory containing this script.
    """
    if getattr(sys, "frozen", False):
        # Running as a PyInstaller bundle
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent


APP_DATA = Path(os.getenv("APPDATA", "")) / "Sentinel"
USER_CONFIG = APP_DATA / "config.yaml"


def ensure_user_config() -> str:
    """Copy the bundled default config to %APPDATA% on first run.

    Returns the path to the user-writable config file as a string.
    """
    APP_DATA.mkdir(parents=True, exist_ok=True)
    if not USER_CONFIG.exists():
        bundled = _get_base_path() / "config.yaml"
        if bundled.exists():
            shutil.copy(bundled, USER_CONFIG)
        else:
            # Fallback: no bundled config — copy from project root
            fallback = Path(__file__).resolve().parent / "config.yaml"
            if fallback.exists():
                shutil.copy(fallback, USER_CONFIG)
    return str(USER_CONFIG)


def main() -> None:
    print(BANNER)

    # ── 1. Ensure user config exists in %APPDATA% ────────────────────
    config_path = ensure_user_config()

    # ── 2. Load configuration ────────────────────────────────────────
    config = load_config(config_path)

    # ── 3. Set up logger ─────────────────────────────────────────────
    logger = setup_logger(
        log_file=config.log_file,
        max_bytes=config.log_max_bytes,
        backup_count=config.log_backup_count,
    )

    # ── 4. Start GUI Dashboard ───────────────────────────────────────
    print("[Sentinel] Launching GUI Dashboard...")
    app = DashboardApp(config_path=config_path, config=config, logger=logger)
    app.mainloop()
    
    print("[Sentinel] Goodbye.")


if __name__ == "__main__":
    main()
