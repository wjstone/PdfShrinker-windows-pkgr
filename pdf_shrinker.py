"""
PDF Shrinker - A simple GUI tool to reduce PDF file sizes.
Requires: pypdf, Pillow
Optional: Ghostscript (for deeper compression)
Package with: pyinstaller --onefile --windowed pdf_shrinker.py
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os
import sys
import subprocess
import io
import shutil
from pathlib import Path


# ── Ghostscript detection ────────────────────────────────────────────────────

def find_ghostscript():
    """Return path to gs/gswin64c, or None if not found.
    Checks the PyInstaller bundle first, then the host system."""

    # ── 1. Bundled copy (PyInstaller _MEIPASS) ──────────────────────────────
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        gs_bin = Path(bundle_dir) / "gs_bin"
        marker = gs_bin / "gs_exe_name.txt"
        if marker.exists():
            exe_name = marker.read_text().strip()
            bundled = gs_bin / exe_name
            if bundled.exists():
                # Tell GS where its resource files are
                os.environ.setdefault("GS_LIB",
                    str(gs_bin / "lib") + os.pathsep +
                    str(gs_bin / "fonts") + os.pathsep +
                    str(gs_bin / "Resource"))
                return str(bundled)

    # ── 2. System installation ───────────────────────────────────────────────
    candidates = [
        "gswin64c", "gswin64", "gswin32c", "gswin32", "gs",  # PATH
    ]
    # Scan C:\Program Files\gs\* dynamically (newest first)
    for prog_files in [r"C:\Program Files", r"C:\Program Files (x86)"]:
        gs_root = Path(prog_files) / "gs"
        if gs_root.exists():
            for ver_dir in sorted(gs_root.iterdir(), reverse=True):
                for exe in ["gswin64c.exe", "gswin64.exe", "gswin32c.exe", "gswin32.exe"]:
                    p = ver_dir / "bin" / exe
                    if p.exists():
                        candidates.append(str(p))

    for c in candidates:
        path = shutil.which(c) or (c if os.path.isfile(c) else None)
        if path:
            return path
    return None


GS_PATH = find_ghostscript()

GS_PRESETS = {
    "screen (72 dpi – smallest)":  "screen",
    "ebook (150 dpi – balanced)":  "ebook",
    "printer (300 dpi – quality)": "printer",
    "prepress (high quality)":     "prepress",
}


# ── Compression back-ends ────────────────────────────────────────────────────

def compress_with_ghostscript(src: str, dst: str, preset: str,
                               progress_cb=None) -> tuple[int, int]:
    """Run Ghostscript with live per-page progress and no console window."""
    from pypdf import PdfReader
    orig = os.path.getsize(src)

    # Count pages so we can report real progress
    try:
        total_pages = len(PdfReader(src).pages)
    except Exception:
        total_pages = 0

    # Remove -dQUIET so GS prints "Page N" lines we can parse
    cmd = [
        GS_PATH,
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.4",
        f"-dPDFSETTINGS=/{preset}",
        "-dNOPAUSE", "-dBATCH",
        f"-sOutputFile={dst}",
        src,
    ]

    CREATE_NO_WINDOW = 0x08000000  # Windows flag - suppresses the CMD box
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=CREATE_NO_WINDOW,
    )

    page_num = 0
    for line in proc.stdout:
        line = line.strip()
        if line.startswith("Page "):
            try:
                page_num = int(line.split()[1])
                if progress_cb and total_pages:
                    pct = min(95, int(page_num / total_pages * 95))
                    progress_cb(pct)
            except (ValueError, IndexError):
                pass

    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("Ghostscript failed (exit code " + str(proc.returncode) + ")")

    if progress_cb:
        progress_cb(100)
    return orig, os.path.getsize(dst)


def compress_with_pypdf(src: str, dst: str, image_quality: int,
                         progress_cb=None) -> tuple[int, int]:
    """Pure-Python compression: stream compression + image resampling."""
    from pypdf import PdfReader, PdfWriter
    from PIL import Image

    orig = os.path.getsize(src)
    reader = PdfReader(src)
    writer = PdfWriter()
    total = len(reader.pages)

    for i, page in enumerate(reader.pages):
        # Re-compress images embedded in this page
        for img_key in list(page.images):
            try:
                img_obj = page.images[img_key]
                pil = Image.open(io.BytesIO(img_obj.data))
                # Convert RGBA/P → RGB for JPEG
                if pil.mode in ("RGBA", "P"):
                    pil = pil.convert("RGB")
                buf = io.BytesIO()
                pil.save(buf, format="JPEG", quality=image_quality,
                         optimize=True)
                img_obj.replace(buf.getvalue(), name="/DCTDecode")
            except Exception:
                pass  # leave unchanged if anything fails

        writer.add_page(page)
        if progress_cb:
            progress_cb(int((i + 1) / total * 90))

    writer.compress_identical_objects(remove_identicals=True, remove_orphans=True)
    with open(dst, "wb") as f:
        writer.write(f)

    if progress_cb:
        progress_cb(100)
    return orig, os.path.getsize(dst)


# ── Helpers ──────────────────────────────────────────────────────────────────

def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def default_output(src: str) -> str:
    p = Path(src)
    return str(p.parent / f"{p.stem}_compressed{p.suffix}")


# ── GUI ──────────────────────────────────────────────────────────────────────

DARK   = "#1e1e2e"
PANEL  = "#2a2a3e"
ACCENT = "#7c6af7"
GREEN  = "#50fa7b"
RED    = "#ff5555"
FG     = "#cdd6f4"
SUBTLE = "#6c7086"
ENTRY  = "#313244"


class PDFShrinkerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PDF Shrinker")
        self.resizable(False, False)
        self.configure(bg=DARK)
        self._build_ui()
        self._center()

    def _center(self):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"+{(sw-w)//2}+{(sh-h)//2}")

    # ── Layout ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        pad = dict(padx=20, pady=10)

        # Title bar
        hdr = tk.Frame(self, bg=PANEL, height=56)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⬛ PDF Shrinker", font=("Segoe UI", 16, "bold"),
                 fg=ACCENT, bg=PANEL).pack(side="left", padx=20, pady=12)
        gs_txt = f"Ghostscript ✓" if GS_PATH else "Ghostscript ✗ (using built-in)"
        gs_col = GREEN if GS_PATH else SUBTLE
        tk.Label(hdr, text=gs_txt, font=("Segoe UI", 9),
                 fg=gs_col, bg=PANEL).pack(side="right", padx=20, pady=16)

        body = tk.Frame(self, bg=DARK, padx=24, pady=16)
        body.pack(fill="both")

        # ── Input file
        self._section(body, "Input PDF")
        row = tk.Frame(body, bg=DARK)
        row.pack(fill="x", pady=(4, 0))
        self.inp_var = tk.StringVar()
        self.inp_entry = self._entry(row, self.inp_var, width=52)
        self.inp_entry.pack(side="left", fill="x", expand=True)
        self._btn(row, "Browse…", self._browse_input).pack(side="left", padx=(8, 0))

        # ── Output file
        self._section(body, "Output PDF")
        row2 = tk.Frame(body, bg=DARK)
        row2.pack(fill="x", pady=(4, 0))
        self.out_var = tk.StringVar()
        self._entry(row2, self.out_var, width=52).pack(side="left", fill="x", expand=True)
        self._btn(row2, "Browse…", self._browse_output).pack(side="left", padx=(8, 0))

        # ── Settings
        self._section(body, "Compression Settings")
        cfg = tk.Frame(body, bg=DARK)
        cfg.pack(fill="x", pady=(4, 0))

        if GS_PATH:
            tk.Label(cfg, text="Preset:", font=("Segoe UI", 10),
                     fg=FG, bg=DARK).grid(row=0, column=0, sticky="w")
            self.preset_var = tk.StringVar(value=list(GS_PRESETS)[1])
            cb = ttk.Combobox(cfg, textvariable=self.preset_var,
                               values=list(GS_PRESETS), state="readonly", width=30)
            cb.grid(row=0, column=1, sticky="w", padx=(10, 0))
            self._style_combo(cb)
        else:
            tk.Label(cfg, text="Image quality:", font=("Segoe UI", 10),
                     fg=FG, bg=DARK).grid(row=0, column=0, sticky="w")
            self.quality_var = tk.IntVar(value=60)
            sl = ttk.Scale(cfg, from_=10, to=95, variable=self.quality_var,
                            orient="horizontal", length=200)
            sl.grid(row=0, column=1, padx=(10, 0))
            self.q_lbl = tk.Label(cfg, text="60", font=("Segoe UI", 10),
                                   fg=ACCENT, bg=DARK, width=3)
            self.q_lbl.grid(row=0, column=2, padx=(6, 0))
            self.quality_var.trace_add("write",
                lambda *_: self.q_lbl.config(text=str(self.quality_var.get())))

        # ── Progress
        self.prog_var = tk.DoubleVar(value=0)
        self.prog_bar = ttk.Progressbar(body, variable=self.prog_var,
                                         maximum=100, length=480)
        self.prog_bar.pack(pady=(20, 4))
        self._style_progress()

        self.status_var = tk.StringVar(value="Ready")
        tk.Label(body, textvariable=self.status_var, font=("Segoe UI", 9),
                 fg=SUBTLE, bg=DARK).pack()

        # ── Result card
        self.result_frame = tk.Frame(body, bg=PANEL, bd=0,
                                      highlightthickness=0, padx=16, pady=12)
        self.result_frame.pack(fill="x", pady=(12, 0))
        self.r_orig  = self._result_label(self.result_frame, "Original", "—", 0)
        self.r_new   = self._result_label(self.result_frame, "Compressed", "—", 1)
        self.r_saved = self._result_label(self.result_frame, "Savings", "—", 2)
        self.result_frame.columnconfigure((0, 1, 2), weight=1)

        # ── Compress button
        self.go_btn = tk.Button(body, text="Compress PDF",
                                 font=("Segoe UI", 12, "bold"),
                                 bg=ACCENT, fg="white", relief="flat",
                                 padx=32, pady=10, cursor="hand2",
                                 activebackground="#6a5af0",
                                 command=self._run)
        self.go_btn.pack(pady=(20, 4))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _section(self, parent, text):
        tk.Label(parent, text=text.upper(),
                 font=("Segoe UI", 8, "bold"), fg=SUBTLE, bg=DARK
                 ).pack(anchor="w", pady=(14, 0))

    def _entry(self, parent, var, width=40):
        e = tk.Entry(parent, textvariable=var, width=width,
                     bg=ENTRY, fg=FG, insertbackground=FG,
                     relief="flat", font=("Segoe UI", 10), bd=6)
        return e

    def _btn(self, parent, text, cmd):
        return tk.Button(parent, text=text, command=cmd,
                         bg=PANEL, fg=FG, relief="flat",
                         font=("Segoe UI", 10), padx=10, pady=5,
                         cursor="hand2", activebackground=ENTRY)

    def _result_label(self, parent, title, value, col):
        f = tk.Frame(parent, bg=PANEL)
        f.grid(row=0, column=col, padx=8, sticky="ew")
        tk.Label(f, text=title, font=("Segoe UI", 8), fg=SUBTLE, bg=PANEL).pack()
        lbl = tk.Label(f, text=value, font=("Segoe UI", 14, "bold"),
                        fg=FG, bg=PANEL)
        lbl.pack()
        return lbl

    def _style_combo(self, cb):
        s = ttk.Style()
        s.theme_use("default")
        s.configure("TCombobox", fieldbackground=ENTRY, background=ENTRY,
                     foreground=FG, selectbackground=ACCENT)

    def _style_progress(self):
        s = ttk.Style()
        s.theme_use("default")
        s.configure("TProgressbar", troughcolor=PANEL,
                     background=ACCENT, borderwidth=0, relief="flat")

    # ── Actions ───────────────────────────────────────────────────────────────

    def _browse_input(self):
        f = filedialog.askopenfilename(title="Select PDF",
                                        filetypes=[("PDF files", "*.pdf")])
        if f:
            self.inp_var.set(f)
            if not self.out_var.get():
                self.out_var.set(default_output(f))

    def _browse_output(self):
        f = filedialog.asksaveasfilename(title="Save compressed PDF as",
                                          defaultextension=".pdf",
                                          filetypes=[("PDF files", "*.pdf")])
        if f:
            self.out_var.set(f)

    def _run(self):
        src = self.inp_var.get().strip()
        dst = self.out_var.get().strip()
        if not src or not os.path.isfile(src):
            messagebox.showerror("Error", "Please select a valid input PDF.")
            return
        if not dst:
            messagebox.showerror("Error", "Please specify an output file.")
            return

        self.go_btn.config(state="disabled")
        self.prog_var.set(0)
        self.status_var.set("Compressing…")

        def task():
            try:
                def cb(pct):
                    self.after(0, lambda p=pct: (
                        self.prog_var.set(p),
                        self.status_var.set(f"Processing… {p}%")
                    ))

                if GS_PATH:
                    preset = GS_PRESETS[self.preset_var.get()]
                    orig, new = compress_with_ghostscript(src, dst, preset, cb)
                else:
                    q = self.quality_var.get()
                    orig, new = compress_with_pypdf(src, dst, q, cb)

                savings = orig - new
                pct = savings / orig * 100 if orig else 0

                def update():
                    self.r_orig.config(text=human_size(orig))
                    self.r_new.config(text=human_size(new))
                    saved_txt = f"-{human_size(savings)} ({pct:.1f}%)"
                    color = GREEN if savings > 0 else RED
                    self.r_saved.config(text=saved_txt, fg=color)
                    self.status_var.set("Done! ✓")
                    self.go_btn.config(state="normal")

                self.after(0, update)

            except Exception as e:
                def err():
                    messagebox.showerror("Compression failed", str(e))
                    self.status_var.set("Error.")
                    self.go_btn.config(state="normal")
                self.after(0, err)

        threading.Thread(target=task, daemon=True).start()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = PDFShrinkerApp()
    # Support drag-and-drop onto the .exe: Windows passes the file as argv[1]
    if len(sys.argv) > 1:
        dropped = sys.argv[1]
        if os.path.isfile(dropped) and dropped.lower().endswith(".pdf"):
            app.inp_var.set(dropped)
            app.out_var.set(default_output(dropped))
    app.mainloop()
