@echo off
setlocal enabledelayedexpansion
echo ============================================================
echo  PDF Shrinker - Windows Build Script (Bundled Ghostscript)
echo ============================================================
echo.

REM ── Check Python ────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install from https://python.org
    pause & exit /b 1
)

REM ── Locate Ghostscript ──────────────────────────────────────
set GS_BIN=

REM Dynamically scan C:\Program Files\gs\gs*\bin\ for any version
for /d %%D in ("C:\Program Files\gs\gs*") do (
    if "!GS_BIN!"=="" (
        for %%E in (gswin64c.exe gswin64.exe gswin32c.exe gswin32.exe gs.exe) do (
            if "!GS_BIN!"=="" (
                if exist "%%D\bin\%%E" set GS_BIN=%%D\bin
            )
        )
    )
)

REM Also check Program Files (x86)
for /d %%D in ("C:\Program Files (x86)\gs\gs*") do (
    if "!GS_BIN!"=="" (
        for %%E in (gswin64c.exe gswin64.exe gswin32c.exe gswin32.exe gs.exe) do (
            if "!GS_BIN!"=="" (
                if exist "%%D\bin\%%E" set GS_BIN=%%D\bin
            )
        )
    )
)

REM Also check PATH
if "!GS_BIN!"=="" (
    for %%X in (gswin64c.exe gswin64.exe gswin32c.exe gswin32.exe gs.exe) do (
        if "!GS_BIN!"=="" (
            for /f "delims=" %%F in ('where %%X 2^>nul') do (
                if "!GS_BIN!"=="" (
                    for %%D in ("%%F\..") do set GS_BIN=%%~fD
                )
            )
        )
    )
)

if "!GS_BIN!"=="" (
    echo ERROR: Ghostscript not found on this machine.
    echo        Install it from: https://ghostscript.com/releases/gsdnld.html
    echo        Then re-run this script.
    pause & exit /b 1
)

echo Found Ghostscript at: !GS_BIN!
echo.

REM ── Stage GS binaries for bundling ──────────────────────────
echo [1/4] Staging Ghostscript binaries...
if exist gs_bin rmdir /s /q gs_bin
mkdir gs_bin

REM Copy all DLLs and the console executable
copy /y "!GS_BIN!\*.dll"   gs_bin\ >nul 2>&1
copy /y "!GS_BIN!\*.exe"   gs_bin\ >nul 2>&1

REM Copy the Ghostscript resource/lib folder (fonts, PS files, etc.)
REM It lives one level up from bin\
for %%D in ("!GS_BIN!\..")  do set GS_ROOT=%%~fD
if exist "!GS_ROOT!\lib"      xcopy /e /q /y "!GS_ROOT!\lib"      gs_bin\lib\      >nul
if exist "!GS_ROOT!\fonts"    xcopy /e /q /y "!GS_ROOT!\fonts"    gs_bin\fonts\    >nul
if exist "!GS_ROOT!\Resource" xcopy /e /q /y "!GS_ROOT!\Resource" gs_bin\Resource\ >nul

REM Detect exe name (prefer console variants, 64-bit first)
set GS_EXE=
for %%E in (gswin64c.exe gswin64.exe gswin32c.exe gswin32.exe gs.exe) do (
    if "!GS_EXE!"=="" (
        if exist "gs_bin\%%E" set GS_EXE=%%E
    )
)
echo     Executable: !GS_EXE!

REM Write a small marker file so the app knows the bundled exe name
echo !GS_EXE!> gs_bin\gs_exe_name.txt
echo.

REM ── Install Python dependencies ──────────────────────────────
echo [2/4] Installing Python dependencies...
pip install -r requirements.txt --quiet
if errorlevel 1 ( echo ERROR: pip failed. & pause & exit /b 1 )
echo.

REM ── Check icon exists ───────────────────────────────────────
if not exist "%~dp0app_icon.ico" (
    echo ERROR: app_icon.ico not found next to build.bat
    pause & exit /b 1
)
set ICON_PATH=%~dp0app_icon.ico

REM ── Build with PyInstaller ───────────────────────────────────
echo [3/4] Building executable (this takes a minute)...
python -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name "PDF Shrinker" ^
    --add-data "gs_bin;gs_bin" ^
    --icon "%ICON_PATH%" ^
    --clean ^
    --noconfirm ^
    pdf_shrinker.py
if errorlevel 1 ( echo ERROR: PyInstaller failed. & pause & exit /b 1 )
echo.

REM ── Cleanup staging folder ───────────────────────────────────
echo [4/4] Cleaning up...
rmdir /s /q gs_bin
rmdir /s /q build
del /q "PDF Shrinker.spec" 2>nul

REM ── Flush Windows icon cache so the new icon shows immediately ──
echo Refreshing icon cache...
ie4uinit.exe -show >nul 2>&1 || true

echo.
echo ============================================================
echo  Build complete!
echo  Output: dist\PDF Shrinker.exe
echo  This .exe bundles Ghostscript - no install needed on target
echo  machines. Just copy the .exe anywhere and run it.
echo ============================================================
echo.
pause
