#!/usr/bin/env bash
# =============================================================================
#  PDF Shrinker – macOS Build Script (Bundled Ghostscript)
#  Requires: Ghostscript and dylibbundler via Homebrew
#
#  Install prerequisites:
#    brew install ghostscript dylibbundler python-tk
# =============================================================================
set -euo pipefail

echo "============================================================"
echo " PDF Shrinker – macOS Build Script (Bundled Ghostscript)"
echo "============================================================"
echo

# ── Helper ────────────────────────────────────────────────────────────────────
die() { echo "ERROR: $*" >&2; exit 1; }

# ── Check tools ───────────────────────────────────────────────────────────────
command -v dylibbundler >/dev/null 2>&1 || die "dylibbundler not found. Run: brew install dylibbundler"

# ── Find a Python that has tkinter ───────────────────────────────────────────
# macOS system Python and plain Homebrew python omit tkinter.
# brew install python-tk provides a tk-enabled build at a versioned path.
PYTHON=""

# Check Homebrew python-tk installs (newest first)
for candidate in \
    "/opt/homebrew/opt/python-tk@3.14/bin/python3.14" \
    "/opt/homebrew/opt/python-tk@3.13/bin/python3.13" \
    "/opt/homebrew/opt/python-tk@3.12/bin/python3.12" \
    "/opt/homebrew/opt/python-tk@3.11/bin/python3.11" \
    "/opt/homebrew/opt/python-tk@3.10/bin/python3.10" \
    "/usr/local/opt/python-tk@3.14/bin/python3.14" \
    "/usr/local/opt/python-tk@3.13/bin/python3.13" \
    "/usr/local/opt/python-tk@3.12/bin/python3.12"
do
    if [[ -x "$candidate" ]]; then
        # Verify tkinter actually works
        if "$candidate" -c "import tkinter" 2>/dev/null; then
            PYTHON="$candidate"
            break
        fi
    fi
done

# Fallback: scan any python3 on PATH
if [[ -z "$PYTHON" ]]; then
    for candidate in $(command -v python3.14 python3.13 python3.12 python3.11 python3.10 2>/dev/null || true); do
        if "$candidate" -c "import tkinter" 2>/dev/null; then
            PYTHON="$candidate"
            break
        fi
    done
fi

if [[ -z "$PYTHON" ]]; then
    echo
    echo "ERROR: Could not find a Python installation with tkinter."
    echo "  Fix: brew install python-tk"
    echo "  Then re-run this script."
    echo
    exit 1
fi

echo "Found Python with tkinter: $PYTHON"
echo

# ── Locate Ghostscript binary ─────────────────────────────────────────────────
GS_BIN=""
for candidate in \
    "/opt/homebrew/bin/gs" \
    "/usr/local/bin/gs" \
    "/opt/local/bin/gs" \
    "$(command -v gs 2>/dev/null || true)"
do
    if [[ -x "$candidate" ]]; then
        GS_BIN="$candidate"
        break
    fi
done

[[ -n "$GS_BIN" ]] || die "Ghostscript not found. Run: brew install ghostscript"
echo "Found Ghostscript: $GS_BIN ($(\"$GS_BIN\" --version))"
echo

# ── Locate Ghostscript resource files ─────────────────────────────────────────
# GS 10.07+ is built --without-versioned-path: resources live directly in
# share/ghostscript/ with no version subfolder. Older builds use share/ghostscript/<ver>/.
GS_SHARE=""

for share_root in \
    "/opt/homebrew/share/ghostscript" \
    "/usr/local/share/ghostscript" \
    "/opt/local/share/ghostscript"
do
    [[ -d "$share_root" ]] || continue
    # New unversioned layout (10.07+)
    if [[ -d "$share_root/lib" || -d "$share_root/Resource" ]]; then
        GS_SHARE="$share_root"
        break
    fi
    # Old versioned layout
    versioned=$(ls -d "$share_root"/[0-9]* 2>/dev/null | sort -V | tail -1 || true)
    if [[ -d "$versioned" ]]; then
        GS_SHARE="$versioned"
        break
    fi
done

[[ -d "$GS_SHARE" ]] || die "Could not find Ghostscript resources. Is Ghostscript installed via Homebrew?"
echo "GS resources: $GS_SHARE"
echo

# ── Stage GS binary + dylibs ──────────────────────────────────────────────────
echo "[1/5] Staging Ghostscript binary and libraries..."
rm -rf gs_bin
mkdir -p gs_bin/libs

cp "$GS_BIN" gs_bin/gs

dylibbundler \
    -b \
    -x gs_bin/gs \
    -d gs_bin/libs \
    -p @executable_path/libs \
    -od \
    2>&1 | grep -v "^$" || true

echo "  Collected $(ls gs_bin/libs | wc -l | tr -d ' ') dylibs"

# ── Stage GS resource files ───────────────────────────────────────────────────
echo "[2/5] Staging Ghostscript resources..."
[[ -d "$GS_SHARE/lib"      ]] && cp -r "$GS_SHARE/lib"      gs_bin/lib
[[ -d "$GS_SHARE/Resource" ]] && cp -r "$GS_SHARE/Resource" gs_bin/Resource

GS_FONTS=""
for p in "$GS_SHARE/fonts" "$(dirname "$GS_SHARE")/fonts" \
         "/opt/homebrew/share/ghostscript/fonts" "/usr/local/share/ghostscript/fonts"; do
    [[ -d "$p" ]] && GS_FONTS="$p" && break
done
[[ -n "$GS_FONTS" ]] && cp -r "$GS_FONTS" gs_bin/fonts || echo "  (no fonts dir found — continuing)"

echo "gs" > gs_bin/gs_exe_name.txt
echo

# ── Set up venv + install deps ────────────────────────────────────────────────
# We use a venv to avoid macOS PEP 668 restrictions on system-wide pip installs.
echo "[3/5] Setting up build environment..."
"$PYTHON" -m venv .build_venv
source .build_venv/bin/activate
pip install --quiet pypdf Pillow pyinstaller
echo

# ── Build with PyInstaller ────────────────────────────────────────────────────
echo "[4/5] Building app bundle (this takes a minute)..."
python -m PyInstaller \
    --windowed \
    --name "PDF Shrinker" \
    --add-data "gs_bin:gs_bin" \
    --icon "app_icon.icns" \
    --clean \
    --noconfirm \
    pdf_shrinker.py
deactivate
echo

# ── Cleanup ───────────────────────────────────────────────────────────────────
echo "[5/5] Cleaning up..."
rm -rf gs_bin build "PDF Shrinker.spec" .build_venv

echo
echo "============================================================"
echo " Build complete!"
echo " Output: dist/PDF Shrinker.app"
echo
echo " Drag PDF Shrinker.app to your Applications folder."
echo
echo " NOTE: macOS may block unsigned apps. If you see a"
echo " 'cannot be opened' warning, run:"
echo "   xattr -cr \"dist/PDF Shrinker.app\""
echo "============================================================"
echo
