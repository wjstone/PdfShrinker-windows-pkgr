# PDF Shrinker

A lightweight Windows desktop app that compresses PDF files using Ghostscript. Drag a PDF onto the `.exe`, pick a quality preset, and get a smaller file — no install required on target machines.

---

## For End Users — Using the App

### Option 1: Drag and Drop
Drag any `.pdf` file directly onto `PDF Shrinker.exe`. The app opens with the input and output fields already filled in. Just click **Compress PDF**.

### Option 2: Browse for a File
Open `PDF Shrinker.exe`, click **Browse…** next to the Input field, select your PDF, then click **Compress PDF**.

The output file is saved alongside the original with `_compressed` added to the filename (e.g. `report.pdf` → `report_compressed.pdf`). You can change the output path at any time using the second Browse button.

### Compression Presets

| Preset | Image DPI | Best For | Typical Savings |
|--------|-----------|----------|-----------------|
| screen (72 dpi – smallest) | 72 | Email, web sharing | 60–85% |
| ebook (150 dpi – balanced) | 150 | General use, e-readers | 40–70% |
| printer (300 dpi – quality) | 300 | Desktop printing | 20–50% |
| prepress (high quality) | 300+ | Commercial/professional printing | 10–30% |

> **Tip:** If a compressed file ends up *larger* than the original, the source PDF was already well-optimised. Keep the original.

### Progress Bar
The progress bar tracks compression page-by-page in real time. The status line shows the current percentage. When finished, the result panel displays the original size, compressed size, and total savings.

---

## For Developers — Building the App

### Requirements

| Tool | Version | Download |
|------|---------|----------|
| Python | 3.10 or newer | https://www.python.org/downloads/ |
| Ghostscript | Any recent version | https://ghostscript.com/releases/gsdnld.html |

> **Important:** Both Python and Ghostscript only need to be installed on the **machine you build on**. The resulting `.exe` is fully self-contained and needs neither on target machines.

When installing Python, check **"Add Python to PATH"** in the installer.

### Python Dependencies

These are installed automatically by `build.bat`, but can also be installed manually:

```
pip install pypdf Pillow pyinstaller
```

| Package | Purpose | PyPI |
|---------|---------|------|
| `pypdf` | PDF reading, page counting, fallback compression | https://pypi.org/project/pypdf/ |
| `Pillow` | Image recompression (fallback mode) | https://pypi.org/project/Pillow/ |
| `pyinstaller` | Packages everything into a single `.exe` | https://pypi.org/project/pyinstaller/ |

### Building

1. Install Python and Ghostscript on your build machine
2. Unzip the project folder
3. Double-click `build.bat`

The script will:
- Auto-detect your Ghostscript installation
- Copy the GS binaries (`gswin64.exe` / `gswin64c.exe`, DLLs, fonts, and resource files) into a staging folder
- Install Python dependencies via `pip`
- Run PyInstaller to produce a single bundled `.exe`
- Clean up all staging files

**Output:** `dist\PDF Shrinker.exe`

That file is the only thing you need to distribute. Copy it anywhere, put it on a USB drive, share it — no Python, no Ghostscript, no installer needed on the receiving end.

### Build Troubleshooting

**`'pyinstaller' is not recognized`**
Your Python Scripts folder is not on PATH. `build.bat` handles this by calling `python -m PyInstaller` instead of the `pyinstaller` command directly. If you hit this manually, run `python -m pip install pyinstaller`.

**`Ghostscript not found`**
The script scans `C:\Program Files\gs\gs*\bin\` and `C:\Program Files (x86)\gs\gs*\bin\` and also checks PATH. If it still fails, confirm Ghostscript is installed and try adding its `bin` folder to your system PATH manually.

**Antivirus false positive**
Some antivirus software flags PyInstaller-packaged executables. This is a known false positive — PyInstaller bundles a Python interpreter and DLLs into a single file, which can look suspicious to heuristic scanners. Whitelist the output `.exe` in your AV software if needed.

---

## How It Works

### Compression Engine
The app uses Ghostscript to reprocess PDF content. Ghostscript re-renders each page at the target DPI and re-encodes all embedded images, fonts, and streams — this is why it achieves much better compression than tools that only strip metadata.

The GS command used internally:
```
gswin64.exe -sDEVICE=pdfwrite -dCompatibilityLevel=1.4
            -dPDFSETTINGS=/<preset> -dNOPAUSE -dBATCH
            -sOutputFile=<output.pdf> <input.pdf>
```

### Bundled Ghostscript
At build time, `build.bat` copies the Ghostscript binary and all required support files into the PyInstaller bundle under a `gs_bin/` subfolder. A small marker file (`gs_exe_name.txt`) records which executable name was found (e.g. `gswin64.exe` vs `gswin64c.exe`) so the app can locate it at runtime regardless of which GS variant was installed on the build machine.

At runtime, the app checks `sys._MEIPASS/gs_bin/` first (the PyInstaller temp directory), then falls back to any system-installed Ghostscript. It sets the `GS_LIB` environment variable so Ghostscript can find its fonts and resource files inside the bundle.

### Live Progress
Ghostscript prints `Page N` to stdout as it processes each page. The app reads this output line-by-line in a background thread and converts page number / total pages into a 0–95% progress value. The final 5% completes when the process exits successfully. The console window is suppressed using the Windows `CREATE_NO_WINDOW` process flag.

### Fallback Mode (no Ghostscript)
If no Ghostscript is detected, the app falls back to a pure-Python pipeline using `pypdf` and `Pillow`. It re-compresses embedded images as JPEG at a user-chosen quality level (10–95) and strips redundant objects. This works for any PDF without external dependencies but is less effective than Ghostscript, especially for scanned documents.

### Drag and Drop
Windows passes a dragged file's path as `sys.argv[1]` when a file is dropped onto an `.exe`. The app checks for this on startup and pre-populates both the input and output fields automatically.

---

## File Structure

```
pdf_shrinker/
├── pdf_shrinker.py   — Main application (GUI + compression logic)
├── build.bat         — Build script: detects GS, stages binaries, runs PyInstaller
├── requirements.txt  — Python dependencies
└── README.md         — This file
```

After building:
```
pdf_shrinker/
└── dist/
    └── PDF Shrinker.exe   — The distributable app (~35–50 MB)
```

---

## License & Third-Party Components

This project is unlicensed — use it however you like.

Third-party components bundled in the output `.exe`:

| Component | License | Link |
|-----------|---------|------|
| Ghostscript | AGPL v3 (free for personal/open-source use; commercial license available) | https://ghostscript.com/licensing/index.html |
| pypdf | BSD 3-Clause | https://github.com/py-pdf/pypdf/blob/main/LICENSE |
| Pillow | HPND | https://github.com/python-pillow/Pillow/blob/main/LICENSE |
| Python | PSF License | https://docs.python.org/3/license.html |

> **Note on Ghostscript licensing:** Ghostscript is AGPL-licensed. Bundling it in a distributed application is permitted for personal and open-source use. For commercial distribution, review the Artifex commercial licensing page at https://artifex.com/licensing/

---

## Links

| Resource | URL |
|----------|-----|
| Python download | https://www.python.org/downloads/ |
| Ghostscript download | https://ghostscript.com/releases/gsdnld.html |
| Ghostscript commercial license | https://artifex.com/licensing/ |
| pypdf documentation | https://pypdf.readthedocs.io/ |
| Pillow documentation | https://pillow.readthedocs.io/ |
| PyInstaller documentation | https://pyinstaller.org/en/stable/ |
