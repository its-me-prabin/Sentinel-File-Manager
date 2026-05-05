<div align="center">
  <img src="assets/sentinel_icon.ico" width="128" alt="Sentinel Logo">
  <h1>Sentinel File Manager</h1>
  <p><b>An Automated, Intelligent File Organization System with a Modern GUI</b></p>
</div>

## Overview
Sentinel is a robust, automated file manager that runs in the background to keep your directories clean and organized. Powered by real-time file system monitoring and a dedicated age-based sweeper, Sentinel automatically moves incoming files into structured categories (like Finance, Images, or Code) based on file extensions or keyword matching. 

## Features
- **Real-Time Monitoring**: Uses `watchdog` to instantly categorize and move files as soon as they hit your watched folders (e.g., Downloads, Desktop).
- **Intelligent Routing**: 
  - *Extension Rules*: Automatically move `.pdf` to Documents or `.mp4` to Videos.
  - *Keyword Rules*: Move files containing "invoice" or "receipt" directly to your Finance folder.
- **Deep Storage Sweeping**: Automatically archives files older than a specified number of days to keep your active workspace clutter-free.
- **Resilient Retry Queue**: If a file is locked (e.g., still downloading), Sentinel queues it and retries using an exponential backoff strategy.
- **Modern GUI Dashboard**: Built with `customtkinter`, the dashboard provides a live activity feed, real-time statistics, and an intuitive settings panel.

## Architecture
- **Watchdog Engine**: Listens for file creation/modification events in real-time.
- **Sweeper Engine**: Background thread running on an APScheduler cron job to archive stale files.
- **Thread-Safe Event Bus**: Background engines communicate safely with the main GUI thread via `queue.Queue`.
- **AppData Configuration**: Settings dynamically persist in `%APPDATA%\Sentinel\` on Windows, allowing user settings to survive app updates or reinstalls.

## Installation
You can either download the pre-compiled Windows installer directly, or run the application from source.

### 📥 Direct Download (Windows Only)
1. Go to the [installer_output](installer_output/) folder in this repository.
2. Download `SentinelInstaller_v1.0.0.exe`.
3. Run the installer to automatically set up the application, shortcuts, and background engines.

### 💻 Run From Source
1. Clone the repository:
   ```bash
   git clone https://github.com/its-me-prabin/Sentinel-File-Manager.git
   cd ALL-In-One-Sentinal
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the application:
   ```bash
   python sentinel.py
   ```

### Build Windows Installer
Sentinel includes an automated build pipeline using PyInstaller and Inno Setup to create a professional `SentinelInstaller_v1.0.0.exe`.

1. Ensure you have [Inno Setup 6](https://jrsoftware.org/isdl.php) installed on your system.
2. Run the build script in PowerShell or CMD:
   ```bat
   .\build.bat
   ```
3. Find your compiled `.exe` installer in the `installer_output\` directory!

## Configuration
You don't need to manually edit code or YAML to configure Sentinel. Access the **Settings** panel directly from the GUI to manage:
- **Paths**: The directories Sentinel watches and your Deep Storage path.
- **Engine Options**: Configure Archive age limits, Retry attempts, and Scan intervals.
- **Rules**: Add new categorization destinations, keywords, and extensions through an intuitive tabbed interface.

## License
Licensed under the [MIT License](LICENSE.txt). Copyright (c) 2024 its-me-prabin.
