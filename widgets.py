"""
Custom widgets and theme helpers for Octopuzzle.
"""

import math
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
    "disabled_bg": "#27344b",
    "disabled_fg": "#a0acc2",
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
    root.option_add("*Font", "{Segoe UI} 11")
    root.option_add("*TLabel.Font", "{Segoe UI} 11")
    root.option_add("*TButton.Font", "{Segoe UI} 11")
    root.option_add("*TCombobox*Listbox.Font", "{Segoe UI} 11")
    root.option_add("*Entry.Font", "{Segoe UI} 11")
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
            ("pressed", PALETTE["accent_active"]),
            ("disabled", PALETTE["disabled_bg"]),
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
        background=[
            ("active", PALETTE["neutral_hover"]),
            ("pressed", PALETTE["neutral_active"]),
            ("disabled", PALETTE["disabled_bg"]),
        ],
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


class ZoomableImageCanvas(tk.Canvas):
    """Canvas that auto-fits and zooms images around the cursor."""

    def __init__(self, parent, width=800, height=600, max_zoom: Optional[float] = None, **kwargs):
        defaults = {
            "width": width,
            "height": height,
            "bg": PALETTE["canvas"],
            "highlightthickness": 1,
            "highlightbackground": PALETTE["border"],
            "bd": 0,
        }
        defaults.update(kwargs)
        super().__init__(parent, **defaults)

        self.base_image = None
        self.display_image = None
        self.photo: Optional[ImageTk.PhotoImage] = None
        self.image_id: Optional[int] = None

        self.zoom = 1.0
        self.fit_zoom = 1.0
        self.min_zoom = 1.0
        self.max_zoom = None if max_zoom is None or max_zoom <= 0 else float(max_zoom)
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.user_zoomed = False

        self.base_width = 0
        self.base_height = 0
        self.display_width = 0
        self.display_height = 0
        self.view_left = 0
        self.view_top = 0
        self.view_width = 0
        self.view_height = 0
        self.view_canvas_left = 0.0
        self.view_canvas_top = 0.0

        self.primary_pan_enabled = False
        self._pending_render = False
        self._pan_active = False
        self._pan_button: Optional[int] = None
        self._pan_last = (0, 0)
        self._pan_candidate = None
        self._space_pan = False

        self.bind("<Configure>", self._on_configure)
        self.bind("<MouseWheel>", self._on_mousewheel)
        self.bind("<Button-4>", self._on_mousewheel)
        self.bind("<Button-5>", self._on_mousewheel)
        self.bind("<Double-Button-1>", self._on_double_click)
        self.bind("<Enter>", lambda _evt: self.focus_set())
        self.bind("<ButtonPress-2>", self._start_pan, add="+")
        self.bind("<ButtonPress-3>", self._start_pan, add="+")
        self.bind("<B2-Motion>", self._do_pan, add="+")
        self.bind("<B3-Motion>", self._do_pan, add="+")
        self.bind("<ButtonRelease-2>", self._stop_pan, add="+")
        self.bind("<ButtonRelease-3>", self._stop_pan, add="+")
        self.bind("<KeyPress-space>", self._on_space_press, add="+")
        self.bind("<KeyRelease-space>", self._on_space_release, add="+")
        self.bind("<ButtonPress-1>", self._maybe_start_primary_pan, add="+")
        self.bind("<B1-Motion>", self._maybe_do_primary_pan, add="+")
        self.bind("<ButtonRelease-1>", self._maybe_stop_primary_pan, add="+")

    def set_base_image(self, cv_img, reset_view: bool = True):
        """Assign a new base image (resets the view unless specified)."""
        if cv_img is None:
            return

        self.base_image = cv_img
        self.base_height, self.base_width = cv_img.shape[:2]
        self.set_display_image(cv_img, reset_view=reset_view)

    def set_display_image(self, cv_img, reset_view: bool = False):
        """Update the displayed image, preserving zoom unless requested."""
        if cv_img is None:
            return

        self.display_image = cv_img
        if self.base_image is None:
            self.base_image = cv_img
            self.base_height, self.base_width = cv_img.shape[:2]

        if reset_view:
            self.user_zoomed = False

        self._update_fit_zoom(force=reset_view)
        self._request_render()

    def clear_image(self):
        """Clear the canvas image and reset zoom state."""
        if self.image_id is not None:
            self.delete(self.image_id)
            self.image_id = None

        self.photo = None
        self.base_image = None
        self.display_image = None
        self.base_width = 0
        self.base_height = 0
        self.display_width = 0
        self.display_height = 0
        self.view_left = 0
        self.view_top = 0
        self.view_width = 0
        self.view_height = 0
        self.view_canvas_left = 0.0
        self.view_canvas_top = 0.0

        self.zoom = 1.0
        self.fit_zoom = 1.0
        self.min_zoom = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.user_zoomed = False
        self._pan_active = False
        self._pan_button = None
        self._pan_candidate = None
        self._space_pan = False
        self._pan_last = (0, 0)

    def reset_view(self):
        """Reset zoom and centering to fit within the canvas."""
        if self.display_image is None:
            return
        self.user_zoomed = False
        self._update_fit_zoom(force=True)
        self._render_image()

    def set_primary_pan_enabled(self, enabled: bool):
        """Allow panning with the primary button without holding space."""
        self.primary_pan_enabled = bool(enabled)

    def is_panning(self) -> bool:
        """Return whether a pan gesture is currently active."""
        return self._pan_active

    def canvas_to_image(self, x: float, y: float) -> Tuple[Optional[float], Optional[float]]:
        """Convert canvas coordinates to image coordinates."""
        if self.display_image is None:
            return None, None

        img_h, img_w = self.display_image.shape[:2]
        if (
            img_w == 0
            or img_h == 0
            or self.view_width <= 0
            or self.view_height <= 0
        ):
            return None, None

        left = self.view_canvas_left
        top = self.view_canvas_top
        right = left + self.view_width * self.zoom
        bottom = top + self.view_height * self.zoom

        if x < left or x > right or y < top or y > bottom:
            return None, None

        img_x = self.view_left + (x - left) / self.zoom
        img_y = self.view_top + (y - top) / self.zoom
        return img_x, img_y

    def _on_double_click(self, _event):
        self.reset_view()

    def _on_space_press(self, _event):
        self._space_pan = True

    def _on_space_release(self, event):
        self._space_pan = False
        if self._pan_active and self._pan_button == 1:
            self._stop_pan(event, force=True)

    def _start_pan(self, event):
        if self.display_image is None:
            return
        button = getattr(event, "num", None)
        if button is None and hasattr(event, "button"):
            button = event.button
        self.focus_set()
        self._pan_active = True
        self._pan_button = button
        self._pan_candidate = None
        self._pan_last = (event.x, event.y)
        return "break"

    def _do_pan(self, event):
        if not self._pan_active:
            return
        dx = event.x - self._pan_last[0]
        dy = event.y - self._pan_last[1]
        if dx == 0 and dy == 0:
            return "break"
        self._pan_last = (event.x, event.y)
        self.offset_x += dx
        self.offset_y += dy
        self.user_zoomed = True
        self._render_image()
        return "break"

    def _stop_pan(self, event, force: bool = False):
        if not self._pan_active:
            return
        button = getattr(event, "num", None)
        if button is None and hasattr(event, "button"):
            button = event.button
        if not force and self._pan_button not in (None, button):
            return
        self._pan_active = False
        self._pan_button = None
        self._pan_candidate = None
        return "break"

    def _maybe_start_primary_pan(self, event):
        if self.display_image is None:
            return
        if self._space_pan:
            self.focus_set()
            self._pan_active = True
            self._pan_button = 1
            self._pan_candidate = None
            self._pan_last = (event.x, event.y)
            return "break"
        if self.primary_pan_enabled:
            self.focus_set()
            self._pan_candidate = (event.x, event.y)

    def _maybe_do_primary_pan(self, event):
        if self.display_image is None:
            return
        if self._pan_active and self._pan_button == 1:
            return self._do_pan(event)
        if self.primary_pan_enabled and self._pan_candidate is not None:
            start_x, start_y = self._pan_candidate
            if abs(event.x - start_x) < 1 and abs(event.y - start_y) < 1:
                return
            self._pan_button = 1
            self._pan_active = True
            self._pan_last = (start_x, start_y)
            self._pan_candidate = None
            return self._do_pan(event)

    def _maybe_stop_primary_pan(self, event):
        if self._pan_active and self._pan_button == 1:
            return self._stop_pan(event, force=True)
        if self.primary_pan_enabled:
            self._pan_candidate = None
            if not self._pan_active:
                self._pan_button = None

    def _on_configure(self, _event):
        if self.display_image is None:
            return
        self._update_fit_zoom()
        self._render_image()

    def _on_mousewheel(self, event):
        if self.display_image is None:
            return

        delta = 0
        if hasattr(event, "delta") and event.delta:
            delta = event.delta
        elif hasattr(event, "num"):
            if event.num == 4:
                delta = 120
            elif event.num == 5:
                delta = -120

        if delta == 0:
            return

        factor = 1.12 if delta > 0 else 1 / 1.12
        self._zoom_at(event.x, event.y, factor)

    def _zoom_at(self, canvas_x: float, canvas_y: float, factor: float):
        if self.display_image is None:
            return

        if self.max_zoom is not None:
            new_zoom = max(self.min_zoom, min(self.max_zoom, self.zoom * factor))
        else:
            new_zoom = max(self.min_zoom, self.zoom * factor)
        if abs(new_zoom - self.zoom) < 1e-3:
            return

        img_coords = self.canvas_to_image(canvas_x, canvas_y)
        if img_coords[0] is None or img_coords[1] is None:
            img_x = (self.base_width or self.display_image.shape[1]) / 2
            img_y = (self.base_height or self.display_image.shape[0]) / 2
        else:
            img_x, img_y = img_coords

        self.zoom = new_zoom
        self.user_zoomed = True

        self._update_offset_after_zoom(img_x, img_y, canvas_x, canvas_y)
        self._render_image()

    def _update_fit_zoom(self, force: bool = False):
        if self.display_image is None:
            return

        canvas_w = max(1, self.winfo_width())
        canvas_h = max(1, self.winfo_height())
        if canvas_w <= 1 or canvas_h <= 1:
            return

        img_h, img_w = self.display_image.shape[:2]
        if img_w == 0 or img_h == 0:
            return

        fit = min(canvas_w / img_w, canvas_h / img_h)
        if fit <= 0:
            fit = 1.0

        self.fit_zoom = fit
        self.min_zoom = max(0.1, fit * 0.2)

        if force or not self.user_zoomed:
            self.zoom = self.fit_zoom
            if self.max_zoom is not None and self.zoom > self.max_zoom:
                self.zoom = self.max_zoom
            self.offset_x = 0.0
            self.offset_y = 0.0
        else:
            if self.zoom < self.min_zoom:
                self.zoom = self.min_zoom
            if self.max_zoom is not None and self.zoom > self.max_zoom:
                self.zoom = self.max_zoom

        scaled_w = img_w * self.zoom
        scaled_h = img_h * self.zoom
        self._clamp_offsets(canvas_w, canvas_h, scaled_w, scaled_h)

    def _update_offset_after_zoom(self, img_x: float, img_y: float, canvas_x: float, canvas_y: float):
        canvas_w = max(1, self.winfo_width())
        canvas_h = max(1, self.winfo_height())

        img_h, img_w = self.display_image.shape[:2]
        scaled_w = img_w * self.zoom
        scaled_h = img_h * self.zoom

        left = canvas_x - img_x * self.zoom
        top = canvas_y - img_y * self.zoom

        center_x = left + scaled_w / 2
        center_y = top + scaled_h / 2

        self.offset_x = center_x - canvas_w / 2
        self.offset_y = center_y - canvas_h / 2

        self._clamp_offsets(canvas_w, canvas_h, scaled_w, scaled_h)

    def _clamp_offsets(self, canvas_w: float, canvas_h: float, scaled_w: float, scaled_h: float):
        if scaled_w <= canvas_w:
            self.offset_x = 0.0
        else:
            max_offset_x = (scaled_w - canvas_w) / 2
            self.offset_x = max(-max_offset_x, min(max_offset_x, self.offset_x))

        if scaled_h <= canvas_h:
            self.offset_y = 0.0
        else:
            max_offset_y = (scaled_h - canvas_h) / 2
            self.offset_y = max(-max_offset_y, min(max_offset_y, self.offset_y))

    def _request_render(self):
        if not self._pending_render:
            self._pending_render = True
            self.after_idle(self._render_image)

    def _render_image(self):
        self._pending_render = False

        if self.display_image is None:
            return

        canvas_w = max(1, self.winfo_width())
        canvas_h = max(1, self.winfo_height())
        if canvas_w <= 1 or canvas_h <= 1:
            self._request_render()
            return

        img_h, img_w = self.display_image.shape[:2]
        if img_w == 0 or img_h == 0:
            return

        total_scaled_w = img_w * self.zoom
        total_scaled_h = img_h * self.zoom

        left_canvas = canvas_w / 2 + self.offset_x - total_scaled_w / 2
        top_canvas = canvas_h / 2 + self.offset_y - total_scaled_h / 2

        left_img = max(0, int(math.floor(-left_canvas / self.zoom)))
        top_img = max(0, int(math.floor(-top_canvas / self.zoom)))
        right_img = min(img_w, int(math.ceil((canvas_w - left_canvas) / self.zoom)))
        bottom_img = min(img_h, int(math.ceil((canvas_h - top_canvas) / self.zoom)))

        if right_img <= left_img or bottom_img <= top_img:
            left_img, top_img = 0, 0
            right_img, bottom_img = img_w, img_h
            left_canvas = (canvas_w - total_scaled_w) / 2
            top_canvas = (canvas_h - total_scaled_h) / 2

        self.view_left = left_img
        self.view_top = top_img
        self.view_width = max(1, right_img - left_img)
        self.view_height = max(1, bottom_img - top_img)

        crop = self.display_image[top_img:bottom_img, left_img:right_img]
        scaled_w = max(1, int(round(self.view_width * self.zoom)))
        scaled_h = max(1, int(round(self.view_height * self.zoom)))

        interpolation = cv2.INTER_NEAREST if self.zoom >= 1.0 else cv2.INTER_AREA
        resized = cv2.resize(crop, (scaled_w, scaled_h), interpolation=interpolation)

        photo, display_w, display_h = cv2_to_photoimage(resized)
        if not photo:
            return

        self.photo = photo
        self.display_width = display_w
        self.display_height = display_h

        self._clamp_offsets(canvas_w, canvas_h, total_scaled_w, total_scaled_h)

        canvas_left = max(left_canvas, 0.0)
        canvas_top = max(top_canvas, 0.0)
        self.view_canvas_left = canvas_left
        self.view_canvas_top = canvas_top

        center_x = canvas_left + display_w / 2
        center_y = canvas_top + display_h / 2

        if self.image_id is None:
            self.image_id = self.create_image(center_x, center_y, image=photo, anchor=tk.CENTER)
        else:
            self.coords(self.image_id, center_x, center_y)
            self.itemconfig(self.image_id, image=photo)

        self.tag_lower(self.image_id)


class CalibrationCanvas(ZoomableImageCanvas):
    """
    Canvas with interactive calibration features:
    - Drag to select ROI
    - Drag to select background sample
    - Real-time visual feedback
    """

    def __init__(self, parent, width=800, height=600, **kwargs):
        super().__init__(parent, width=width, height=height, **kwargs)

        self.mode = "none"  # 'roi', 'background', or 'none'
        self.roi: Optional[Tuple[int, int, int, int]] = None
        self.outer_roi: Optional[Tuple[int, int, int, int]] = None
        self.inner_roi: Optional[Tuple[int, int, int, int]] = None
        self.background_sample: Optional[Tuple[int, int, int]] = None

        self.drag_start: Optional[Tuple[int, int]] = None
        self.drag_rect_id = None

        # Callbacks
        self.on_roi_selected: Optional[Callable[[Tuple[int, int, int, int]], None]] = None
        self.on_outer_selected: Optional[Callable[[Tuple[int, int, int, int]], None]] = None
        self.on_inner_selected: Optional[Callable[[Tuple[int, int, int, int]], None]] = None
        self.on_background_selected: Optional[Callable[[Tuple[int, int, int]], None]] = None

        # Bind mouse events specific to calibration
        self.bind("<ButtonPress-1>", self._on_mouse_down, add="+")
        self.bind("<B1-Motion>", self._on_mouse_drag, add="+")
        self.bind("<ButtonRelease-1>", self._on_mouse_up, add="+")

    def set_mode(self, mode: str):
        """Set interaction mode: 'roi', 'background', or 'none'."""
        self.mode = mode
        if mode == "none":
            self.drag_start = None
            self.configure(cursor="arrow")
        else:
            self.configure(cursor="crosshair")

    def load_image(self, cv_img):
        """Load and display image."""
        if cv_img is None:
            return

        self.roi = None
        self.outer_roi = None
        self.inner_roi = None
        self.background_sample = None
        self.set_base_image(cv_img, reset_view=True)

    def show_image(self, cv_img):
        """Display provided image without altering base reference."""
        self.set_display_image(cv_img)

    def show_debug_image(self, debug_img):
        """Display debug image with contours."""
        self.set_display_image(debug_img)

    def draw_roi_overlay(self):
        """Draw ROI overlay on current image."""
        if self.base_image is None:
            return

        img_with_overlay = draw_roi_overlay(self.base_image, self.roi or self.outer_roi, self.inner_roi)
        self.set_display_image(img_with_overlay)

    def clear(self):
        """Clear canvas."""
        super().clear_image()
        self.delete("all")
        self.roi = None
        self.outer_roi = None
        self.inner_roi = None
        self.background_sample = None
        self.drag_rect_id = None
        self.drag_start = None

    def _on_mouse_down(self, event):
        """Handle mouse button press."""
        if self.mode == "none":
            return

        if self.is_panning():
            return

        self.drag_start = (event.x, event.y)

    def _on_mouse_drag(self, event):
        """Handle mouse drag - show selection rectangle."""
        if self.drag_start is None or self.mode == "none":
            return

        if self.is_panning():
            return

        if self.drag_rect_id:
            self.delete(self.drag_rect_id)
            self.drag_rect_id = None

        x1, y1 = self.drag_start
        x2, y2 = event.x, event.y

        if self.mode in {"outer", "roi"}:
            color = PALETTE["accent"]
        elif self.mode == "inner":
            color = "#63d6ff"
        else:
            color = PALETTE["warning"]
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

        if self.is_panning():
            self.drag_start = None
            return

        if self.drag_rect_id:
            self.delete(self.drag_rect_id)
            self.drag_rect_id = None

        if self.base_image is None:
            self.drag_start = None
            return

        start = self.canvas_to_image(*self.drag_start)
        end = self.canvas_to_image(event.x, event.y)

        if start[0] is None or end[0] is None:
            self.drag_start = None
            return

        x1, y1 = start
        x2, y2 = end

        min_x = max(0.0, min(x1, x2))
        min_y = max(0.0, min(y1, y2))
        max_x = min(float(self.base_width), max(x1, x2))
        max_y = min(float(self.base_height), max(y1, y2))

        width = max_x - min_x
        height = max_y - min_y

        if width < 10 or height < 10:
            self.drag_start = None
            return

        x = int(round(min_x))
        y = int(round(min_y))
        w = int(round(width))
        h = int(round(height))

        w = min(w, self.base_width - x)
        h = min(h, self.base_height - y)

        if w <= 0 or h <= 0:
            self.drag_start = None
            return

        if self.mode == "roi":
            self.roi = (x, y, w, h)
            self.draw_roi_overlay()
            if self.on_roi_selected:
                self.on_roi_selected(self.roi)

        elif self.mode == "outer":
            self.outer_roi = (x, y, w, h)
            self.draw_roi_overlay()
            if self.on_outer_selected:
                self.on_outer_selected(self.outer_roi)

        elif self.mode == "inner":
            self.inner_roi = (x, y, w, h)
            self.draw_roi_overlay()
            if self.on_inner_selected:
                self.on_inner_selected(self.inner_roi)

        elif self.mode == "background" and self.base_image is not None:
            roi_img = self.base_image[y : y + h, x : x + w]
            if roi_img.size > 0:
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

        self.canvas = ZoomableImageCanvas(
            self.image_frame,
            width=400,
            height=400,
            bg=PALETTE["surface"],
            highlightthickness=0,
            highlightbackground=PALETTE["surface"],
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.set_primary_pan_enabled(True)

        self.placeholder = tk.Label(
            self.image_frame,
            bg=PALETTE["surface"],
            fg=PALETTE["muted"],
            text="Image en attente",
            font=("Segoe UI", 12, "italic"),
        )
        self.placeholder.place(relx=0.5, rely=0.5, anchor="center")

        self.info_label = tk.Label(
            self,
            text="",
            bg=PALETTE["panel"],
            fg=PALETTE["muted"],
            font=("Segoe UI", 10),
            justify=tk.LEFT,
        )
        self.info_label.pack(pady=(0, 10))

    def set_image(self, cv_img, info_text: str = ""):
        """Set image and info text."""
        if cv_img is None:
            self.clear()
            return

        self.canvas.set_base_image(cv_img, reset_view=True)
        self.placeholder.place_forget()

        if info_text:
            self.info_label.config(text=info_text, fg=PALETTE["text"])
        else:
            self.info_label.config(text="", fg=PALETTE["muted"])

    def clear(self):
        """Clear image and info."""
        self.canvas.clear_image()
        self.placeholder.place(relx=0.5, rely=0.5, anchor="center")
        self.info_label.config(text="", fg=PALETTE["muted"])


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
            text="○ Bord extérieur : non défini",
            bg=PALETTE["panel"],
            fg=PALETTE["muted"],
            font=("Segoe UI", 10),
            anchor="w",
        )
        self.roi_status.pack(fill=tk.X, padx=10, pady=(8, 4))

        self.inner_status = tk.Label(
            self,
            text="○ Zone interne : non définie",
            bg=PALETTE["panel"],
            fg=PALETTE["muted"],
            font=("Segoe UI", 10),
            anchor="w",
        )
        self.inner_status.pack(fill=tk.X, padx=10, pady=(0, 4))

        self.bg_status = tk.Label(
            self,
            text="○ Fond : non défini",
            bg=PALETTE["panel"],
            fg=PALETTE["muted"],
            font=("Segoe UI", 10),
            anchor="w",
        )
        self.bg_status.pack(fill=tk.X, padx=10, pady=(0, 8))

    def update_outer_roi(self, roi: Optional[Tuple[int, int, int, int]]):
        """Update outer ROI status."""
        if roi:
            _, _, w, h = roi
            self.roi_status.config(
                text=f"✓ Bord extérieur : {w}×{h}px",
                fg=PALETTE["accent"],
            )
        else:
            self.roi_status.config(
                text="○ Bord extérieur : non défini",
                fg=PALETTE["muted"],
            )

    def update_inner_roi(self, roi: Optional[Tuple[int, int, int, int]]):
        """Update inner ROI status."""
        if roi:
            _, _, w, h = roi
            self.inner_status.config(
                text=f"✓ Zone interne : {w}×{h}px",
                fg="#63d6ff",
            )
        else:
            self.inner_status.config(
                text="○ Zone interne : non définie",
                fg=PALETTE["muted"],
            )

    def update_roi(self, roi: Optional[Tuple[int, int, int, int]]):
        """Backward compatibility for single ROI workflows."""
        self.update_outer_roi(roi)

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
