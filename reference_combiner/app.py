from __future__ import annotations

import io
import json
import os
import platform
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk
from typing import Any

from PIL import Image, ImageGrab, ImageTk, UnidentifiedImageError

from .composer import ComposeSettings, compose_image

try:
    import windnd
except Exception:  # pragma: no cover
    windnd = None

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
SETTINGS_PATH = Path.home() / ".reference_combiner_settings.json"


class ReferenceCombinerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Reference Combiner")
        self.root.geometry("1300x760")
        self.root.minsize(1000, 650)

        self.image_paths: list[str] = []
        self.images: list[Image.Image] = []
        self.combined_image: Image.Image | None = None
        self.preview_photo: ImageTk.PhotoImage | None = None
        self.thumbnail_cache: dict[str, ImageTk.PhotoImage] = {}
        self._drag_item: str | None = None

        self.layout_var = tk.StringVar(value="auto")
        self.fit_var = tk.StringVar(value="fit")
        self.bg_var = tk.StringVar(value="#2f2f2f")
        self.gap_var = tk.IntVar(value=8)
        self.margin_var = tk.IntVar(value=8)
        self.width_mode_var = tk.StringVar(value="auto")
        self.custom_width_var = tk.IntVar(value=2560)
        self.custom_cols_var = tk.IntVar(value=3)
        self.jpg_quality_var = tk.IntVar(value=95)
        self.open_after_export_var = tk.BooleanVar(value=True)

        self._load_settings()
        self._build_ui()
        self._bind_events()
        self._setup_external_drop()
        self.render_preview()

    def _build_ui(self) -> None:
        root = self.root
        root.columnconfigure(0, weight=0)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        left = ttk.Frame(root, padding=10)
        left.grid(row=0, column=0, sticky="ns")

        right = ttk.Frame(root, padding=(0, 10, 10, 10))
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        ttk.Label(left, text="Images", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        btn_row = ttk.Frame(left)
        btn_row.grid(row=1, column=0, sticky="ew", pady=(6, 8))
        ttk.Button(btn_row, text="Add Images", command=self.add_images).grid(row=0, column=0, padx=(0, 4))
        ttk.Button(btn_row, text="Clear", command=self.clear_images).grid(row=0, column=1, padx=4)
        ttk.Button(btn_row, text="Paste", command=self.paste_from_clipboard).grid(row=0, column=2, padx=(4, 0))

        self.tree = ttk.Treeview(left, show="tree", selectmode="browse", height=16)
        self.tree.grid(row=2, column=0, sticky="nsew")
        left.rowconfigure(2, weight=1)

        order_row = ttk.Frame(left)
        order_row.grid(row=3, column=0, sticky="ew", pady=(6, 10))
        ttk.Button(order_row, text="Move Left", command=lambda: self.move_selected(-1)).grid(row=0, column=0, padx=(0, 4))
        ttk.Button(order_row, text="Move Right", command=lambda: self.move_selected(1)).grid(row=0, column=1, padx=(0, 4))
        ttk.Button(order_row, text="Delete", command=self.delete_selected).grid(row=0, column=2)

        ttk.Label(left, text="Layout", font=("Segoe UI", 10, "bold")).grid(row=4, column=0, sticky="w")
        layout_box = ttk.Frame(left)
        layout_box.grid(row=5, column=0, sticky="ew", pady=(6, 8))
        ttk.Label(layout_box, text="Preset:").grid(row=0, column=0, sticky="w")
        layout_combo = ttk.Combobox(
            layout_box,
            textvariable=self.layout_var,
            state="readonly",
            width=16,
            values=["auto", "horizontal", "vertical", "2x2", "3x1", "1x3", "custom"],
        )
        layout_combo.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        ttk.Label(layout_box, text="Custom columns:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Spinbox(layout_box, from_=1, to=12, textvariable=self.custom_cols_var, width=7).grid(row=1, column=1, sticky="w", padx=(6, 0), pady=(6, 0))

        fit_box = ttk.Frame(left)
        fit_box.grid(row=6, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(fit_box, text="Image fit:").grid(row=0, column=0, sticky="w")
        ttk.Combobox(fit_box, textvariable=self.fit_var, state="readonly", values=["fit", "fill", "original"], width=10).grid(row=0, column=1, padx=(6, 0))

        canvas_box = ttk.LabelFrame(left, text="Canvas")
        canvas_box.grid(row=7, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(canvas_box, text="Background", command=self.pick_background).grid(row=0, column=0, sticky="w", padx=6, pady=6)
        ttk.Label(canvas_box, textvariable=self.bg_var).grid(row=0, column=1, sticky="w")
        ttk.Label(canvas_box, text="Gap:").grid(row=1, column=0, sticky="w", padx=6)
        ttk.Spinbox(canvas_box, from_=0, to=100, textvariable=self.gap_var, width=8).grid(row=1, column=1, sticky="w")
        ttk.Label(canvas_box, text="Margin:").grid(row=2, column=0, sticky="w", padx=6, pady=(0, 6))
        ttk.Spinbox(canvas_box, from_=0, to=200, textvariable=self.margin_var, width=8).grid(row=2, column=1, sticky="w", pady=(0, 6))

        width_box = ttk.LabelFrame(left, text="Output size")
        width_box.grid(row=8, column=0, sticky="ew", pady=(0, 8))
        ttk.Combobox(
            width_box,
            textvariable=self.width_mode_var,
            state="readonly",
            values=["auto", "1920", "2560", "3840", "custom"],
            width=12,
        ).grid(row=0, column=0, padx=6, pady=6, sticky="w")
        ttk.Label(width_box, text="Custom width:").grid(row=1, column=0, padx=6, sticky="w")
        ttk.Spinbox(width_box, from_=256, to=20000, textvariable=self.custom_width_var, width=10).grid(row=1, column=1, sticky="w")

        export_box = ttk.LabelFrame(left, text="Export")
        export_box.grid(row=9, column=0, sticky="ew")
        ttk.Button(export_box, text="Export PNG", command=lambda: self.export_image("PNG")).grid(row=0, column=0, padx=6, pady=6)
        ttk.Button(export_box, text="Export JPG", command=lambda: self.export_image("JPEG")).grid(row=0, column=1, padx=6, pady=6)
        ttk.Label(export_box, text="JPG quality:").grid(row=1, column=0, padx=6, sticky="w")
        ttk.Spinbox(export_box, from_=50, to=100, textvariable=self.jpg_quality_var, width=8).grid(row=1, column=1, sticky="w")
        ttk.Checkbutton(export_box, text="Open after export", variable=self.open_after_export_var).grid(row=2, column=0, columnspan=2, padx=6, pady=(2, 6), sticky="w")
        ttk.Button(export_box, text="Copy to Clipboard", command=self.copy_to_clipboard).grid(row=3, column=0, columnspan=2, padx=6, pady=(0, 6), sticky="ew")

        ttk.Label(right, text="Live Preview", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.preview = ttk.Label(right, anchor="center", relief="sunken")
        self.preview.grid(row=1, column=0, sticky="nsew")

    def _bind_events(self) -> None:
        self.tree.bind("<Double-1>", lambda _e: self.replace_selected())
        self.tree.bind("<ButtonPress-1>", self._tree_drag_start)
        self.tree.bind("<ButtonRelease-1>", self._tree_drag_drop)
        self.root.bind("<Delete>", lambda _e: self.delete_selected())
        self.root.bind("<Control-v>", lambda _e: self.paste_from_clipboard())
        self.preview.bind("<Configure>", lambda _e: self.render_preview())

        watched_vars: list[tk.Variable] = [
            self.layout_var,
            self.fit_var,
            self.bg_var,
            self.gap_var,
            self.margin_var,
            self.width_mode_var,
            self.custom_width_var,
            self.custom_cols_var,
            self.jpg_quality_var,
            self.open_after_export_var,
        ]
        for var in watched_vars:
            var.trace_add("write", lambda *_args: self.render_preview())
            var.trace_add("write", lambda *_args: self._save_settings())

    def _setup_external_drop(self) -> None:
        if windnd is None:
            return

        def on_drop(files: Any) -> None:
            paths = [Path(f.decode("utf-8")).as_posix() for f in files]
            self._add_images(paths)

        windnd.hook_dropfiles(self.root, func=on_drop)

    def _load_settings(self) -> None:
        if not SETTINGS_PATH.exists():
            return
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return
        self.layout_var.set(data.get("layout", self.layout_var.get()))
        self.fit_var.set(data.get("fit", self.fit_var.get()))
        self.bg_var.set(data.get("background", self.bg_var.get()))
        self.gap_var.set(int(data.get("gap", self.gap_var.get())))
        self.margin_var.set(int(data.get("margin", self.margin_var.get())))
        self.width_mode_var.set(data.get("width_mode", self.width_mode_var.get()))
        self.custom_width_var.set(int(data.get("custom_width", self.custom_width_var.get())))
        self.custom_cols_var.set(int(data.get("custom_columns", self.custom_cols_var.get())))
        self.jpg_quality_var.set(int(data.get("jpg_quality", self.jpg_quality_var.get())))
        self.open_after_export_var.set(bool(data.get("open_after_export", self.open_after_export_var.get())))

    def _save_settings(self) -> None:
        data = {
            "layout": self.layout_var.get(),
            "fit": self.fit_var.get(),
            "background": self.bg_var.get(),
            "gap": self.gap_var.get(),
            "margin": self.margin_var.get(),
            "width_mode": self.width_mode_var.get(),
            "custom_width": self.custom_width_var.get(),
            "custom_columns": self.custom_cols_var.get(),
            "jpg_quality": self.jpg_quality_var.get(),
            "open_after_export": self.open_after_export_var.get(),
        }
        try:
            SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _default_layout_for_count(self, count: int) -> str:
        if count <= 1:
            return "horizontal"
        if count == 2:
            return "horizontal"
        if count == 3:
            return "3x1"
        if count == 4:
            return "2x2"
        return "auto"

    def add_images(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Add reference images",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp")],
        )
        self._add_images(paths)

    def _add_images(self, paths: Any) -> None:
        added = 0
        for raw in paths:
            path = str(raw)
            ext = Path(path).suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            try:
                with Image.open(path) as im:
                    self.images.append(im.convert("RGBA"))
                self.image_paths.append(path)
                added += 1
            except (FileNotFoundError, UnidentifiedImageError, OSError):
                continue
        if added and len(self.images) == added:
            self.layout_var.set(self._default_layout_for_count(len(self.images)))
        self._refresh_thumbnail_list()
        self.render_preview()

    def clear_images(self) -> None:
        self.images.clear()
        self.image_paths.clear()
        self.thumbnail_cache.clear()
        self._refresh_thumbnail_list()
        self.render_preview()

    def _refresh_thumbnail_list(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for idx, path in enumerate(self.image_paths):
            thumb = self.thumbnail_cache.get(path)
            if thumb is None:
                try:
                    with Image.open(path) as im:
                        preview = im.convert("RGBA")
                    preview.thumbnail((64, 64), Image.Resampling.LANCZOS)
                    thumb = ImageTk.PhotoImage(preview)
                    self.thumbnail_cache[path] = thumb
                except Exception:
                    thumb = None
            name = f"{idx + 1}. {Path(path).name}"
            self.tree.insert("", "end", iid=str(idx), text=name, image=thumb)

    def _selected_index(self) -> int | None:
        selected = self.tree.selection()
        if not selected:
            return None
        try:
            return int(selected[0])
        except ValueError:
            return None

    def move_selected(self, offset: int) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        new_idx = idx + offset
        if new_idx < 0 or new_idx >= len(self.images):
            return
        self.images[idx], self.images[new_idx] = self.images[new_idx], self.images[idx]
        self.image_paths[idx], self.image_paths[new_idx] = self.image_paths[new_idx], self.image_paths[idx]
        self._refresh_thumbnail_list()
        self.tree.selection_set(str(new_idx))
        self.render_preview()

    def delete_selected(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        del self.images[idx]
        del self.image_paths[idx]
        self._refresh_thumbnail_list()
        self.render_preview()

    def replace_selected(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp")])
        if not path:
            return
        try:
            with Image.open(path) as im:
                self.images[idx] = im.convert("RGBA")
            self.image_paths[idx] = path
            self.thumbnail_cache.pop(path, None)
            self._refresh_thumbnail_list()
            self.tree.selection_set(str(idx))
            self.render_preview()
        except (FileNotFoundError, UnidentifiedImageError, OSError):
            messagebox.showerror("Reference Combiner", "Could not open selected image.")

    def _tree_drag_start(self, event: tk.Event) -> None:
        item = self.tree.identify_row(event.y)
        if item:
            self._drag_item = item

    def _tree_drag_drop(self, event: tk.Event) -> None:
        if self._drag_item is None:
            return
        target = self.tree.identify_row(event.y)
        if not target or target == self._drag_item:
            self._drag_item = None
            return
        from_idx = int(self._drag_item)
        to_idx = int(target)
        image = self.images.pop(from_idx)
        path = self.image_paths.pop(from_idx)
        self.images.insert(to_idx, image)
        self.image_paths.insert(to_idx, path)
        self._drag_item = None
        self._refresh_thumbnail_list()
        self.tree.selection_set(str(to_idx))
        self.render_preview()

    def paste_from_clipboard(self) -> None:
        grabbed = ImageGrab.grabclipboard()
        if isinstance(grabbed, Image.Image):
            self.images.append(grabbed.convert("RGBA"))
            self.image_paths.append("clipboard_image.png")
            self._refresh_thumbnail_list()
            self.render_preview()
            return
        if isinstance(grabbed, list):
            self._add_images(grabbed)

    def pick_background(self) -> None:
        color = colorchooser.askcolor(color=self.bg_var.get())[1]
        if color:
            self.bg_var.set(color)

    def current_settings(self) -> ComposeSettings:
        return ComposeSettings(
            layout=self.layout_var.get(),
            fit_mode=self.fit_var.get(),
            background=self.bg_var.get(),
            gap=max(0, int(self.gap_var.get())),
            margin=max(0, int(self.margin_var.get())),
            output_width_mode=self.width_mode_var.get(),
            custom_width=max(1, int(self.custom_width_var.get())),
            custom_columns=max(1, int(self.custom_cols_var.get())),
        )

    def render_preview(self) -> None:
        settings = self.current_settings()
        self.combined_image = compose_image(self.images, settings)

        preview_img = self.combined_image.copy()
        width = max(200, self.preview.winfo_width() - 6)
        height = max(200, self.preview.winfo_height() - 6)
        preview_img.thumbnail((width, height), Image.Resampling.LANCZOS)
        self.preview_photo = ImageTk.PhotoImage(preview_img)
        self.preview.configure(image=self.preview_photo)

    def export_image(self, fmt: str) -> None:
        if self.combined_image is None:
            self.render_preview()
        if self.combined_image is None:
            return
        if fmt == "PNG":
            default_name = "reference_combined.png"
            ext = ".png"
            filetypes = [("PNG", "*.png")]
        else:
            default_name = "reference_combined.jpg"
            ext = ".jpg"
            filetypes = [("JPEG", "*.jpg *.jpeg")]

        path = filedialog.asksaveasfilename(
            title=f"Export {fmt}",
            defaultextension=ext,
            initialfile=default_name,
            filetypes=filetypes,
        )
        if not path:
            return

        output = self.combined_image
        if fmt == "JPEG":
            output = self.combined_image.convert("RGB")
            output.save(path, format="JPEG", quality=max(50, min(100, self.jpg_quality_var.get())), optimize=True)
        else:
            output.save(path, format="PNG", optimize=True)

        if self.open_after_export_var.get():
            self._open_file(path)
        messagebox.showinfo("Reference Combiner", f"Exported to\n{path}")

    def _open_file(self, path: str) -> None:
        try:
            if platform.system() == "Windows":
                os.startfile(path)  # type: ignore[attr-defined]
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            pass

    def copy_to_clipboard(self) -> None:
        if self.combined_image is None:
            self.render_preview()
        if self.combined_image is None:
            return

        if platform.system() != "Windows":
            messagebox.showwarning("Reference Combiner", "Copy to clipboard currently supports Windows only.")
            return

        try:
            from ctypes import c_size_t, c_void_p, windll

            output = self.combined_image.convert("RGB")
            with io.BytesIO() as buffer:
                output.save(buffer, "BMP")
                data = buffer.getvalue()[14:]  # strip BMP header for CF_DIB

            CF_DIB = 8
            GHND = 0x0042
            hglobal = windll.kernel32.GlobalAlloc(GHND, c_size_t(len(data)))
            ptr = windll.kernel32.GlobalLock(c_void_p(hglobal))
            windll.msvcrt.memcpy(c_void_p(ptr), data, len(data))
            windll.kernel32.GlobalUnlock(c_void_p(hglobal))

            windll.user32.OpenClipboard(0)
            windll.user32.EmptyClipboard()
            windll.user32.SetClipboardData(CF_DIB, hglobal)
            windll.user32.CloseClipboard()
            messagebox.showinfo("Reference Combiner", "Combined image copied to clipboard.")
        except Exception:
            messagebox.showerror("Reference Combiner", "Failed to copy image to clipboard.")


def run() -> None:
    root = tk.Tk()
    app = ReferenceCombinerApp(root)
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()


if __name__ == "__main__":
    run()
