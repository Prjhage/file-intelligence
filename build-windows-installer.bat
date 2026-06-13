@echo off
setlocal enabledelayedexpansion

echo.
echo ==========================================
echo  File Intelligence - Windows Installer Build
echo ==========================================
echo.

REM Get project root
set "PROJECT_ROOT=%~dp0"
cd /d "%PROJECT_ROOT%"

echo [STEP 1/5] Checking requirements...
where python >nul 2>nul
if errorlevel 1 (
    echo ❌ ERROR: Python not found! Install from https://www.python.org/
    pause
    exit /b 1
)
echo ✓ Python found

where npm >nul 2>nul
if errorlevel 1 (
    echo ❌ ERROR: Node.js/npm not found! Install from https://nodejs.org/
    pause
    exit /b 1
)
echo ✓ Node.js found

where cargo >nul 2>nul
if errorlevel 1 (
    echo ❌ ERROR: Rust not found! Install from https://rustup.rs/
    pause
    exit /b 1
)
echo ✓ Rust found

python --version
node --version
cargo --version
echo.

echo [STEP 2/5] Building Python backend executable...
cd /d "%PROJECT_ROOT%python-backend"

REM Clean previous builds
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

REM Install PyInstaller if needed
pip install pyinstaller --quiet 2>nul

REM Build the executable
echo Building backend...
pyinstaller --onefile ^
    --name "file-intelligence-backend" ^
    --distpath "../src-tauri/binaries" ^
    --specpath "build_spec" ^
    main.py >nul 2>nul

if errorlevel 1 (
    echo ❌ ERROR: Failed to build Python backend
    echo Try running: pip install --upgrade pyinstaller
    pause
    exit /b 1
)

REM Check if binary was created
if not exist "..\src-tauri\binaries\file-intelligence-backend.exe" (
    echo ❌ ERROR: Backend executable not created
    pause
    exit /b 1
)

echo ✓ Python backend built: src-tauri/binaries/file-intelligence-backend.exe
echo.

echo [STEP 3/5] Building React frontend...
cd /d "%PROJECT_ROOT%"

call npm run build >nul 2>nul
if errorlevel 1 (
    echo ❌ ERROR: Frontend build failed
    echo Try running: npm install
    pause
    exit /b 1
)

if not exist "dist" (
    echo ❌ ERROR: dist folder not created
    pause
    exit /b 1
)

echo ✓ React frontend built: dist/
echo.

echo [STEP 4/5] Building Tauri application...
echo This may take 3-10 minutes (compiling Rust)...
echo Please wait...
echo.

call npm run tauri build

if errorlevel 1 (
    echo ❌ ERROR: Tauri build failed
    pause
    exit /b 1
)

echo.
echo ✓ Tauri application built successfully
echo.

echo [STEP 5/5] Locating installer...

set "INSTALLER_NSIS=%PROJECT_ROOT%src-tauri\target\release\bundle\nsis\*setup.exe"
set "INSTALLER_MSI=%PROJECT_ROOT%src-tauri\target\release\bundle\msi\*.msi"

if exist "%INSTALLER_NSIS%" (
    echo ✓ NSIS Installer (recommended):
    for %%i in ("%INSTALLER_NSIS%") do (
        echo   %%~ni
        echo   Location: %%~fi
    )
)

if exist "%INSTALLER_MSI%" (
    echo.
    echo ✓ MSI Installer:
    for %%i in ("%INSTALLER_MSI%") do (
        echo   %%~ni
        echo   Location: %%~fi
    )
)

echo.
echo ==========================================
echo  BUILD COMPLETE! ✅
echo ==========================================
echo.
echo Next steps:
echo 1. Test the installer on your PC
echo 2. Share the .EXE or .MSI file with users
echo 3. Users can download and double-click to install
echo.
pause
