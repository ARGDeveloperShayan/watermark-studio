import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image, ImageOps, ImageTk

SUPPORTED_EXT = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff")

MODE_SINGLE = "تک تصویر"
MODE_TILE   = "کاشی‌کاری"

POSITIONS = {
    "بالا - چپ":     ("left",   "top"),
    "بالا - وسط":    ("center", "top"),
    "بالا - راست":   ("right",  "top"),
    "وسط - چپ":      ("left",   "center"),
    "مرکز":          ("center", "center"),
    "وسط - راست":    ("right",  "center"),
    "پایین - چپ":    ("left",   "bottom"),
    "پایین - وسط":   ("center", "bottom"),
    "پایین - راست":  ("right",  "bottom"),
}

FONT   = ("Tahoma", 10)
FONT_B = ("Tahoma", 10, "bold")

class WatermarkApp:

    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("🎨 استودیو واترمارک")
        root.geometry("1200x820")
        root.minsize(1000, 700)

        self.wm_path            = None
        self.wm_src             = None
        self.folder_path        = None
        self.preview_source     = None
        self.preview_source_path = None

        self._preview_job = None
        self._tk_img      = None
        self._busy        = False
        self._cancel      = False

        self.var_mode     = tk.StringVar(value=MODE_SINGLE)
        self.var_position = tk.StringVar(value="پایین - راست")
        self.var_scale    = tk.DoubleVar(value=20)
        self.var_opacity  = tk.DoubleVar(value=80)
        self.var_rotation = tk.DoubleVar(value=0)
        self.var_margin   = tk.DoubleVar(value=25)
        self.var_spacing  = tk.DoubleVar(value=60)
        self.var_quality  = tk.DoubleVar(value=92)
        self.var_suffix   = tk.StringVar(value="_wm")
        self.var_output   = tk.StringVar(value="")

        self._build_ui()
        self.schedule_preview()

    def _build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TLabel", font=FONT)
        style.configure("TLabelframe.Label", font=FONT_B)
        style.configure("TButton", font=FONT, padding=6)
        style.configure("Accent.TButton", font=FONT_B, padding=8)

        main = ttk.Frame(self.root, padding=12)
        main.pack(fill="both", expand=True)

        preview_box = ttk.LabelFrame(main, text=" پیش‌نمایش زنده ", padding=6)
        preview_box.pack(side="left", fill="both", expand=True)

        self.canvas = tk.Canvas(preview_box, bg="#1e1e1e", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.schedule_preview())

        side_outer = ttk.Frame(main, width=390)
        side_outer.pack(side="right", fill="y", padx=(12, 0))
        side_outer.pack_propagate(False)

        cvs = tk.Canvas(side_outer, highlightthickness=0, width=370)
        sb  = ttk.Scrollbar(side_outer, orient="vertical", command=cvs.yview)
        cvs.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        cvs.pack(side="left", fill="both", expand=True)

        side = ttk.Frame(cvs)
        win_id = cvs.create_window((0, 0), window=side, anchor="nw")

        side.bind("<Configure>", lambda e: cvs.configure(scrollregion=cvs.bbox("all")))
        cvs.bind("<Configure>", lambda e: cvs.itemconfigure(win_id, width=e.width))

        def _wheel(e):
            cvs.yview_scroll(int(-e.delta / 120), "units")
        cvs.bind("<Enter>", lambda e: cvs.bind_all("<MouseWheel>", _wheel))
        cvs.bind("<Leave>", lambda e: cvs.unbind_all("<MouseWheel>"))

        s1 = ttk.LabelFrame(side, text=" ۱) فایل‌ها ", padding=10)
        s1.pack(fill="x", pady=(0, 8))

        ttk.Button(s1, text="🖼  انتخاب تصویر واترمارک",
                   command=self.choose_watermark).pack(fill="x")
        self.lbl_wm = ttk.Label(s1, text="انتخاب نشده", foreground="#c0392b",
                                anchor="e", wraplength=330)
        self.lbl_wm.pack(fill="x", pady=(3, 10))

        ttk.Button(s1, text="📁  انتخاب پوشه تصاویر",
                   command=self.choose_folder).pack(fill="x")
        self.lbl_folder = ttk.Label(s1, text="انتخاب نشده", foreground="#c0392b",
                                    anchor="e", wraplength=330)
        self.lbl_folder.pack(fill="x", pady=(3, 10))

        ttk.Label(s1, text="تصویر نمونه برای پیش‌نمایش:", anchor="e").pack(fill="x")
        self.cmb_preview = ttk.Combobox(s1, state="readonly", values=[])
        self.cmb_preview.pack(fill="x", pady=(3, 0))
        self.cmb_preview.bind("<<ComboboxSelected>>", self.on_preview_select)

        s2 = ttk.LabelFrame(side, text=" ۲) حالت و جای‌گذاری ", padding=10)
        s2.pack(fill="x", pady=(0, 8))

        r = ttk.Frame(s2); r.pack(fill="x", pady=2)
        ttk.Label(r, text="حالت چیدمان:").pack(side="right")
        self.cmb_mode = ttk.Combobox(r, textvariable=self.var_mode, state="readonly",
                                     values=[MODE_SINGLE, MODE_TILE], width=15)
        self.cmb_mode.pack(side="right", padx=8)
        self.cmb_mode.bind("<<ComboboxSelected>>", self._on_mode_change)

        r = ttk.Frame(s2); r.pack(fill="x", pady=2)
        ttk.Label(r, text="موقعیت:").pack(side="right")
        self.cmb_pos = ttk.Combobox(r, textvariable=self.var_position, state="readonly",
                                    values=list(POSITIONS.keys()), width=15)
        self.cmb_pos.pack(side="right", padx=8)
        self.cmb_pos.bind("<<ComboboxSelected>>", lambda e: self.schedule_preview())

        g2 = ttk.Frame(s2); g2.pack(fill="x", pady=(8, 0))
        g2.columnconfigure(1, weight=1)
        self.sld_spacing = self._add_slider(g2, 0, "فاصله کاشی‌ها (%)",
                                            self.var_spacing, 0, 250, suffix="٪")

        s3 = ttk.LabelFrame(side, text=" ۳) تنظیمات ظاهری ", padding=10)
        s3.pack(fill="x", pady=(0, 8))

        g3 = ttk.Frame(s3); g3.pack(fill="x")
        g3.columnconfigure(1, weight=1)
        self._add_slider(g3, 0, "اندازه واترمارک (%)", self.var_scale,    1, 100, suffix="٪")
        self._add_slider(g3, 1, "شفافیت (%)",         self.var_opacity,  0, 100, suffix="٪")
        self._add_slider(g3, 2, "چرخش (درجه)",        self.var_rotation, -180, 180, suffix="°")
        self._add_slider(g3, 3, "حاشیه (px)",         self.var_margin,   0, 400, suffix="px")

        s4 = ttk.LabelFrame(side, text=" ۴) خروجی ", padding=10)
        s4.pack(fill="x", pady=(0, 8))

        ttk.Button(s4, text="📂  انتخاب پوشه خروجی",
                   command=self.choose_output).pack(fill="x")
        self.lbl_output = ttk.Label(s4, text="پیش‌فرض: پوشه تصاویر / watermarked",
                                    foreground="#7f8c8d", anchor="e", wraplength=330)
        self.lbl_output.pack(fill="x", pady=(3, 10))

        r = ttk.Frame(s4); r.pack(fill="x", pady=2)
        ttk.Label(r, text="پسوند نام فایل:").pack(side="right")
        ttk.Entry(r, textvariable=self.var_suffix, width=15, justify="center").pack(
            side="right", padx=8)

        g4 = ttk.Frame(s4); g4.pack(fill="x", pady=(6, 0))
        g4.columnconfigure(1, weight=1)
        self._add_slider(g4, 0, "کیفیت JPEG (%)", self.var_quality, 50, 100, suffix="٪")

        s5 = ttk.LabelFrame(side, text=" ۵) اجرا ", padding=10)
        s5.pack(fill="x", pady=(0, 8))

        self.btn_run = ttk.Button(s5, text="🚀  اعمال روی همه تصاویر",
                                  style="Accent.TButton", command=self.start_process)
        self.btn_run.pack(fill="x")

        self.btn_cancel = ttk.Button(s5, text="✖  توقف", command=self.cancel_process,
                                     state="disabled")
        self.btn_cancel.pack(fill="x", pady=(6, 0))

        self.progress = ttk.Progressbar(s5, mode="determinate")
        self.progress.pack(fill="x", pady=(10, 4))

        self.lbl_status = ttk.Label(s5, text="آماده", anchor="e", foreground="#2c3e50")
        self.lbl_status.pack(fill="x")

    def _add_slider(self, parent, row, text, var, frm, to, fmt="{:.0f}", suffix=""):
        ttk.Label(parent, text=text, anchor="e").grid(
            row=row, column=0, sticky="e", padx=(0, 6), pady=3)

        val_lbl = ttk.Label(parent, text=fmt.format(var.get()) + suffix,
                            width=7, anchor="center")
        val_lbl.grid(row=row, column=2, sticky="w", padx=(6, 0), pady=3)

        def on_change(v):
            try:
                val_lbl.config(text=fmt.format(float(v)) + suffix)
            except (ValueError, tk.TclError):
                pass
            self.schedule_preview()

        sld = ttk.Scale(parent, from_=frm, to=to, variable=var,
                        orient="horizontal", command=on_change)
        sld.grid(row=row, column=1, sticky="ew", pady=3)
        return sld

    def choose_watermark(self):
        path = filedialog.askopenfilename(
            title="انتخاب تصویر واترمارک",
            filetypes=[("تصاویر", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff"),
                       ("همه فایل‌ها", "*.*")])
        if not path:
            return
        try:
            img = Image.open(path)
            img = ImageOps.exif_transpose(img).convert("RGBA")
        except Exception as e:
            messagebox.showerror("خطا", f"خواندن تصویر ممکن نشد:\n{e}")
            return

        self.wm_path = path
        self.wm_src  = img
        self.lbl_wm.config(text=os.path.basename(path), foreground="#27ae60")
        self.schedule_preview()

    def choose_folder(self):
        path = filedialog.askdirectory(title="انتخاب پوشه تصاویر")
        if not path:
            return
        self.folder_path = path
        files = self.list_images()
        self.lbl_folder.config(
            text=f"{path}   ({len(files)} تصویر)",
            foreground="#27ae60" if files else "#c0392b")

        names = [os.path.basename(f) for f in files]
        self.cmb_preview["values"] = names
        if names:
            self.cmb_preview.current(0)
            self.preview_source_path = files[0]
            self.load_preview_source()
        self.schedule_preview()

    def choose_output(self):
        path = filedialog.askdirectory(title="انتخاب پوشه خروجی")
        if path:
            self.var_output.set(path)
            self.lbl_output.config(text=path, foreground="#27ae60")

    def on_preview_select(self, _event=None):
        idx = self.cmb_preview.current()
        if idx < 0 or not self.folder_path:
            return
        files = self.list_images()
        if idx < len(files):
            self.preview_source_path = files[idx]
            self.load_preview_source()
            self.schedule_preview()

    def list_images(self):
        if not self.folder_path or not os.path.isdir(self.folder_path):
            return []
        out = []
        for name in sorted(os.listdir(self.folder_path)):
            if name.lower().endswith(SUPPORTED_EXT):
                out.append(os.path.join(self.folder_path, name))
        return out

    def load_preview_source(self):
        try:
            img = Image.open(self.preview_source_path)
            img = ImageOps.exif_transpose(img)
            self.preview_source = img.convert("RGBA")
        except Exception:
            self.preview_source = None

    def schedule_preview(self, *_):
        if self._preview_job:
            self.root.after_cancel(self._preview_job)
        self._preview_job = self.root.after(120, self.update_preview)

    def update_preview(self):
        self._preview_job = None
        self.canvas.delete("all")

        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 20 or ch < 20:
            return

        if self.preview_source is None:
            self.canvas.create_text(
                cw // 2, ch // 2,
                text="برای شروع، تصویر واترمارک و پوشه تصاویر را انتخاب کنید",
                fill="#888888", font=FONT, justify="center")
            return

        base = self.preview_source.copy()
        base.thumbnail((1400, 1400), Image.LANCZOS)

        st = self.snapshot()
        if self.wm_src is not None:
            try:
                wm = self.prepare_watermark(self.wm_src, base.size, st)
                result = self.apply_watermark(base, wm, st)
            except Exception:
                result = base
        else:
            result = base

        result = result.convert("RGB")
        result.thumbnail((max(20, cw - 12), max(20, ch - 12)), Image.LANCZOS)

        self._tk_img = ImageTk.PhotoImage(result)
        self.canvas.create_image(cw // 2, ch // 2, image=self._tk_img)
        self.canvas.create_text(
            10, 10, anchor="nw",
            text=f"{result.width}×{result.height}", fill="#666666", font=("Tahoma", 8))

    def snapshot(self) -> dict:
        return {
            "mode":     self.var_mode.get(),
            "position": self.var_position.get(),
            "scale":    float(self.var_scale.get()),
            "opacity":  float(self.var_opacity.get()),
            "rotation": float(self.var_rotation.get()),
            "margin":   int(self.var_margin.get()),
            "spacing":  float(self.var_spacing.get()),
            "quality":  int(self.var_quality.get()),
        }

    def _on_mode_change(self, _event=None):
        is_tile = self.var_mode.get() == MODE_TILE
        self.cmb_pos.config(state="disabled" if is_tile else "readonly")
        self.sld_spacing.config(state="normal" if is_tile else "disabled")
        self.schedule_preview()

    @staticmethod
    def prepare_watermark(wm_src: Image.Image, base_size, st: dict) -> Image.Image:
        bw, _bh = base_size

        target_w = max(1, int(bw * st["scale"] / 100.0))
        ratio    = target_w / wm_src.width
        target_h = max(1, int(wm_src.height * ratio))

        wm = wm_src.resize((target_w, target_h), Image.LANCZOS)

        if abs(st["rotation"]) > 0.01:
            wm = wm.rotate(st["rotation"], expand=True, resample=Image.BICUBIC)

        op = st["opacity"] / 100.0
        if op < 0.999:
            alpha = wm.getchannel("A").point(lambda p: int(p * op))
            wm.putalpha(alpha)

        return wm

    @staticmethod
    def apply_watermark(base_rgba: Image.Image, wm: Image.Image, st: dict) -> Image.Image:
        bw, bh = base_rgba.size
        ww, wh = wm.size
        overlay = Image.new("RGBA", base_rgba.size, (0, 0, 0, 0))

        if st["mode"] == MODE_TILE:
            gap = int(ww * st["spacing"] / 100.0)
            step_x = max(1, ww + gap)
            step_y = max(1, wh + gap)

            cols = max(1, (bw - ww) // step_x + 1) if bw > ww else 1
            rows = max(1, (bh - wh) // step_y + 1) if bh > wh else 1

            total_w = ww + (cols - 1) * step_x
            total_h = wh + (rows - 1) * step_y
            sx = max(0, (bw - total_w) // 2)
            sy = max(0, (bh - total_h) // 2)

            for r in range(rows):
                for c in range(cols):
                    x = sx + c * step_x
                    y = sy + r * step_y
                    if x < bw and y < bh:
                        overlay.alpha_composite(wm, (x, y))
        else:
            hx, vy = POSITIONS.get(st["position"], ("right", "bottom"))
            m = st["margin"]

            if hx == "left":
                x = m
            elif hx == "center":
                x = (bw - ww) // 2
            else:
                x = bw - ww - m

            if vy == "top":
                y = m
            elif vy == "center":
                y = (bh - wh) // 2
            else:
                y = bh - wh - m

            x = max(0, x)
            y = max(0, y)
            overlay.alpha_composite(wm, (x, y))

        return Image.alpha_composite(base_rgba, overlay)

    def start_process(self):
        if self._busy:
            return
        if self.wm_src is None:
            messagebox.showwarning("ناقص", "اول تصویر واترمارک را انتخاب کن.")
            return
        if not self.folder_path:
            messagebox.showwarning("ناقص", "پوشه تصاویر را انتخاب کن.")
            return

        files = self.list_images()
        if not files:
            messagebox.showwarning("خالی", "در این پوشه تصویری پیدا نشد.")
            return

        out_dir = self.var_output.get().strip() or os.path.join(self.folder_path, "watermarked")
        os.makedirs(out_dir, exist_ok=True)

        st = self.snapshot()
        suffix = self.var_suffix.get()

        self._busy = True
        self._cancel = False
        self.btn_run.config(state="disabled")
        self.btn_cancel.config(state="normal")
        self.progress.config(maximum=len(files), value=0)
        self.lbl_status.config(text="در حال پردازش…")

        t = threading.Thread(target=self._worker,
                             args=(files, out_dir, st, suffix, self.wm_src.copy()),
                             daemon=True)
        t.start()

    def cancel_process(self):
        self._cancel = True
        self.lbl_status.config(text="در حال توقف…")

    def _worker(self, files, out_dir, st, suffix, wm_src):
        total  = len(files)
        errors = []
        done   = 0

        for i, src in enumerate(files, 1):
            if self._cancel:
                break
            name = os.path.basename(src)
            try:
                img = Image.open(src)
                img = ImageOps.exif_transpose(img)
                fmt = (img.format or "").upper()
                base = img.convert("RGBA")

                wm = self.prepare_watermark(wm_src, base.size, st)
                res = self.apply_watermark(base, wm, st)

                stem, ext = os.path.splitext(name)
                ext_l = ext.lower()
                out_path = os.path.join(out_dir, f"{stem}{suffix}{ext}")

                if ext_l in (".jpg", ".jpeg"):
                    res.convert("RGB").save(out_path, "JPEG",
                                            quality=st["quality"], optimize=True,
                                            progressive=True)
                elif ext_l == ".png":
                    res.save(out_path, "PNG", optimize=True)
                elif ext_l == ".webp":
                    res.save(out_path, "WEBP", quality=st["quality"], method=5)
                elif ext_l in (".tif", ".tiff"):
                    res.save(out_path, "TIFF")
                elif ext_l == ".bmp":
                    res.convert("RGB").save(out_path, "BMP")
                else:
                    res.convert("RGB").save(out_path,
                                            format=fmt or "PNG",
                                            quality=st["quality"])

                done += 1
            except Exception as e:
                errors.append(f"{name}: {e}")

            self.root.after(0, self._set_progress, i, total, name)

        self.root.after(0, self._finish, done, total, errors, out_dir)

    def _set_progress(self, i, total, name):
        self.progress.config(value=i)
        short = name if len(name) <= 32 else name[:29] + "…"
        self.lbl_status.config(text=f"{i} از {total}  —  {short}")

    def _finish(self, done, total, errors, out_dir):
        self._busy = False
        self.btn_run.config(state="normal")
        self.btn_cancel.config(state="disabled")

        if self._cancel:
            self.lbl_status.config(text=f"متوقف شد ({done} تصویر ذخیره شد)")
        else:
            self.lbl_status.config(text=f"تمام شد — {done} از {total} تصویر")

        msg = f"✅ {done} تصویر از {total} با موفقیت واترمارک شد.\n\n📂 {out_dir}"
        if errors:
            msg += f"\n\n⚠ {len(errors)} خطا:\n" + "\n".join(errors[:8])
            if len(errors) > 8:
                msg += f"\n… و {len(errors) - 8} خطای دیگر"
        messagebox.showinfo("نتیجه", msg)

        if os.name == "nt":
            try:
                os.startfile(out_dir)
            except Exception:
                pass

if __name__ == "__main__":
    root = tk.Tk()
    app = WatermarkApp(root)
    root.mainloop()