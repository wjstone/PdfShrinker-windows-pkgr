# PDF Shrinker

A simple, drag-and-drop-style Windows GUI app that reduces PDF file sizes.

## Quick Start

### Run from source
```
pip install -r requirements.txt
python pdf_shrinker.py
```

### Build a standalone .exe
```
build.bat
```
The finished executable lands in `dist\PDF Shrinker.exe` — copy it anywhere, no Python required.

---

## Compression Modes

### With Ghostscript (recommended — much better results)
Install Ghostscript from https://ghostscript.com/releases/gsdnld.html  
The app detects it automatically. Four presets are available:

| Preset   | DPI  | Best for                          |
|----------|------|-----------------------------------|
| screen   |  72  | Email / web — smallest file       |
| ebook    | 150  | E-readers — good balance          |
| printer  | 300  | Desktop printing                  |
| prepress | 300+ | Commercial printing               |

### Without Ghostscript (built-in)
Uses `pypdf` + `Pillow` to re-compress embedded images.  
A quality slider (10–95) controls JPEG compression of images.  
Text-only PDFs shrink less with this method.

---

## Tips

- **Scanned PDFs** (all images) compress best with Ghostscript `screen` or `ebook`.
- **Text-heavy PDFs** may not shrink much regardless of method.
- If the output is *larger* than the input, the original was already well-compressed — just keep the original.

## Dependencies

| Package      | Purpose                      |
|--------------|------------------------------|
| pypdf        | PDF reading / writing        |
| Pillow       | Image recompression          |
| pyinstaller  | Build standalone .exe        |
| Ghostscript  | Optional — deep compression  |
