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
    if sys.platform == "win32":
        candidates = ["gswin64c", "gswin64", "gswin32c", "gswin32", "gs"]
        for prog_files in [r"C:\Program Files", r"C:\Program Files (x86)"]:
            gs_root = Path(prog_files) / "gs"
            if gs_root.exists():
                for ver_dir in sorted(gs_root.iterdir(), reverse=True):
                    for exe in ["gswin64c.exe", "gswin64.exe", "gswin32c.exe", "gswin32.exe"]:
                        p = ver_dir / "bin" / exe
                        if p.exists():
                            candidates.append(str(p))
    else:
        # macOS — Homebrew (Apple Silicon and Intel) and MacPorts
        candidates = [
            "/opt/homebrew/bin/gs",   # Homebrew Apple Silicon (M1/M2/M3)
            "/usr/local/bin/gs",      # Homebrew Intel
            "/opt/local/bin/gs",      # MacPorts
            "gs",                     # PATH fallback
        ]

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

    # CREATE_NO_WINDOW suppresses the CMD box on Windows; not needed/available on Mac
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x08000000
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        **kwargs,
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

# Light, native-feeling palette
BG       = "#f5f5f5"   # window background
SURFACE  = "#ffffff"   # card / input surface
BORDER   = "#d1d1d1"   # subtle borders
BORDER2  = "#b0b0b0"   # hover / emphasis borders
FG       = "#1a1a1a"   # primary text
FG2      = "#555555"   # secondary text
FG3      = "#888888"   # hint / label text
ACCENT   = "#1a1a1a"   # primary button bg (near-black)
ACCENT_H = "#333333"   # primary button hover
SEL_BG   = "#dbeafe"   # preset selected background (blue-50)
SEL_FG   = "#1d4ed8"   # preset selected text (blue-700)
SEL_BD   = "#93c5fd"   # preset selected border (blue-300)
SUCCESS_BG = "#dcfce7" # savings card bg (green-100)
SUCCESS_FG = "#166534" # savings card text (green-800)
ERR_FG   = "#dc2626"   # error red

# Platform-appropriate font
import platform as _platform
if _platform.system() == "Darwin":
    FONT = "-apple-system"
    _SIZE = lambda n: n - 1   # macOS renders slightly larger
else:
    FONT = "Segoe UI"
    _SIZE = lambda n: n

def F(size, weight="normal"):
    return (FONT, _SIZE(size), weight)


class PDFShrinkerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PDF Shrinker")
        self.resizable(False, False)
        self.configure(bg=BG)
        self._setup_styles()
        self._build_ui()
        self._center()

    def _center(self):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"+{(sw-w)//2}+{(sh-h)//2}")

    def _setup_styles(self):
        s = ttk.Style()
        s.theme_use("default")
        s.configure("TProgressbar",
                     troughcolor=BORDER,
                     background=ACCENT,
                     borderwidth=0,
                     relief="flat",
                     thickness=4)

    # ── Layout ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Header ───────────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=SURFACE,
                       highlightbackground=BORDER, highlightthickness=1)
        hdr.pack(fill="x")
        tk.Label(hdr, text="PDF Shrinker", font=F(14, "bold"),
                 fg=FG, bg=SURFACE).pack(side="left", padx=18, pady=12)

        gs_dot  = "●" if GS_PATH else "○"
        gs_txt  = "Ghostscript ready" if GS_PATH else "Built-in mode"
        gs_col  = "#16a34a" if GS_PATH else FG3
        gs_lbl  = tk.Frame(hdr, bg=SURFACE)
        gs_lbl.pack(side="right", padx=18, pady=12)
        tk.Label(gs_lbl, text=gs_dot, font=F(9), fg=gs_col, bg=SURFACE).pack(side="left")
        tk.Label(gs_lbl, text=f" {gs_txt}", font=F(10), fg=FG3, bg=SURFACE).pack(side="left")

        # ── Body ─────────────────────────────────────────────────────────────
        body = tk.Frame(self, bg=BG, padx=20, pady=18)
        body.pack(fill="both")

        # ── Input
        self._label(body, "Input PDF")
        row = tk.Frame(body, bg=BG)
        row.pack(fill="x", pady=(5, 0))
        self.inp_var = tk.StringVar()
        self._entry(row, self.inp_var).pack(side="left", fill="x", expand=True)
        self._browse_btn(row, "Browse…", self._browse_input).pack(side="left", padx=(6, 0))

        # ── Output
        self._label(body, "Output PDF", top=14)
        row2 = tk.Frame(body, bg=BG)
        row2.pack(fill="x", pady=(5, 0))
        self.out_var = tk.StringVar()
        self._entry(row2, self.out_var).pack(side="left", fill="x", expand=True)
        self._browse_btn(row2, "Browse…", self._browse_output).pack(side="left", padx=(6, 0))

        # ── Preset buttons (GS) or quality slider (fallback)
        self._label(body, "Quality preset" if GS_PATH else "Image quality", top=14)
        if GS_PATH:
            self._build_presets(body)
        else:
            self._build_quality_slider(body)

        # ── Progress bar (slim, native-style)
        self.prog_var = tk.DoubleVar(value=0)
        prog_wrap = tk.Frame(body, bg=BG)
        prog_wrap.pack(fill="x", pady=(18, 0))
        self.prog_bar = ttk.Progressbar(prog_wrap, variable=self.prog_var,
                                         maximum=100, style="TProgressbar")
        self.prog_bar.pack(fill="x")

        status_row = tk.Frame(body, bg=BG)
        status_row.pack(fill="x", pady=(4, 0))
        self.status_var = tk.StringVar(value="Ready")
        tk.Label(status_row, textvariable=self.status_var,
                 font=F(10), fg=FG3, bg=BG).pack(side="left")

        # ── Stats cards
        cards = tk.Frame(body, bg=BG)
        cards.pack(fill="x", pady=(16, 0))
        cards.columnconfigure((0, 1, 2), weight=1)

        self.r_orig  = self._stat_card(cards, "Original",    "—", 0, success=False)
        self.r_new   = self._stat_card(cards, "Compressed",  "—", 1, success=False)
        self.r_saved = self._stat_card(cards, "Saved",       "—", 2, success=False)
        self._saved_card_frame = cards.grid_slaves(row=0, column=2)[0]

        # ── Compress button
        self.go_btn = tk.Button(
            body, text="Compress PDF",
            font=F(12, "bold"),
            bg=ACCENT, fg=SURFACE,
            relief="flat", bd=0,
            padx=0, pady=10,
            cursor="hand2",
            activebackground=ACCENT_H,
            activeforeground=SURFACE,
            command=self._run
        )
        self.go_btn.pack(fill="x", pady=(16, 4))

        # Subtle hover effect on button
        self.go_btn.bind("<Enter>", lambda e: self.go_btn.config(bg=ACCENT_H))
        self.go_btn.bind("<Leave>", lambda e: self.go_btn.config(bg=ACCENT))

    # ── Preset toggle buttons ─────────────────────────────────────────────────

    def _build_presets(self, parent):
        PRESET_LABELS = [
            ("Screen",   "72 dpi",  "screen"),
            ("Ebook",    "150 dpi", "ebook"),
            ("Printer",  "300 dpi", "printer"),
            ("Prepress", "300+ dpi","prepress"),
        ]
        self._preset_key = tk.StringVar(value="ebook")
        self._preset_btns = {}

        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(5, 0))
        row.columnconfigure((0,1,2,3), weight=1)

        for col, (label, sub, key) in enumerate(PRESET_LABELS):
            btn = tk.Button(
                row,
                text=label + "\n" + sub,
                font=F(10),
                relief="flat", bd=0,
                padx=4, pady=7,
                cursor="hand2",
                justify="center",
                command=lambda k=key: self._select_preset(k),
                highlightthickness=1,
            )
            btn.grid(row=0, column=col, padx=(0, 4) if col < 3 else 0, sticky="ew")
            self._preset_btns[key] = btn

        self._select_preset("ebook")

    def _select_preset(self, key):
        self._preset_key.set(key)
        for k, btn in self._preset_btns.items():
            if k == key:
                btn.config(bg=SEL_BG, fg=SEL_FG,
                           highlightbackground=SEL_BD,
                           font=F(10, "bold"))
            else:
                btn.config(bg=SURFACE, fg=FG2,
                           highlightbackground=BORDER,
                           font=F(10))

    def _build_quality_slider(self, parent):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(5, 0))
        self.quality_var = tk.IntVar(value=60)
        sl = ttk.Scale(row, from_=10, to=95, variable=self.quality_var,
                        orient="horizontal")
        sl.pack(side="left", fill="x", expand=True)
        self.q_lbl = tk.Label(row, text="60", font=F(10), fg=FG, bg=BG, width=3)
        self.q_lbl.pack(side="left", padx=(8, 0))
        self.quality_var.trace_add("write",
            lambda *_: self.q_lbl.config(text=str(self.quality_var.get())))

    # ── Widget helpers ────────────────────────────────────────────────────────

    def _label(self, parent, text, top=0):
        tk.Label(parent, text=text,
                 font=F(10, "bold"), fg=FG2, bg=BG
                 ).pack(anchor="w", pady=(top, 0))

    def _entry(self, parent, var):
        e = tk.Entry(parent, textvariable=var,
                     bg=SURFACE, fg=FG,
                     insertbackground=FG,
                     relief="flat", bd=0,
                     font=F(10),
                     highlightthickness=1,
                     highlightbackground=BORDER,
                     highlightcolor=BORDER2)
        e.config(width=46)
        # Add inner padding via a wrapper frame
        wrap = tk.Frame(parent, bg=SURFACE,
                        highlightthickness=1,
                        highlightbackground=BORDER)
        e2 = tk.Entry(wrap, textvariable=var,
                      bg=SURFACE, fg=FG,
                      insertbackground=FG,
                      relief="flat", bd=0,
                      font=F(10))
        e2.pack(padx=8, pady=6, fill="x")
        wrap.pack_forget()  # will be managed by caller
        return wrap

    def _browse_btn(self, parent, text, cmd):
        return tk.Button(parent, text=text, command=cmd,
                         bg=SURFACE, fg=FG,
                         relief="flat", bd=0,
                         font=F(10),
                         padx=10, pady=0,
                         cursor="hand2",
                         highlightthickness=1,
                         highlightbackground=BORDER,
                         activebackground=BG)

    def _stat_card(self, parent, title, value, col, success=False):
        card_bg = SUCCESS_BG if success else "#f0f0f0"
        card_fg = SUCCESS_FG if success else FG
        lbl_fg  = SUCCESS_FG if success else FG3

        f = tk.Frame(parent, bg=card_bg, padx=12, pady=10)
        f.grid(row=0, column=col, padx=(0, 6) if col < 2 else 0, sticky="ew")
        tk.Label(f, text=title, font=F(9), fg=lbl_fg, bg=card_bg).pack(anchor="w")
        lbl = tk.Label(f, text=value, font=F(16, "bold"), fg=card_fg, bg=card_bg)
        lbl.pack(anchor="w")
        return lbl

    def _set_stat_card_success(self, col, success):
        """Re-colour a stat card after compression completes."""
        card_bg = SUCCESS_BG if success else "#f0f0f0"
        card_fg = SUCCESS_FG if success else FG
        lbl_fg  = SUCCESS_FG if success else FG3
        card = self._saved_card_frame if col == 2 else None
        if card:
            for widget in card.winfo_children():
                widget.config(bg=card_bg,
                              fg=(lbl_fg if isinstance(widget, tk.Label)
                                  and widget.cget("font") == str(F(9))
                                  else card_fg))
            card.config(bg=card_bg)

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

        self.go_btn.config(state="disabled", bg="#999999")
        self.prog_var.set(0)
        self.status_var.set("Starting…")

        def task():
            try:
                def cb(pct):
                    self.after(0, lambda p=pct: (
                        self.prog_var.set(p),
                        self.status_var.set(f"Processing… {p}%")
                    ))

                if GS_PATH:
                    preset = GS_PRESETS[self._preset_key.get()]
                    orig, new = compress_with_ghostscript(src, dst, preset, cb)
                else:
                    q = self.quality_var.get()
                    orig, new = compress_with_pypdf(src, dst, q, cb)

                savings = orig - new
                pct = savings / orig * 100 if orig else 0

                def update():
                    self.r_orig.config(text=human_size(orig))
                    self.r_new.config(text=human_size(new))
                    self.r_saved.config(text=f"{pct:.1f}%")

                    # Re-colour savings card green if we actually saved space
                    saved_card = self._saved_card_frame
                    if savings > 0:
                        saved_card.config(bg=SUCCESS_BG)
                        for w in saved_card.winfo_children():
                            w.config(bg=SUCCESS_BG,
                                     fg=SUCCESS_FG)
                    else:
                        saved_card.config(bg="#f0f0f0")
                        for w in saved_card.winfo_children():
                            w.config(bg="#f0f0f0",
                                     fg=(FG3 if w.cget("text") == "Saved" else ERR_FG))

                    self.status_var.set("Done  ✓")
                    self.go_btn.config(state="normal", bg=ACCENT)

                self.after(0, update)

            except Exception as e:
                def err():
                    messagebox.showerror("Compression failed", str(e))
                    self.status_var.set("Error.")
                    self.go_btn.config(state="normal", bg=ACCENT)
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
