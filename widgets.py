"""
Custom widgets and theme helpers for Octopuzzle.
"""

import tkinter as tk
from tkinter import ttk
from PIL import ImageTk
import cv2
from typing import Optional, Tuple, Callable

from image_utils import cv2_to_photoimage, draw_roi_overlay


PALETTE = {
    "background": "#0f172a",
    "surface": "#111c34",
    "panel": "#16243d",
    "card": "#1b2d4b",
    "canvas": "#0b1220",
    "border": "#1f2937",
    "text": "#e2e8f0",
    "muted": "#94a3b8",
    "accent": "#6366f1",
    "accent_hover": "#4f46e5",
    "accent_active": "#4338ca",
    "success": "#22c55e",
    "warning": "#f97316",
    "danger": "#ef4444",
    "danger_hover": "#dc2626",
    "danger_active": "#b91c1c",
    "neutral": "#1f2a3d",
    "neutral_hover": "#23314a",
    "neutral_active": "#1b2435",
    "disabled_bg": "#1b2333",
    "disabled_fg": "#6b7280",
}

BUTTON_STYLES = {
    "accent": "OctoAccent.TButton",
    "secondary": "OctoSecondary.TButton",
    "ghost": "OctoGhost.TButton",
    "danger": "OctoDanger.TButton",
}

PROGRESS_STYLE = "Octo.Horizontal.TProgressbar"
CHECKBUTTON_STYLE = "Octo.TCheckbutton"


def init_theme(root: tk.Misc) -> None:
    """Configure a modern visual theme for Octopuzzle."""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        # If clam is unavailable we still continue with default theme.
        pass

    root.configure(bg=PALETTE["background"])
    root.option_add("*Font", "Segoe UI 11")
    root.option_add("*TLabel.Font", "Segoe UI 11")
    root.option_add("*TButton.Font", "Segoe UI 11")
    root.option_add("*TCombobox*Listbox.Font", "Segoe UI 11")
    root.option_add("*Entry.Font", "Segoe UI 11")
    root.option_add("*Foreground", PALETTE["text"])
    root.option_add("*Background", PALETTE["background"])
    root.option_add("*Label.Foreground", PALETTE["text"])

    # Frames & labels
    style.configure("TFrame", background=PALETTE["background"])
    style.configure("Octo.Surface.TFrame", background=PALETTE["surface"])
    style.configure("Octo.Panel.TFrame", background=PALETTE["panel"])
    style.configure("TLabel", background=PALETTE["background"], foreground=PALETTE["text"])
    style.configure(
        "OctoTitle.TLabel",
        background=PALETTE["background"],
        foreground=PALETTE["text"],
        font=("Segoe UI Semibold", 18),
    )
    style.configure(
        "OctoSection.TLabel",
        background=PALETTE["panel"],
        foreground=PALETTE["text"],
        font=("Segoe UI Semibold", 13),
    )
    style.configure(
        "OctoMuted.TLabel",
        background=PALETTE["panel"],
        foreground=PALETTE["muted"],
        font=("Segoe UI", 10),
    )

    # Buttons
    style.configure("OctoAccent.TButton",
                    background=PALETTE["accent"],
                    foreground=PALETTE["text"],
                    padding=(18, 10),
                    borderwidth=0)
    style.map(
        "OctoAccent.TButton",
        background=[
            ("active", PALETTE["accent_hover"]),
            ("pressed", PALETTE["accent_active"])
        ],
        foreground=[("disabled", PALETTE["disabled_fg"])],
        relief=[("pressed", "sunken")],
    )

    style.configure(
        "OctoSecondary.TButton",
        background=PALETTE["neutral"],
        foreground=PALETTE["text"],
        padding=(16, 9),
        borderwidth=0,
    )
    style.map(
        "OctoSecondary.TButton",
        background=[
            ("active", PALETTE["neutral_hover"]),
            ("pressed", PALETTE["neutral_active"]),
            ("disabled", PALETTE["disabled_bg"]),
        ],
        foreground=[("disabled", PALETTE["disabled_fg"])],
    )

    style.configure(
        "OctoGhost.TButton",
        background=PALETTE["surface"],
        foreground=PALETTE["text"],
        padding=(14, 8),
        borderwidth=1
    )
    style.map(
        "OctoGhost.TButton",
        background=[("active", PALETTE["neutral_hover"]), ("pressed", PALETTE["neutral_active"])],
        foreground=[("disabled", PALETTE["disabled_fg"])],
    )

    style.configure(
        "OctoDanger.TButton",
        background=PALETTE["danger"],
        foreground=PALETTE["text"],
        padding=(18, 10),
        borderwidth=0,
    )
    style.map(
        "OctoDanger.TButton",
        background=[
            ("active", PALETTE["danger_hover"]),
            ("pressed", PALETTE["danger_active"]),
            ("disabled", PALETTE["disabled_bg"]),
        ],
        foreground=[("disabled", PALETTE["disabled_fg"])],
    )

    # Combobox & spinbox
    style.configure(
        "TCombobox",
        fieldbackground=PALETTE["panel"],
        background=PALETTE["panel"],
        foreground=PALETTE["text"],
        relief="flat",
    )
    style.map(
        "TCombobox",
        fieldbackground=[
            ("readonly", PALETTE["panel"]),
        ],
        foreground=[("disabled", PALETTE["disabled_fg"])],
        background=[("active", PALETTE["surface"]), ("hover", PALETTE["surface"])],
    )

    style.configure(
        "TSpinbox",
        fieldbackground=PALETTE["panel"],
        background=PALETTE["panel"],
        foreground=PALETTE["text"],
        relief="flat",
    )
    style.map(
        "TSpinbox",
        fieldbackground=[("disabled", PALETTE["disabled_bg"])],
        foreground=[("disabled", PALETTE["disabled_fg"])],
        arrowcolor=[("disabled", PALETTE["disabled_fg"])],
    )

    style.configure(
        CHECKBUTTON_STYLE,
        background=PALETTE["panel"],
        foreground=PALETTE["text"],
        padding=6,
    )
    style.map(
        CHECKBUTTON_STYLE,
        foreground=[("disabled", PALETTE["disabled_fg"])],
        background=[("active", PALETTE["surface"])],
    )

    style.configure(
        PROGRESS_STYLE,
        troughcolor=PALETTE["border"],
        background=PALETTE["accent"],
    )

    style.configure("Vertical.TScrollbar", troughcolor=PALETTE["surface"])


class CalibrationCanvas(tk.Canvas):
    """
    Canvas with interactive calibration features:
    - Drag to select ROI
    - Drag to select background sample
    - Real-time visual feedback
    """

    def __init__(self, parent, width=800, height=600, **kwargs):
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=PALETTE["canvas"],
            highlightthickness=1,
            highlightbackground=PALETTE["border"],
            bd=0,
            **kwargs,
        )

        self.image = None  # Current cv2 image
        self.photo: Optional[ImageTk.PhotoImage] = None
        self.image_id = None  # Canvas image ID

        self.mode = "none"  # 'roi', 'background', or 'none'
        self.roi: Optional[Tuple[int, int, int, int]] = None
        self.background_sample: Optional[Tuple[int, int, int]] = None

        self.drag_start: Optional[Tuple[int, int]] = None
        self.drag_rect_id = None

        # Callbacks
        self.on_roi_selected: Optional[Callable[[Tuple[int, int, int, int]], None]] = None
        self.on_background_selected: Optional[Callable[[Tuple[int, int, int]], None]] = None

        # Bind mouse events
        self.bind("<ButtonPress-1>", self._on_mouse_down)
        self.bind("<B1-Motion>", self._on_mouse_drag)
        self.bind("<ButtonRelease-1>", self._on_mouse_up)

    def set_mode(self, mode: str):
        """Set interaction mode: 'roi', 'background', or 'none'."""
        self.mode = mode
        if mode == "none":
            self.drag_start = None

    def load_image(self, cv_img):
        """Load and display image."""
        if cv_img is None:
            return

        self.image = cv_img
        self._display_image(cv_img)

    def show_debug_image(self, debug_img):
        """Display debug image with contours."""
        self._display_image(debug_img)

    def draw_roi_overlay(self):
        """Draw ROI overlay on current image."""
        if self.image is None or self.roi is None:
            return

        img_with_overlay = draw_roi_overlay(self.image, self.roi)
        self._display_image(img_with_overlay)

    def clear(self):
        """Clear canvas."""
        self.delete("all")
        self.image = None
        self.photo = None
        self.image_id = None

    def _display_image(self, cv_img):
        """Display OpenCV image on canvas."""
        if cv_img is None:
            return

        canvas_width = self.winfo_width()
        canvas_height = self.winfo_height()

        if canvas_width <= 1:
            canvas_width = int(self["width"])
        if canvas_height <= 1:
            canvas_height = int(self["height"])

        photo, _, _ = cv2_to_photoimage(cv_img, canvas_width, canvas_height)

        if photo:
            self.photo = photo
            self.delete("all")
            self.image_id = self.create_image(
                canvas_width // 2, canvas_height // 2, image=photo, anchor=tk.CENTER
            )

    def _on_mouse_down(self, event):
        """Handle mouse button press."""
        if self.mode == "none":
            return

        self.drag_start = (event.x, event.y)

    def _on_mouse_drag(self, event):
        """Handle mouse drag - show selection rectangle."""
        if self.drag_start is None or self.mode == "none":
            return

        if self.drag_rect_id:
            self.delete(self.drag_rect_id)

        x1, y1 = self.drag_start
        x2, y2 = event.x, event.y

        color = PALETTE["accent"] if self.mode == "roi" else PALETTE["warning"]
        self.drag_rect_id = self.create_rectangle(
            x1,
            y1,
            x2,
            y2,
            outline=color,
            width=2,
            dash=(5, 5),
        )

    def _on_mouse_up(self, event):
        """Handle mouse button release - finalize selection."""
        if self.drag_start is None or self.mode == "none":
            return

        if self.drag_rect_id:
            self.delete(self.drag_rect_id)
            self.drag_rect_id = None

        x1, y1 = self.drag_start
        x2, y2 = event.x, event.y

        x = min(x1, x2)
        y = min(y1, y2)
        w = abs(x2 - x1)
        h = abs(y2 - y1)

        if w < 10 or h < 10:
            self.drag_start = None
            return

        if self.image is not None and self.photo is not None:
            img_h, img_w = self.image.shape[:2]
            canvas_w = self.winfo_width()
            canvas_h = self.winfo_height()

            photo_w = self.photo.width()
            photo_h = self.photo.height()
            offset_x = (canvas_w - photo_w) // 2
            offset_y = (canvas_h - photo_h) // 2

            x -= offset_x
            y -= offset_y

            scale_x = img_w / photo_w
            scale_y = img_h / photo_h

            x = int(x * scale_x)
            y = int(y * scale_y)
            w = int(w * scale_x)
            h = int(h * scale_y)

            x = max(0, min(x, img_w - 1))
            y = max(0, min(y, img_h - 1))
            w = min(w, img_w - x)
            h = min(h, img_h - y)

        if self.mode == "roi":
            self.roi = (x, y, w, h)
            self.draw_roi_overlay()
            if self.on_roi_selected:
                self.on_roi_selected(self.roi)

        elif self.mode == "background" and self.image is not None:
            roi_img = self.image[y : y + h, x : x + w]
            avg_color = cv2.mean(roi_img)[:3]
            self.background_sample = tuple(int(c) for c in avg_color)
            if self.on_background_selected:
                self.on_background_selected(self.background_sample)

        self.drag_start = None


class ImagePanel(tk.Frame):
    """Panel to display a piece image with info."""

    def __init__(self, parent, title: str = "", **kwargs):
        super().__init__(parent, bg=PALETTE["panel"], **kwargs)
        self.configure(highlightbackground=PALETTE["border"], highlightthickness=1)

        self.title_label = tk.Label(
            self,
            text=title,
            font=("Segoe UI Semibold", 12),
            bg=PALETTE["panel"],
            fg=PALETTE["text"],
        )
        self.title_label.pack(pady=(8, 4))

        self.image_frame = tk.Frame(
            self,
            bg=PALETTE["surface"],
            width=400,
            height=400,
            highlightthickness=0,
        )
        self.image_frame.pack(padx=12, pady=8, fill=tk.BOTH, expand=True)
        self.image_frame.pack_propagate(False)

        self.image_label = tk.Label(
            self.image_frame,
            bg=PALETTE["surface"],
            fg=PALETTE["muted"],
            text="Image en attente",
            font=("Segoe UI", 12, "italic"),
        )
        self.image_label.pack(expand=True)

        self.info_label = tk.Label(
            self,
            text="",
            bg=PALETTE["panel"],
            fg=PALETTE["muted"],
            font=("Segoe UI", 10),
            justify=tk.LEFT,
        )
        self.info_label.pack(pady=(0, 10))

        self.photo: Optional[ImageTk.PhotoImage] = None

    def set_image(self, cv_img, info_text: str = ""):
        """Set image and info text."""
        if cv_img is None:
            self.clear()
            return

        photo, _, _ = cv2_to_photoimage(cv_img, 380, 380)

        if photo:
            self.photo = photo
            self.image_label.config(image=photo, text="")
            self.info_label.config(text=info_text, fg=PALETTE["text"])

    def clear(self):
        """Clear image and info."""
        self.image_label.config(image="", text="Image en attente")
        self.info_label.config(text="", fg=PALETTE["muted"])
        self.photo = None


class StatsBar(tk.Frame):
    """Progress bar and statistics display."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=PALETTE["surface"], **kwargs)
        self.configure(highlightbackground=PALETTE["border"], highlightthickness=1)

        self.progress_var = tk.DoubleVar(value=0)
        self.progress = ttk.Progressbar(
            self,
            variable=self.progress_var,
            maximum=100,
            mode="determinate",
            style=PROGRESS_STYLE,
        )
        self.progress.pack(fill=tk.X, padx=24, pady=(16, 10))

        stats_frame = tk.Frame(self, bg=PALETTE["surface"])
        stats_frame.pack(pady=(4, 14))

        self.placed_label = tk.Label(
            stats_frame,
            text="Placées : 0",
            bg=PALETTE["surface"],
            fg=PALETTE["accent"],
            font=("Segoe UI Semibold", 11),
        )
        self.placed_label.pack(side=tk.LEFT, padx=16)

        self.remaining_label = tk.Label(
            stats_frame,
            text="Restantes : 0",
            bg=PALETTE["surface"],
            fg=PALETTE["warning"],
            font=("Segoe UI Semibold", 11),
        )
        self.remaining_label.pack(side=tk.LEFT, padx=16)

        self.total_label = tk.Label(
            stats_frame,
            text="Total : 0",
            bg=PALETTE["surface"],
            fg=PALETTE["text"],
            font=("Segoe UI Semibold", 11),
        )
        self.total_label.pack(side=tk.LEFT, padx=16)

    def update_stats(self, placed: int, total: int):
        """Update statistics display."""
        remaining = total - placed
        progress = (placed / total * 100) if total > 0 else 0

        self.progress_var.set(progress)
        self.placed_label.config(text=f"Placées : {placed}")
        self.remaining_label.config(text=f"Restantes : {remaining}")
        self.total_label.config(text=f"Total : {total}")


class CalibrationStatusDisplay(tk.Frame):
    """Display calibration status with colored indicators."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=PALETTE["panel"], **kwargs)
        self.configure(highlightbackground=PALETTE["border"], highlightthickness=1)

        self.roi_status = tk.Label(
            self,
            text="○ Zone de remplissage : non définie",
            bg=PALETTE["panel"],
            fg=PALETTE["muted"],
            font=("Segoe UI", 10),
            anchor="w",
        )
        self.roi_status.pack(fill=tk.X, padx=10, pady=(8, 4))

        self.bg_status = tk.Label(
            self,
            text="○ Fond : non défini",
            bg=PALETTE["panel"],
            fg=PALETTE["muted"],
            font=("Segoe UI", 10),
            anchor="w",
        )
        self.bg_status.pack(fill=tk.X, padx=10, pady=(0, 8))

    def update_roi(self, roi: Optional[Tuple[int, int, int, int]]):
        """Update ROI status."""
        if roi:
            _, _, w, h = roi
            self.roi_status.config(
                text=f"✓ Zone de remplissage : {w}×{h}px",
                fg=PALETTE["accent"],
            )
        else:
            self.roi_status.config(
                text="○ Zone de remplissage : non définie",
                fg=PALETTE["muted"],
            )

    def update_background(self, bg_color: Optional[Tuple[int, int, int]]):
        """Update background sample status."""
        if bg_color:
            r, g, b = int(bg_color[2]), int(bg_color[1]), int(bg_color[0])
            self.bg_status.config(
                text=f"✓ Fond : RGB({r}, {g}, {b})",
                fg=PALETTE["accent"],
            )
        else:
            self.bg_status.config(
                text="○ Fond : non défini",
                fg=PALETTE["muted"],
            )
