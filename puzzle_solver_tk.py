"""
Puzzle Solver - Tkinter GUI Application
Main application with 3-step workflow
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import cv2
from typing import List, Optional

from models import CalibrationData, PuzzlePiece, PuzzlePieceDetector, PuzzleSolver
from widgets import CalibrationCanvas, ImagePanel, StatsBar, CalibrationStatusDisplay
from image_utils import image_cache, extract_piece_image


class PuzzleSolverApp(tk.Tk):
    """Main application window"""

    def __init__(self):
        super().__init__()

        self.title("🧩 Puzzle Solver")
        self.geometry("1200x800")
        self.configure(bg='#2c3e50')

        # State
        self.puzzle_calibration = CalibrationData()
        self.pieces_calibration = CalibrationData()
        self.puzzle_image_path = None
        self.pieces_image_paths = []
        self.puzzle_pieces = []
        self.available_pieces = []
        self.solver = None
        self.current_suggestion = None

        # Create main container
        self.container = tk.Frame(self, bg='#2c3e50')
        self.container.pack(fill=tk.BOTH, expand=True)

        # Create steps
        self.step1 = Step1Frame(self.container, self)
        self.step2 = Step2Frame(self.container, self)
        self.step3 = Step3Frame(self.container, self)

        # Show step 1
        self.show_step(1)

        # Handle cleanup on close
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def show_step(self, step_num: int):
        """Show specific step"""
        self.step1.pack_forget()
        self.step2.pack_forget()
        self.step3.pack_forget()

        if step_num == 1:
            self.step1.pack(fill=tk.BOTH, expand=True)
        elif step_num == 2:
            self.step2.pack(fill=tk.BOTH, expand=True)
        elif step_num == 3:
            self.step3.pack(fill=tk.BOTH, expand=True)

    def on_close(self):
        """Cleanup and close"""
        image_cache.cleanup()
        self.destroy()


class Step1Frame(tk.Frame):
    """Step 1: Load and calibrate puzzle state image"""

    def __init__(self, parent, app):
        super().__init__(parent, bg='#2c3e50')
        self.app = app

        # Header
        header = tk.Label(self, text="Step 1: Load Puzzle State (the hole to fill)",
                         font=('Arial', 16, 'bold'), bg='#2c3e50', fg='white')
        header.pack(pady=20)

        # Main content area
        content = tk.Frame(self, bg='#2c3e50')
        content.pack(fill=tk.BOTH, expand=True, padx=20)

        # Left side - controls
        controls = tk.Frame(content, bg='#34495e', width=300)
        controls.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        controls.pack_propagate(False)

        tk.Label(controls, text="Controls", font=('Arial', 12, 'bold'),
                bg='#34495e', fg='white').pack(pady=10)

        # Load button
        tk.Button(controls, text="📷 Browse Image",
                 command=self.load_image, bg='#3498db', fg='white',
                 font=('Arial', 11), relief=tk.RAISED, padx=20, pady=10).pack(pady=10)

        # Calibration tools
        calib_frame = tk.LabelFrame(controls, text="Calibration Tools",
                                    bg='#34495e', fg='white', font=('Arial', 10, 'bold'))
        calib_frame.pack(fill=tk.X, padx=10, pady=10)

        self.debug_var = tk.BooleanVar()
        tk.Checkbutton(calib_frame, text="Show Debug (Contours)",
                      variable=self.debug_var, command=self.toggle_debug,
                      bg='#34495e', fg='white', selectcolor='#2c3e50',
                      font=('Arial', 10)).pack(anchor=tk.W, padx=5, pady=5)

        self.btn_select_roi = tk.Button(calib_frame, text="1. Select Fill Zone",
                                        command=self.select_roi, bg='#7f8c8d', fg='white',
                                        font=('Arial', 10), state=tk.DISABLED)
        self.btn_select_roi.pack(fill=tk.X, padx=5, pady=5)

        self.btn_select_bg = tk.Button(calib_frame, text="2. Select Background",
                                       command=self.select_background, bg='#7f8c8d', fg='white',
                                       font=('Arial', 10), state=tk.DISABLED)
        self.btn_select_bg.pack(fill=tk.X, padx=5, pady=5)

        self.btn_preview = tk.Button(calib_frame, text="Preview Detection",
                                     command=self.preview_detection, bg='#7f8c8d', fg='white',
                                     font=('Arial', 10), state=tk.DISABLED)
        self.btn_preview.pack(fill=tk.X, padx=5, pady=5)

        # Area settings
        area_frame = tk.LabelFrame(controls, text="Area Filter",
                                  bg='#34495e', fg='white', font=('Arial', 10, 'bold'))
        area_frame.pack(fill=tk.X, padx=10, pady=10)

        tk.Label(area_frame, text="Min Area (px²):", bg='#34495e', fg='white').pack(anchor=tk.W, padx=5)
        self.min_area_var = tk.IntVar(value=500)
        tk.Spinbox(area_frame, from_=10, to=10000, textvariable=self.min_area_var,
                  font=('Arial', 10)).pack(fill=tk.X, padx=5, pady=2)

        tk.Label(area_frame, text="Max Area (px²):", bg='#34495e', fg='white').pack(anchor=tk.W, padx=5, pady=(5,0))
        self.max_area_var = tk.IntVar(value=50000)
        tk.Spinbox(area_frame, from_=100, to=100000, textvariable=self.max_area_var,
                  font=('Arial', 10)).pack(fill=tk.X, padx=5, pady=2)

        # Status display
        self.status_display = CalibrationStatusDisplay(controls)
        self.status_display.pack(fill=tk.X, padx=10, pady=10)

        # Status text
        self.status_label = tk.Label(controls, text="Upload an image to start",
                                     bg='#34495e', fg='#95a5a6', font=('Arial', 9))
        self.status_label.pack(pady=10)

        # Right side - canvas
        canvas_frame = tk.Frame(content, bg='#2c3e50')
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = CalibrationCanvas(canvas_frame, width=800, height=600)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.on_roi_selected = self.on_roi_selected
        self.canvas.on_background_selected = self.on_background_selected

        # Bottom - navigation
        nav = tk.Frame(self, bg='#2c3e50')
        nav.pack(fill=tk.X, pady=20)

        self.btn_next = tk.Button(nav, text="Next: Load Available Pieces →",
                                 command=self.next_step, bg='#27ae60', fg='white',
                                 font=('Arial', 12, 'bold'), padx=30, pady=10,
                                 state=tk.DISABLED)
        self.btn_next.pack(side=tk.RIGHT, padx=20)

    def load_image(self):
        """Load puzzle state image"""
        path = filedialog.askopenfilename(
            title="Select Puzzle State Image",
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.bmp")]
        )

        if not path:
            return

        img = cv2.imread(path)
        if img is None:
            messagebox.showerror("Error", "Could not load image")
            return

        self.app.puzzle_image_path = path
        self.canvas.load_image(img)

        # Enable buttons
        self.btn_select_roi.config(state=tk.NORMAL)
        self.btn_select_bg.config(state=tk.NORMAL)
        self.btn_preview.config(state=tk.NORMAL)

        self.status_label.config(text="Image loaded. Configure calibration settings.")

    def select_roi(self):
        """Activate ROI selection mode"""
        self.canvas.set_mode('roi')
        self.btn_select_roi.config(bg='#2ecc71')  # Active color
        self.btn_select_bg.config(bg='#7f8c8d')
        self.status_label.config(text="Drag on image to select Fill Zone")

    def select_background(self):
        """Activate background selection mode"""
        self.canvas.set_mode('background')
        self.btn_select_bg.config(bg='#2ecc71')  # Active color
        self.btn_select_roi.config(bg='#7f8c8d')
        self.status_label.config(text="Drag on image to select background sample")

    def on_roi_selected(self, roi):
        """Handle ROI selection"""
        self.app.puzzle_calibration.roi = roi
        self.status_display.update_roi(roi)
        self.status_label.config(text=f"Fill Zone set: {roi[2]}x{roi[3]}px")
        self.btn_select_roi.config(bg='#7f8c8d')  # Deactivate
        self.canvas.set_mode('none')
        self.check_ready()

    def on_background_selected(self, bg_color):
        """Handle background selection"""
        self.app.puzzle_calibration.background_sample = bg_color
        self.status_display.update_background(bg_color)
        r, g, b = int(bg_color[2]), int(bg_color[1]), int(bg_color[0])
        self.status_label.config(text=f"Background set: RGB({r}, {g}, {b})")
        self.btn_select_bg.config(bg='#7f8c8d')  # Deactivate
        self.canvas.set_mode('none')
        self.check_ready()

    def toggle_debug(self):
        """Toggle debug view"""
        if self.debug_var.get():
            self.preview_detection()
        else:
            # Reload original image
            if self.app.puzzle_image_path:
                img = cv2.imread(self.app.puzzle_image_path)
                if self.canvas.roi:
                    self.canvas.load_image(img)
                    self.canvas.draw_roi_overlay()
                else:
                    self.canvas.load_image(img)

    def preview_detection(self):
        """Preview piece detection with debug overlay"""
        if not self.app.puzzle_image_path:
            return

        # Update calibration from UI
        self.app.puzzle_calibration.min_area = self.min_area_var.get()
        self.app.puzzle_calibration.max_area = self.max_area_var.get()

        # Run detection with debug
        detector = PuzzlePieceDetector(self.app.puzzle_calibration)
        pieces, debug_img = detector.detect_with_debug(self.app.puzzle_image_path)

        if debug_img is not None:
            self.canvas.show_debug_image(debug_img)
            self.status_label.config(text=f"Detected {len(pieces)} pieces")

    def check_ready(self):
        """Check if ready to proceed to next step"""
        if self.app.puzzle_image_path:
            self.btn_next.config(state=tk.NORMAL)

    def next_step(self):
        """Load pieces and proceed to step 2"""
        if not self.app.puzzle_image_path:
            return

        # Update calibration
        self.app.puzzle_calibration.min_area = self.min_area_var.get()
        self.app.puzzle_calibration.max_area = self.max_area_var.get()

        # Detect pieces
        detector = PuzzlePieceDetector(self.app.puzzle_calibration)
        self.app.puzzle_pieces = detector.detect_pieces(self.app.puzzle_image_path, "puzzle_state")

        self.status_label.config(text=f"Loaded {len(self.app.puzzle_pieces)} puzzle pieces")
        self.app.show_step(2)


class Step2Frame(tk.Frame):
    """Step 2: Load and calibrate available pieces images"""

    def __init__(self, parent, app):
        super().__init__(parent, bg='#2c3e50')
        self.app = app
        self.current_image_index = 0

        # Header
        header = tk.Label(self, text="Step 2: Load Available Pieces",
                         font=('Arial', 16, 'bold'), bg='#2c3e50', fg='white')
        header.pack(pady=20)

        # Main content area
        content = tk.Frame(self, bg='#2c3e50')
        content.pack(fill=tk.BOTH, expand=True, padx=20)

        # Left side - controls
        controls = tk.Frame(content, bg='#34495e', width=300)
        controls.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        controls.pack_propagate(False)

        tk.Label(controls, text="Controls", font=('Arial', 12, 'bold'),
                bg='#34495e', fg='white').pack(pady=10)

        # Info label
        tk.Label(controls, text="ℹ️ Calibration settings apply\nto all uploaded images",
                fg='#95a5a6', bg='#34495e', font=('Arial', 9)).pack(pady=5)

        # Load button
        tk.Button(controls, text="📷 Browse Images (multiple)",
                 command=self.load_images, bg='#3498db', fg='white',
                 font=('Arial', 11), relief=tk.RAISED, padx=20, pady=10).pack(pady=10)

        # Image selector
        selector_frame = tk.Frame(controls, bg='#34495e')
        selector_frame.pack(fill=tk.X, padx=10, pady=10)

        tk.Label(selector_frame, text="Preview file:", bg='#34495e', fg='white').pack(anchor=tk.W)
        self.image_selector = ttk.Combobox(selector_frame, state='readonly')
        self.image_selector.pack(fill=tk.X, pady=5)
        self.image_selector.bind('<<ComboboxSelected>>', self.on_image_changed)

        # Calibration tools
        calib_frame = tk.LabelFrame(controls, text="Calibration Tools",
                                    bg='#34495e', fg='white', font=('Arial', 10, 'bold'))
        calib_frame.pack(fill=tk.X, padx=10, pady=10)

        self.debug_var = tk.BooleanVar()
        tk.Checkbutton(calib_frame, text="Show Debug (Contours)",
                      variable=self.debug_var, command=self.toggle_debug,
                      bg='#34495e', fg='white', selectcolor='#2c3e50',
                      font=('Arial', 10)).pack(anchor=tk.W, padx=5, pady=5)

        self.btn_select_roi = tk.Button(calib_frame, text="1. Select ROI",
                                        command=self.select_roi, bg='#7f8c8d', fg='white',
                                        font=('Arial', 10), state=tk.DISABLED)
        self.btn_select_roi.pack(fill=tk.X, padx=5, pady=5)

        self.btn_select_bg = tk.Button(calib_frame, text="2. Select Background",
                                       command=self.select_background, bg='#7f8c8d', fg='white',
                                       font=('Arial', 10), state=tk.DISABLED)
        self.btn_select_bg.pack(fill=tk.X, padx=5, pady=5)

        self.btn_preview = tk.Button(calib_frame, text="Preview Detection",
                                     command=self.preview_detection, bg='#7f8c8d', fg='white',
                                     font=('Arial', 10), state=tk.DISABLED)
        self.btn_preview.pack(fill=tk.X, padx=5, pady=5)

        # Area settings
        area_frame = tk.LabelFrame(controls, text="Area Filter",
                                  bg='#34495e', fg='white', font=('Arial', 10, 'bold'))
        area_frame.pack(fill=tk.X, padx=10, pady=10)

        tk.Label(area_frame, text="Min Area (px²):", bg='#34495e', fg='white').pack(anchor=tk.W, padx=5)
        self.min_area_var = tk.IntVar(value=500)
        tk.Spinbox(area_frame, from_=10, to=10000, textvariable=self.min_area_var,
                  font=('Arial', 10)).pack(fill=tk.X, padx=5, pady=2)

        tk.Label(area_frame, text="Max Area (px²):", bg='#34495e', fg='white').pack(anchor=tk.W, padx=5, pady=(5,0))
        self.max_area_var = tk.IntVar(value=50000)
        tk.Spinbox(area_frame, from_=100, to=100000, textvariable=self.max_area_var,
                  font=('Arial', 10)).pack(fill=tk.X, padx=5, pady=2)

        # Status display
        self.status_display = CalibrationStatusDisplay(controls)
        self.status_display.pack(fill=tk.X, padx=10, pady=10)

        # Status text
        self.status_label = tk.Label(controls, text="Upload images to start",
                                     bg='#34495e', fg='#95a5a6', font=('Arial', 9))
        self.status_label.pack(pady=10)

        # Right side - canvas
        canvas_frame = tk.Frame(content, bg='#2c3e50')
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = CalibrationCanvas(canvas_frame, width=800, height=600)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.on_roi_selected = self.on_roi_selected
        self.canvas.on_background_selected = self.on_background_selected

        # Bottom - navigation
        nav = tk.Frame(self, bg='#2c3e50')
        nav.pack(fill=tk.X, pady=20)

        tk.Button(nav, text="← Back",
                 command=lambda: self.app.show_step(1), bg='#7f8c8d', fg='white',
                 font=('Arial', 11), padx=20, pady=8).pack(side=tk.LEFT, padx=20)

        self.btn_next = tk.Button(nav, text="Next: Validate & Start →",
                                 command=self.next_step, bg='#27ae60', fg='white',
                                 font=('Arial', 12, 'bold'), padx=30, pady=10,
                                 state=tk.DISABLED)
        self.btn_next.pack(side=tk.RIGHT, padx=20)

    def load_images(self):
        """Load multiple available pieces images"""
        paths = filedialog.askopenfilenames(
            title="Select Available Pieces Images",
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.bmp")]
        )

        if not paths:
            return

        self.app.pieces_image_paths = list(paths)
        self.current_image_index = 0

        # Update selector
        image_names = [f"Image {i+1}" for i in range(len(paths))]
        self.image_selector['values'] = image_names
        self.image_selector.current(0)

        # Load first image
        img = cv2.imread(paths[0])
        if img is None:
            messagebox.showerror("Error", "Could not load first image")
            return

        self.canvas.load_image(img)

        # Enable buttons
        self.btn_select_roi.config(state=tk.NORMAL)
        self.btn_select_bg.config(state=tk.NORMAL)
        self.btn_preview.config(state=tk.NORMAL)

        self.status_label.config(text=f"Loaded {len(paths)} images. Configure calibration.")
        self.check_ready()

    def on_image_changed(self, event):
        """Handle image selection change"""
        self.current_image_index = self.image_selector.current()
        if 0 <= self.current_image_index < len(self.app.pieces_image_paths):
            path = self.app.pieces_image_paths[self.current_image_index]
            img = cv2.imread(path)
            if img:
                if self.debug_var.get():
                    self.preview_detection()
                else:
                    self.canvas.load_image(img)
                    if self.canvas.roi:
                        self.canvas.draw_roi_overlay()

    def select_roi(self):
        """Activate ROI selection mode"""
        self.canvas.set_mode('roi')
        self.btn_select_roi.config(bg='#2ecc71')
        self.btn_select_bg.config(bg='#7f8c8d')
        self.status_label.config(text="Drag on image to select ROI")

    def select_background(self):
        """Activate background selection mode"""
        self.canvas.set_mode('background')
        self.btn_select_bg.config(bg='#2ecc71')
        self.btn_select_roi.config(bg='#7f8c8d')
        self.status_label.config(text="Drag on image to select background sample")

    def on_roi_selected(self, roi):
        """Handle ROI selection"""
        self.app.pieces_calibration.roi = roi
        self.status_display.update_roi(roi)
        self.status_label.config(text=f"ROI set: {roi[2]}x{roi[3]}px")
        self.btn_select_roi.config(bg='#7f8c8d')
        self.canvas.set_mode('none')
        self.check_ready()

    def on_background_selected(self, bg_color):
        """Handle background selection"""
        self.app.pieces_calibration.background_sample = bg_color
        self.status_display.update_background(bg_color)
        r, g, b = int(bg_color[2]), int(bg_color[1]), int(bg_color[0])
        self.status_label.config(text=f"Background set: RGB({r}, {g}, {b})")
        self.btn_select_bg.config(bg='#7f8c8d')
        self.canvas.set_mode('none')
        self.check_ready()

    def toggle_debug(self):
        """Toggle debug view"""
        if self.debug_var.get():
            self.preview_detection()
        else:
            # Reload original image
            if self.app.pieces_image_paths and 0 <= self.current_image_index < len(self.app.pieces_image_paths):
                img = cv2.imread(self.app.pieces_image_paths[self.current_image_index])
                if self.canvas.roi:
                    self.canvas.load_image(img)
                    self.canvas.draw_roi_overlay()
                else:
                    self.canvas.load_image(img)

    def preview_detection(self):
        """Preview piece detection with debug overlay"""
        if not self.app.pieces_image_paths or self.current_image_index >= len(self.app.pieces_image_paths):
            return

        # Update calibration
        self.app.pieces_calibration.min_area = self.min_area_var.get()
        self.app.pieces_calibration.max_area = self.max_area_var.get()

        # Run detection with debug
        detector = PuzzlePieceDetector(self.app.pieces_calibration)
        current_path = self.app.pieces_image_paths[self.current_image_index]
        pieces, debug_img = detector.detect_with_debug(current_path)

        if debug_img is not None:
            self.canvas.show_debug_image(debug_img)
            self.status_label.config(text=f"Detected {len(pieces)} pieces in current image")

    def check_ready(self):
        """Check if ready to proceed"""
        if self.app.pieces_image_paths:
            self.btn_next.config(state=tk.NORMAL)

    def next_step(self):
        """Load all pieces and proceed to step 3"""
        if not self.app.pieces_image_paths:
            return

        # Update calibration
        self.app.pieces_calibration.min_area = self.min_area_var.get()
        self.app.pieces_calibration.max_area = self.max_area_var.get()

        # Detect pieces from all images
        detector = PuzzlePieceDetector(self.app.pieces_calibration)
        self.app.available_pieces = []

        for path in self.app.pieces_image_paths:
            pieces = detector.detect_pieces(path, "available")
            self.app.available_pieces.extend(pieces)

        total = len(self.app.puzzle_pieces) + len(self.app.available_pieces)
        self.status_label.config(text=f"Loaded {len(self.app.available_pieces)} available pieces (Total: {total})")

        # Initialize solver
        all_pieces = self.app.puzzle_pieces + self.app.available_pieces
        self.app.solver = PuzzleSolver(all_pieces)

        # Place first piece
        if self.app.puzzle_pieces:
            self.app.solver.place_piece(self.app.puzzle_pieces[0].id, (0, 0))
        elif self.app.available_pieces:
            self.app.solver.place_piece(self.app.available_pieces[0].id, (0, 0))

        self.app.show_step(3)
        self.app.step3.load_next_suggestion()


class Step3Frame(tk.Frame):
    """Step 3: Solving interface"""

    def __init__(self, parent, app):
        super().__init__(parent, bg='#2c3e50')
        self.app = app

        # Header
        header = tk.Label(self, text="🧩 Puzzle Solver",
                         font=('Arial', 18, 'bold'), bg='#2c3e50', fg='white')
        header.pack(pady=10)

        # Stats bar
        self.stats_bar = StatsBar(self)
        self.stats_bar.pack(fill=tk.X, pady=10)

        # Main content - two panels side by side
        panels = tk.Frame(self, bg='#2c3e50')
        panels.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        # Reference piece panel
        self.ref_panel = ImagePanel(panels, title="🔴 CONNECT TO THIS PIECE")
        self.ref_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)

        # Suggested piece panel
        self.piece_panel = ImagePanel(panels, title="🟢 TRY THIS PIECE")
        self.piece_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)

        # Control buttons
        controls = tk.Frame(self, bg='#2c3e50')
        controls.pack(pady=20)

        tk.Button(controls, text="✓ It Fits!",
                 command=lambda: self.handle_feedback(True),
                 bg='#27ae60', fg='white', font=('Arial', 12, 'bold'),
                 padx=30, pady=15).pack(side=tk.LEFT, padx=10)

        tk.Button(controls, text="✗ No Match",
                 command=lambda: self.handle_feedback(False),
                 bg='#e74c3c', fg='white', font=('Arial', 12, 'bold'),
                 padx=30, pady=15).pack(side=tk.LEFT, padx=10)

        tk.Button(controls, text="⊘ Skip",
                 command=self.load_next_suggestion,
                 bg='#95a5a6', fg='white', font=('Arial', 12, 'bold'),
                 padx=30, pady=15).pack(side=tk.LEFT, padx=10)

    def load_next_suggestion(self):
        """Load next piece suggestion"""
        if not self.app.solver:
            return

        suggestion = self.app.solver.get_best_suggestion()

        if not suggestion:
            messagebox.showinfo("Complete", "Puzzle complete or no more suggestions!")
            return

        self.app.current_suggestion = suggestion

        # Load reference piece image
        ref_piece = suggestion['ref_piece']
        ref_img = extract_piece_image(ref_piece.source_image, ref_piece.bbox_in_source, (255, 0, 0))

        side_names = ['TOP', 'RIGHT', 'BOTTOM', 'LEFT']
        side_name = side_names[suggestion['side']]

        ref_info = f"Piece #{ref_piece.id}\nConnect on: {side_name} side\nTabs: {ref_piece.tabs}"
        self.ref_panel.set_image(ref_img, ref_info)

        # Load suggested piece image
        piece = suggestion['piece']
        piece_img = extract_piece_image(piece.source_image, piece.bbox_in_source, (0, 255, 0))

        piece_info = f"Piece #{piece.id}\nConfidence: {suggestion['score']*100:.1f}%\nTabs: {piece.tabs}"
        self.piece_panel.set_image(piece_img, piece_info)

        # Update stats
        self.update_stats()

    def handle_feedback(self, fits: bool):
        """Handle user feedback on suggested match"""
        if not self.app.current_suggestion:
            return

        suggestion = self.app.current_suggestion
        piece = suggestion['piece']
        ref_piece = suggestion['ref_piece']
        side = suggestion['side']

        if fits:
            # Place piece
            self.app.solver.place_piece(piece.id, suggestion['position'])
        else:
            # Reject match
            self.app.solver.reject_match(ref_piece.id, side, piece.id)

        # Load next suggestion
        self.load_next_suggestion()

    def update_stats(self):
        """Update statistics display"""
        if not self.app.solver:
            return

        placed = len(self.app.solver.used)
        total = len(self.app.solver.pieces)

        self.stats_bar.update_stats(placed, total)


def main():
    """Run the application"""
    app = PuzzleSolverApp()
    app.mainloop()


if __name__ == "__main__":
    main()
