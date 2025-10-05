"""
Custom Tkinter widgets for Puzzle Solver
Contains: CalibrationCanvas, ImagePanel, StatsBar
"""

import tkinter as tk
from tkinter import ttk
from PIL import ImageTk
import cv2
from typing import Optional, Tuple, Callable
from image_utils import cv2_to_photoimage, draw_roi_overlay, draw_selection_rect


class CalibrationCanvas(tk.Canvas):
    """
    Canvas with interactive calibration features:
    - Drag to select ROI
    - Drag to select background sample
    - Real-time visual feedback
    """

    def __init__(self, parent, width=800, height=600, **kwargs):
        super().__init__(parent, width=width, height=height, bg='#2c3e50', **kwargs)

        self.image = None  # Current cv2 image
        self.photo = None  # Current PhotoImage
        self.image_id = None  # Canvas image ID

        self.mode = 'none'  # 'roi', 'background', or 'none'
        self.roi = None  # (x, y, w, h)
        self.background_sample = None  # (B, G, R)

        self.drag_start = None
        self.drag_rect_id = None

        # Bind mouse events
        self.bind('<ButtonPress-1>', self._on_mouse_down)
        self.bind('<B1-Motion>', self._on_mouse_drag)
        self.bind('<ButtonRelease-1>', self._on_mouse_up)

        # Callbacks
        self.on_roi_selected = None  # Callback when ROI is selected
        self.on_background_selected = None  # Callback when background is selected

    def set_mode(self, mode: str):
        """Set interaction mode: 'roi', 'background', or 'none'"""
        self.mode = mode
        if mode == 'none':
            self.drag_start = None

    def load_image(self, cv_img):
        """Load and display image"""
        if cv_img is None:
            return

        self.image = cv_img
        self._display_image(cv_img)

    def show_debug_image(self, debug_img):
        """Display debug image with contours"""
        self._display_image(debug_img)

    def draw_roi_overlay(self):
        """Draw ROI overlay on current image"""
        if self.image is None or self.roi is None:
            return

        img_with_overlay = draw_roi_overlay(self.image, self.roi)
        self._display_image(img_with_overlay)

    def clear(self):
        """Clear canvas"""
        self.delete('all')
        self.image = None
        self.photo = None
        self.image_id = None

    def _display_image(self, cv_img):
        """Display OpenCV image on canvas"""
        if cv_img is None:
            return

        # Get canvas size
        canvas_width = self.winfo_width()
        canvas_height = self.winfo_height()

        # Use default if not yet realized
        if canvas_width <= 1:
            canvas_width = int(self['width'])
        if canvas_height <= 1:
            canvas_height = int(self['height'])

        # Convert to PhotoImage
        photo, w, h = cv2_to_photoimage(cv_img, canvas_width, canvas_height)

        if photo:
            self.photo = photo
            self.delete('all')
            self.image_id = self.create_image(canvas_width // 2, canvas_height // 2,
                                             image=photo, anchor=tk.CENTER)

    def _on_mouse_down(self, event):
        """Handle mouse button press"""
        if self.mode == 'none':
            return

        self.drag_start = (event.x, event.y)

    def _on_mouse_drag(self, event):
        """Handle mouse drag - show selection rectangle"""
        if self.drag_start is None or self.mode == 'none':
            return

        # Remove previous rectangle
        if self.drag_rect_id:
            self.delete(self.drag_rect_id)

        # Draw new rectangle
        x1, y1 = self.drag_start
        x2, y2 = event.x, event.y

        color = '#4287f5' if self.mode == 'roi' else '#f5a142'
        self.drag_rect_id = self.create_rectangle(x1, y1, x2, y2,
                                                  outline=color, width=2,
                                                  dash=(5, 5))

    def _on_mouse_up(self, event):
        """Handle mouse button release - finalize selection"""
        if self.drag_start is None or self.mode == 'none':
            return

        # Remove drag rectangle
        if self.drag_rect_id:
            self.delete(self.drag_rect_id)
            self.drag_rect_id = None

        # Calculate selection
        x1, y1 = self.drag_start
        x2, y2 = event.x, event.y

        # Convert to image coordinates
        x = min(x1, x2)
        y = min(y1, y2)
        w = abs(x2 - x1)
        h = abs(y2 - y1)

        # Minimum size check
        if w < 10 or h < 10:
            self.drag_start = None
            return

        # Scale to image coordinates if needed
        if self.image is not None and self.photo is not None:
            img_h, img_w = self.image.shape[:2]
            canvas_w = self.winfo_width()
            canvas_h = self.winfo_height()

            # Calculate image position on canvas (centered)
            photo_w = self.photo.width()
            photo_h = self.photo.height()
            offset_x = (canvas_w - photo_w) // 2
            offset_y = (canvas_h - photo_h) // 2

            # Adjust coordinates
            x -= offset_x
            y -= offset_y

            # Scale to original image size
            scale_x = img_w / photo_w
            scale_y = img_h / photo_h

            x = int(x * scale_x)
            y = int(y * scale_y)
            w = int(w * scale_x)
            h = int(h * scale_y)

            # Clamp to image bounds
            x = max(0, min(x, img_w - 1))
            y = max(0, min(y, img_h - 1))
            w = min(w, img_w - x)
            h = min(h, img_h - y)

        # Handle based on mode
        if self.mode == 'roi':
            self.roi = (x, y, w, h)
            self.draw_roi_overlay()
            if self.on_roi_selected:
                self.on_roi_selected(self.roi)

        elif self.mode == 'background':
            # Get average color from selected area
            if self.image is not None:
                roi_img = self.image[y:y+h, x:x+w]
                avg_color = cv2.mean(roi_img)[:3]
                self.background_sample = tuple(int(c) for c in avg_color)
                if self.on_background_selected:
                    self.on_background_selected(self.background_sample)

        self.drag_start = None


class ImagePanel(tk.Frame):
    """Panel to display a piece image with info"""

    def __init__(self, parent, title="", bg_color='#34495e', **kwargs):
        super().__init__(parent, bg=bg_color, **kwargs)

        # Title
        self.title_label = tk.Label(self, text=title, font=('Arial', 12, 'bold'),
                                    bg=bg_color, fg='white')
        self.title_label.pack(pady=5)

        # Image container
        self.image_frame = tk.Frame(self, bg='#2c3e50', width=400, height=400)
        self.image_frame.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        self.image_frame.pack_propagate(False)

        self.image_label = tk.Label(self.image_frame, bg='#2c3e50', fg='#95a5a6',
                                    text="No image", font=('Arial', 14))
        self.image_label.pack(expand=True)

        # Info label
        self.info_label = tk.Label(self, text="", bg=bg_color, fg='white',
                                  font=('Arial', 10), justify=tk.LEFT)
        self.info_label.pack(pady=5)

        self.photo = None  # Keep reference

    def set_image(self, cv_img, info_text=""):
        """Set image and info text"""
        if cv_img is None:
            self.image_label.config(image='', text="No image")
            self.info_label.config(text="")
            return

        # Convert to PhotoImage
        photo, _, _ = cv2_to_photoimage(cv_img, 380, 380)

        if photo:
            self.photo = photo
            self.image_label.config(image=photo, text="")
            self.info_label.config(text=info_text)

    def clear(self):
        """Clear image and info"""
        self.image_label.config(image='', text="No image")
        self.info_label.config(text="")
        self.photo = None


class StatsBar(tk.Frame):
    """Progress bar and statistics display"""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg='#2c3e50', **kwargs)

        # Progress bar
        self.progress_var = tk.DoubleVar(value=0)
        self.progress = ttk.Progressbar(self, variable=self.progress_var,
                                       maximum=100, mode='determinate')
        self.progress.pack(fill=tk.X, padx=20, pady=10)

        # Stats labels
        stats_frame = tk.Frame(self, bg='#2c3e50')
        stats_frame.pack(pady=5)

        self.placed_label = tk.Label(stats_frame, text="Placed: 0",
                                    bg='#2c3e50', fg='#2ecc71',
                                    font=('Arial', 11, 'bold'))
        self.placed_label.pack(side=tk.LEFT, padx=15)

        self.remaining_label = tk.Label(stats_frame, text="Remaining: 0",
                                       bg='#2c3e50', fg='#e67e22',
                                       font=('Arial', 11, 'bold'))
        self.remaining_label.pack(side=tk.LEFT, padx=15)

        self.total_label = tk.Label(stats_frame, text="Total: 0",
                                   bg='#2c3e50', fg='#3498db',
                                   font=('Arial', 11, 'bold'))
        self.total_label.pack(side=tk.LEFT, padx=15)

    def update_stats(self, placed: int, total: int):
        """Update statistics display"""
        remaining = total - placed
        progress = (placed / total * 100) if total > 0 else 0

        self.progress_var.set(progress)
        self.placed_label.config(text=f"Placed: {placed}")
        self.remaining_label.config(text=f"Remaining: {remaining}")
        self.total_label.config(text=f"Total: {total}")


class CalibrationStatusDisplay(tk.Frame):
    """Display calibration status with colored indicators"""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg='#34495e', **kwargs)

        self.roi_status = tk.Label(self, text="○ ROI: Not set",
                                  bg='#34495e', fg='#95a5a6',
                                  font=('Arial', 10))
        self.roi_status.pack(anchor=tk.W, padx=5, pady=2)

        self.bg_status = tk.Label(self, text="○ Background: Not set",
                                 bg='#34495e', fg='#95a5a6',
                                 font=('Arial', 10))
        self.bg_status.pack(anchor=tk.W, padx=5, pady=2)

    def update_roi(self, roi: Optional[Tuple[int, int, int, int]]):
        """Update ROI status"""
        if roi:
            _, _, w, h = roi
            self.roi_status.config(text=f"✓ ROI: {w}x{h}px",
                                  fg='#2ecc71', bg='#27ae60')
        else:
            self.roi_status.config(text="○ ROI: Not set",
                                  fg='#95a5a6', bg='#34495e')

    def update_background(self, bg_color: Optional[Tuple[int, int, int]]):
        """Update background status"""
        if bg_color:
            # Convert BGR to RGB for display
            r, g, b = int(bg_color[2]), int(bg_color[1]), int(bg_color[0])
            self.bg_status.config(text=f"✓ Background: RGB({r}, {g}, {b})",
                                 fg='#2ecc71', bg='#27ae60')
        else:
            self.bg_status.config(text="○ Background: Not set",
                                 fg='#95a5a6', bg='#34495e')
