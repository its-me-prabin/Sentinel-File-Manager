@echo off
echo ============================================
echo  Sentinel Build Pipeline
echo ============================================

echo.
echo [1/3] Activating virtual environment...
if exist build_env\Scripts\activate.bat (
    call build_env\Scripts\activate
) else (
    echo WARNING: build_env not found. Using system Python.
    echo          Run: python -m venv build_env
    echo          Then: build_env\Scripts\activate
    echo          Then: pip install customtkinter watchdog apscheduler pyyaml pyinstaller
)

echo.
echo [2/3] Running PyInstaller...
py -3.12 -m PyInstaller sentinel.spec --clean
if %errorlevel% neq 0 (
    echo ERROR: PyInstaller failed. Check output above.
    pause
    exit /b 1
)

echo.
echo Verifying output...
if not exist "dist\Sentinel.exe" (
    echo ERROR: dist\Sentinel.exe not found after build.
    pause
    exit /b 1
)
echo OK: dist\Sentinel.exe exists

echo.
echo [3/3] Building installer with Inno Setup...
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
    if %errorlevel% neq 0 (
        echo ERROR: Inno Setup failed. Check output above.
        pause
        exit /b 1
    )
) else (
    echo WARNING: Inno Setup 6 not found at default location.
    echo          Install from: https://jrsoftware.org/isdl.php
    echo          Or run manually: ISCC.exe installer.iss
    echo.
    echo Skipping installer step. You still have dist\Sentinel.exe
)

echo.
echo ============================================
echo  Build complete!
if exist "installer_output\SentinelInstaller_v1.0.0.exe" (
    echo  Installer: installer_output\SentinelInstaller_v1.0.0.exe
) else (
    echo  Standalone: dist\Sentinel.exe
)
echo ============================================
pause
