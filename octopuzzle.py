"""
Octopuzzle - Desktop assistant to help fill uniform puzzle areas.
Main application with the 3-step workflow (calibrate hole → calibrate pieces → solve).
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import cv2
from typing import List, Optional
from pathlib import Path

from models import CalibrationData, PuzzlePiece, PuzzlePieceDetector, PuzzleSolver
from widgets import (
    CalibrationCanvas,
    ImagePanel,
    StatsBar,
    CalibrationStatusDisplay,
    init_theme,
    PALETTE,
    BUTTON_STYLES,
    CHECKBUTTON_STYLE,
)
from image_utils import image_cache, extract_piece_image

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
ICON_PNG_PATH = ASSETS_DIR / "octopuzzle_icon.png"
ICON_ICO_PATH = ASSETS_DIR / "octopuzzle_icon.ico"


class OctopuzzleApp(tk.Tk):
    """Main application window."""

    def __init__(self):
        super().__init__()

        init_theme(self)
        self.title("Octopuzzle")
        self.geometry("1200x820")
        self.minsize(1080, 760)

        self.configure(bg=PALETTE["background"])

        self.icon_image = None
        self._configure_icon()

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
        self.container = tk.Frame(self, bg=PALETTE["background"])
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

    def make_button(self, parent, text: str, command=None, variant: str = "accent"):
        """Factory for themed buttons."""
        style = BUTTON_STYLES.get(variant, BUTTON_STYLES["accent"])
        return ttk.Button(parent, text=text, command=command, style=style)

    def on_close(self):
        """Cleanup and close"""
        image_cache.cleanup()
        self.destroy()

    def _configure_icon(self):
        """Set custom window/taskbar icon when available."""
        try:
            if ICON_PNG_PATH.exists():
                self.icon_image = tk.PhotoImage(file=str(ICON_PNG_PATH))
                self.iconphoto(True, self.icon_image)
        except Exception as exc:
            print(f"[WARN] Unable to set PhotoImage icon: {exc}")

        try:
            if ICON_ICO_PATH.exists():
                self.iconbitmap(default=str(ICON_ICO_PATH))
        except Exception:
            # Some platforms (e.g., macOS/Linux) don't support iconbitmap with ICO files.
            pass


class Step1Frame(tk.Frame):
    """Step 1: Load and calibrate puzzle state image."""

    def __init__(self, parent, app):
        super().__init__(parent, bg=PALETTE["background"])
        self.app = app

        header = ttk.Label(self, text="Étape 1 · Zone à compléter", style="OctoTitle.TLabel")
        header.pack(pady=(20, 8))

        subheader = tk.Label(
            self,
            text="Chargez la photo du trou à combler, puis ajustez les paramètres si nécessaire.",
            bg=PALETTE["background"],
            fg=PALETTE["muted"],
            font=("Segoe UI", 11),
            wraplength=880,
        )
        subheader.pack(pady=(0, 18))

        content = tk.Frame(self, bg=PALETTE["background"])
        content.pack(fill=tk.BOTH, expand=True, padx=24, pady=(0, 20))

        controls = tk.Frame(
            content,
            bg=PALETTE["panel"],
            highlightbackground=PALETTE["border"],
            highlightthickness=1,
            width=330,
        )
        controls.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 16))
        controls.pack_propagate(False)

        tk.Label(
            controls,
            text="Calibration",
            font=("Segoe UI Semibold", 12),
            bg=PALETTE["panel"],
            fg=PALETTE["text"],
        ).pack(anchor=tk.W, padx=20, pady=(20, 8))

        self.btn_load = self.app.make_button(controls, "📷 Importer une image", self.load_image)
        self.btn_load.pack(fill=tk.X, padx=20, pady=(0, 12))

        self.debug_var = tk.BooleanVar()
        self.debug_toggle = ttk.Checkbutton(
            controls,
            text="Afficher la détection en direct",
            variable=self.debug_var,
            command=self.toggle_debug,
            style=CHECKBUTTON_STYLE,
        )
        self.debug_toggle.pack(anchor=tk.W, padx=20, pady=(0, 14))

        self.btn_select_roi = self.app.make_button(
            controls,
            "1. Définir la zone à remplir",
            self.select_roi,
            variant="secondary",
        )
        self.btn_select_roi.pack(fill=tk.X, padx=20, pady=4)
        self.btn_select_roi.state(["disabled"])

        self.btn_select_bg = self.app.make_button(
            controls,
            "2. Échantillonner le fond",
            self.select_background,
            variant="secondary",
        )
        self.btn_select_bg.pack(fill=tk.X, padx=20, pady=4)
        self.btn_select_bg.state(["disabled"])

        self.btn_preview = self.app.make_button(
            controls,
            "Prévisualiser la détection",
            self.preview_detection,
            variant="ghost",
        )
        self.btn_preview.pack(fill=tk.X, padx=20, pady=(10, 16))
        self.btn_preview.state(["disabled"])

        tk.Label(
            controls,
            text="Filtre de surface (px²)",
            font=("Segoe UI Semibold", 11),
            bg=PALETTE["panel"],
            fg=PALETTE["text"],
        ).pack(anchor=tk.W, padx=20, pady=(4, 2))

        area_frame = tk.Frame(controls, bg=PALETTE["panel"])
        area_frame.pack(fill=tk.X, padx=20)
        area_frame.columnconfigure(1, weight=1)

        tk.Label(area_frame, text="Min", bg=PALETTE["panel"], fg=PALETTE["muted"]).grid(
            row=0, column=0, sticky="w", pady=2
        )
        self.min_area_var = tk.IntVar(value=500)
        self.min_area_input = ttk.Spinbox(
            area_frame,
            from_=10,
            to=200000,
            increment=50,
            textvariable=self.min_area_var,
            width=10,
        )
        self.min_area_input.grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=2)

        tk.Label(area_frame, text="Max", bg=PALETTE["panel"], fg=PALETTE["muted"]).grid(
            row=1, column=0, sticky="w", pady=2
        )
        self.max_area_var = tk.IntVar(value=50000)
        self.max_area_input = ttk.Spinbox(
            area_frame,
            from_=100,
            to=500000,
            increment=100,
            textvariable=self.max_area_var,
            width=10,
        )
        self.max_area_input.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=(2, 8))

        self.status_display = CalibrationStatusDisplay(controls)
        self.status_display.pack(fill=tk.X, padx=18, pady=(12, 8))

        self.status_label = tk.Label(
            controls,
            text="Importez la photo du trou pour démarrer.",
            bg=PALETTE["panel"],
            fg=PALETTE["muted"],
            font=("Segoe UI", 10),
            wraplength=260,
            justify=tk.LEFT,
        )
        self.status_label.pack(fill=tk.X, padx=20, pady=(4, 18))

        self.btn_next = self.app.make_button(
            controls,
            "Étape suivante · Pièces disponibles →",
            self.next_step,
        )
        self.btn_next.pack(fill=tk.X, padx=20, pady=(0, 24))
        self.btn_next.state(["disabled"])

        canvas_frame = tk.Frame(content, bg=PALETTE["background"])
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = CalibrationCanvas(canvas_frame, width=820, height=640)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.on_roi_selected = self.on_roi_selected
        self.canvas.on_background_selected = self.on_background_selected

    def load_image(self):
        """Load puzzle state image."""
        path = filedialog.askopenfilename(
            title="Sélectionner la zone à compléter",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp")],
        )

        if not path:
            return

        img = cv2.imread(path)
        if img is None:
            messagebox.showerror("Octopuzzle", "Impossible de charger cette image.")
            return

        self.app.puzzle_image_path = path
        self.canvas.load_image(img)
        self.canvas.roi = None
        self.canvas.background_sample = None

        self.app.puzzle_calibration.roi = None
        self.app.puzzle_calibration.background_sample = None

        self.status_display.update_roi(None)
        self.status_display.update_background(None)
        self.status_label.config(
            text="Zone chargée. Sélectionnez la zone à remplir puis, si besoin, échantillonnez le fond."
        )

        self.btn_select_roi.state(["!disabled"])
        self.btn_select_bg.state(["!disabled"])
        self.btn_preview.state(["!disabled"])
        self.btn_next.state(["!disabled"])
        self.debug_var.set(False)
        self.canvas.set_mode("none")

    def select_roi(self):
        """Activate ROI selection mode."""
        if not self.app.puzzle_image_path:
            return
        self.canvas.set_mode("roi")
        self.status_label.config(text="Glissez sur l'image pour délimiter la zone à remplir.")

    def select_background(self):
        """Activate background selection mode."""
        if not self.app.puzzle_image_path:
            return
        self.canvas.set_mode("background")
        self.status_label.config(text="Glissez sur l'image pour échantillonner le fond.")

    def on_roi_selected(self, roi):
        """Handle ROI selection."""
        self.app.puzzle_calibration.roi = roi
        self.status_display.update_roi(roi)
        self.status_label.config(text=f"Zone définie : {roi[2]} × {roi[3]} px.")
        self.canvas.set_mode("none")
        self.check_ready()

    def on_background_selected(self, bg_color):
        """Handle background selection."""
        self.app.puzzle_calibration.background_sample = bg_color
        self.status_display.update_background(bg_color)
        r, g, b = int(bg_color[2]), int(bg_color[1]), int(bg_color[0])
        self.status_label.config(text=f"Fond échantillonné : RGB({r}, {g}, {b}).")
        self.canvas.set_mode("none")
        self.check_ready()

    def toggle_debug(self):
        """Toggle debug view."""
        if self.debug_var.get():
            self.preview_detection()
        else:
            if self.app.puzzle_image_path:
                img = cv2.imread(self.app.puzzle_image_path)
                if img is not None:
                    self.canvas.load_image(img)
                    if self.canvas.roi:
                        self.canvas.draw_roi_overlay()

    def preview_detection(self):
        """Preview piece detection with debug overlay."""
        if not self.app.puzzle_image_path:
            return

        self.app.puzzle_calibration.min_area = self.min_area_var.get()
        self.app.puzzle_calibration.max_area = self.max_area_var.get()

        detector = PuzzlePieceDetector(self.app.puzzle_calibration)
        pieces, debug_img = detector.detect_with_debug(self.app.puzzle_image_path)

        if debug_img is not None:
            self.canvas.show_debug_image(debug_img)
            self.status_label.config(text=f"{len(pieces)} pièces détectées dans la zone.")

    def check_ready(self):
        """Check if ready to proceed to next step."""
        if self.app.puzzle_image_path:
            self.btn_next.state(["!disabled"])
        else:
            self.btn_next.state(["disabled"])

    def next_step(self):
        """Load pieces and proceed to step 2."""
        if not self.app.puzzle_image_path:
            return

        self.app.puzzle_calibration.min_area = self.min_area_var.get()
        self.app.puzzle_calibration.max_area = self.max_area_var.get()

        detector = PuzzlePieceDetector(self.app.puzzle_calibration)
        self.app.puzzle_pieces = detector.detect_pieces(
            self.app.puzzle_image_path, "puzzle_state"
        )

        self.status_label.config(
            text=f"{len(self.app.puzzle_pieces)} morceaux identifiés dans le trou."
        )
        self.app.show_step(2)


class Step2Frame(tk.Frame):
    """Step 2: Load and calibrate available pieces images."""

    def __init__(self, parent, app):
        super().__init__(parent, bg=PALETTE["background"])
        self.app = app
        self.current_image_index = 0

        header = ttk.Label(self, text="Étape 2 · Pièces disponibles", style="OctoTitle.TLabel")
        header.pack(pady=(20, 8))

        subheader = tk.Label(
            self,
            text="Importez les photos des pièces restantes. Les réglages de calibration s'appliquent à toutes les images.",
            bg=PALETTE["background"],
            fg=PALETTE["muted"],
            font=("Segoe UI", 11),
            wraplength=880,
        )
        subheader.pack(pady=(0, 18))

        content = tk.Frame(self, bg=PALETTE["background"])
        content.pack(fill=tk.BOTH, expand=True, padx=24, pady=(0, 20))

        controls = tk.Frame(
            content,
            bg=PALETTE["panel"],
            highlightbackground=PALETTE["border"],
            highlightthickness=1,
            width=330,
        )
        controls.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 16))
        controls.pack_propagate(False)

        tk.Label(
            controls,
            text="Import des pièces",
            font=("Segoe UI Semibold", 12),
            bg=PALETTE["panel"],
            fg=PALETTE["text"],
        ).pack(anchor=tk.W, padx=20, pady=(20, 8))

        self.btn_load = self.app.make_button(
            controls,
            "📷 Importer des images (multi)",
            self.load_images,
        )
        self.btn_load.pack(fill=tk.X, padx=20, pady=(0, 12))

        selector_frame = tk.Frame(controls, bg=PALETTE["panel"])
        selector_frame.pack(fill=tk.X, padx=20, pady=(0, 16))

        tk.Label(
            selector_frame,
            text="Aperçu :",
            bg=PALETTE["panel"],
            fg=PALETTE["muted"],
        ).pack(anchor=tk.W)

        self.image_selector = ttk.Combobox(selector_frame, state="readonly")
        self.image_selector.pack(fill=tk.X, pady=(6, 0))
        self.image_selector.bind("<<ComboboxSelected>>", self.on_image_changed)

        tk.Label(
            controls,
            text="Calibration",
            font=("Segoe UI Semibold", 12),
            bg=PALETTE["panel"],
            fg=PALETTE["text"],
        ).pack(anchor=tk.W, padx=20, pady=(18, 8))

        self.debug_var = tk.BooleanVar()
        self.debug_toggle = ttk.Checkbutton(
            controls,
            text="Afficher la détection en direct",
            variable=self.debug_var,
            command=self.toggle_debug,
            style=CHECKBUTTON_STYLE,
        )
        self.debug_toggle.pack(anchor=tk.W, padx=20, pady=(0, 12))

        self.btn_select_roi = self.app.make_button(
            controls,
            "1. Définir une ROI commune",
            self.select_roi,
            variant="secondary",
        )
        self.btn_select_roi.pack(fill=tk.X, padx=20, pady=4)
        self.btn_select_roi.state(["disabled"])

        self.btn_select_bg = self.app.make_button(
            controls,
            "2. Échantillonner le fond",
            self.select_background,
            variant="secondary",
        )
        self.btn_select_bg.pack(fill=tk.X, padx=20, pady=4)
        self.btn_select_bg.state(["disabled"])

        self.btn_preview = self.app.make_button(
            controls,
            "Prévisualiser la détection",
            self.preview_detection,
            variant="ghost",
        )
        self.btn_preview.pack(fill=tk.X, padx=20, pady=(10, 16))
        self.btn_preview.state(["disabled"])

        tk.Label(
            controls,
            text="Filtre de surface (px²)",
            font=("Segoe UI Semibold", 11),
            bg=PALETTE["panel"],
            fg=PALETTE["text"],
        ).pack(anchor=tk.W, padx=20, pady=(4, 2))

        area_frame = tk.Frame(controls, bg=PALETTE["panel"])
        area_frame.pack(fill=tk.X, padx=20)
        area_frame.columnconfigure(1, weight=1)

        tk.Label(area_frame, text="Min", bg=PALETTE["panel"], fg=PALETTE["muted"]).grid(
            row=0, column=0, sticky="w", pady=2
        )
        self.min_area_var = tk.IntVar(value=500)
        self.min_area_input = ttk.Spinbox(
            area_frame,
            from_=10,
            to=200000,
            increment=50,
            textvariable=self.min_area_var,
            width=10,
        )
        self.min_area_input.grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=2)

        tk.Label(area_frame, text="Max", bg=PALETTE["panel"], fg=PALETTE["muted"]).grid(
            row=1, column=0, sticky="w", pady=2
        )
        self.max_area_var = tk.IntVar(value=50000)
        self.max_area_input = ttk.Spinbox(
            area_frame,
            from_=100,
            to=500000,
            increment=100,
            textvariable=self.max_area_var,
            width=10,
        )
        self.max_area_input.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=(2, 8))

        self.status_display = CalibrationStatusDisplay(controls)
        self.status_display.pack(fill=tk.X, padx=18, pady=(12, 8))

        self.status_label = tk.Label(
            controls,
            text="Importez les images des pièces pour commencer.",
            bg=PALETTE["panel"],
            fg=PALETTE["muted"],
            font=("Segoe UI", 10),
            wraplength=260,
            justify=tk.LEFT,
        )
        self.status_label.pack(fill=tk.X, padx=20, pady=(4, 30))

        canvas_frame = tk.Frame(content, bg=PALETTE["background"])
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = CalibrationCanvas(canvas_frame, width=820, height=640)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.on_roi_selected = self.on_roi_selected
        self.canvas.on_background_selected = self.on_background_selected

        nav = tk.Frame(self, bg=PALETTE["background"])
        nav.pack(fill=tk.X, pady=10, padx=24)

        back_btn = self.app.make_button(nav, "← Retour", lambda: self.app.show_step(1), variant="ghost")
        back_btn.pack(side=tk.LEFT)

        self.btn_next = self.app.make_button(
            nav,
            "Étape suivante · Suggestions →",
            self.next_step,
        )
        self.btn_next.pack(side=tk.RIGHT)
        self.btn_next.state(["disabled"])

    def load_images(self):
        """Load multiple available pieces images."""
        paths = filedialog.askopenfilenames(
            title="Sélectionner les images des pièces disponibles",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp")],
        )

        if not paths:
            return

        self.app.pieces_image_paths = list(paths)
        self.current_image_index = 0

        image_names = [f"Image {i+1}" for i in range(len(paths))]
        self.image_selector["values"] = image_names
        if image_names:
            self.image_selector.current(0)

        first_img = cv2.imread(paths[0])
        if first_img is None:
            messagebox.showerror("Octopuzzle", "Impossible de charger la première image.")
            return

        self.canvas.load_image(first_img)
        self.status_label.config(
            text=f"{len(paths)} images chargées. Ajustez la calibration si nécessaire."
        )

        self.canvas.roi = None
        self.canvas.background_sample = None
        self.app.pieces_calibration.roi = None
        self.app.pieces_calibration.background_sample = None

        self.btn_select_roi.state(["!disabled"])
        self.btn_select_bg.state(["!disabled"])
        self.btn_preview.state(["!disabled"])
        self.btn_next.state(["!disabled"])
        self.debug_var.set(False)

        self.status_display.update_roi(None)
        self.status_display.update_background(None)
        self.check_ready()

    def on_image_changed(self, event):
        """Handle image selection change."""
        self.current_image_index = self.image_selector.current()
        if 0 <= self.current_image_index < len(self.app.pieces_image_paths):
            path = self.app.pieces_image_paths[self.current_image_index]
            img = cv2.imread(path)
            if img is not None:
                if self.debug_var.get():
                    self.preview_detection()
                else:
                    self.canvas.load_image(img)
                    if self.canvas.roi:
                        self.canvas.draw_roi_overlay()

    def select_roi(self):
        """Activate ROI selection mode."""
        if not self.app.pieces_image_paths:
            return
        self.canvas.set_mode("roi")
        self.status_label.config(
            text="Glissez sur l'image pour définir la zone où chercher les pièces."
        )

    def select_background(self):
        """Activate background selection mode."""
        if not self.app.pieces_image_paths:
            return
        self.canvas.set_mode("background")
        self.status_label.config(
            text="Glissez sur l'image pour échantillonner la couleur du fond."
        )

    def on_roi_selected(self, roi):
        """Handle ROI selection."""
        self.app.pieces_calibration.roi = roi
        self.status_display.update_roi(roi)
        self.status_label.config(text=f"ROI commune définie : {roi[2]} × {roi[3]} px.")
        self.canvas.set_mode("none")
        self.check_ready()

    def on_background_selected(self, bg_color):
        """Handle background selection."""
        self.app.pieces_calibration.background_sample = bg_color
        self.status_display.update_background(bg_color)
        r, g, b = int(bg_color[2]), int(bg_color[1]), int(bg_color[0])
        self.status_label.config(text=f"Fond échantillonné : RGB({r}, {g}, {b}).")
        self.canvas.set_mode("none")
        self.check_ready()

    def toggle_debug(self):
        """Toggle debug view."""
        if self.debug_var.get():
            self.preview_detection()
        else:
            if self.app.pieces_image_paths and 0 <= self.current_image_index < len(
                self.app.pieces_image_paths
            ):
                img = cv2.imread(self.app.pieces_image_paths[self.current_image_index])
                if img is not None:
                    self.canvas.load_image(img)
                    if self.canvas.roi:
                        self.canvas.draw_roi_overlay()

    def preview_detection(self):
        """Preview piece detection with debug overlay."""
        if not self.app.pieces_image_paths or self.current_image_index >= len(
            self.app.pieces_image_paths
        ):
            return

        self.app.pieces_calibration.min_area = self.min_area_var.get()
        self.app.pieces_calibration.max_area = self.max_area_var.get()

        detector = PuzzlePieceDetector(self.app.pieces_calibration)
        current_path = self.app.pieces_image_paths[self.current_image_index]
        pieces, debug_img = detector.detect_with_debug(current_path)

        if debug_img is not None:
            self.canvas.show_debug_image(debug_img)
            self.status_label.config(
                text=f"{len(pieces)} pièces détectées dans l'image sélectionnée."
            )

    def check_ready(self):
        """Check if ready to proceed."""
        if self.app.pieces_image_paths:
            self.btn_next.state(["!disabled"])
        else:
            self.btn_next.state(["disabled"])

    def next_step(self):
        """Load all pieces and proceed to step 3."""
        if not self.app.pieces_image_paths:
            return

        self.app.pieces_calibration.min_area = self.min_area_var.get()
        self.app.pieces_calibration.max_area = self.max_area_var.get()

        detector = PuzzlePieceDetector(self.app.pieces_calibration)
        self.app.available_pieces = []

        for path in self.app.pieces_image_paths:
            pieces = detector.detect_pieces(path, "available")
            self.app.available_pieces.extend(pieces)

        total = len(self.app.puzzle_pieces) + len(self.app.available_pieces)
        self.status_label.config(
            text=f"{len(self.app.available_pieces)} pièces disponibles détectées (Total : {total})."
        )

        all_pieces = self.app.puzzle_pieces + self.app.available_pieces
        for idx, piece in enumerate(all_pieces):
            piece.id = idx

        self.app.solver = PuzzleSolver(all_pieces)

        if self.app.puzzle_pieces:
            self.app.solver.place_piece(self.app.puzzle_pieces[0].id, (0, 0))
        elif self.app.available_pieces:
            self.app.solver.place_piece(self.app.available_pieces[0].id, (0, 0))

        self.app.show_step(3)
        self.app.step3.load_next_suggestion()


class Step3Frame(tk.Frame):
    """Step 3: Solving interface."""

    def __init__(self, parent, app):
        super().__init__(parent, bg=PALETTE["background"])
        self.app = app

        header = ttk.Label(self, text="Étape 3 · Suggestions Octopuzzle", style="OctoTitle.TLabel")
        header.pack(pady=(20, 8))

        subheader = tk.Label(
            self,
            text="Octopuzzle propose les pièces les plus plausibles. Validez la bonne correspondance, rejetez-la ou passez à une autre suggestion.",
            bg=PALETTE["background"],
            fg=PALETTE["muted"],
            font=("Segoe UI", 11),
            wraplength=880,
        )
        subheader.pack(pady=(0, 18))

        self.stats_bar = StatsBar(self)
        self.stats_bar.pack(fill=tk.X, pady=(0, 20))

        panels = tk.Frame(self, bg=PALETTE["background"])
        panels.pack(fill=tk.BOTH, expand=True, padx=24, pady=(0, 16))

        self.ref_panel = ImagePanel(panels, title="🔴 Pièce de référence")
        self.ref_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)

        self.piece_panel = ImagePanel(panels, title="🟢 Proposition Octopuzzle")
        self.piece_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)

        controls = tk.Frame(self, bg=PALETTE["background"])
        controls.pack(pady=(0, 24))

        self.btn_accept = self.app.make_button(
            controls,
            "✓ C'est la bonne",
            lambda: self.handle_feedback(True),
            variant="accent",
        )
        self.btn_accept.pack(side=tk.LEFT, padx=10)

        self.btn_reject = self.app.make_button(
            controls,
            "✗ Mauvais raccord",
            lambda: self.handle_feedback(False),
            variant="danger",
        )
        self.btn_reject.pack(side=tk.LEFT, padx=10)

        self.btn_skip = self.app.make_button(
            controls,
            "⊘ Passer",
            self.load_next_suggestion,
            variant="secondary",
        )
        self.btn_skip.pack(side=tk.LEFT, padx=10)

    def load_next_suggestion(self):
        """Load next piece suggestion."""
        if not self.app.solver:
            return

        suggestion = self.app.solver.get_best_suggestion()

        if not suggestion:
            messagebox.showinfo("Octopuzzle", "Plus aucune suggestion n'est disponible.")
            return

        self.app.current_suggestion = suggestion

        ref_piece = suggestion["ref_piece"]
        ref_img = extract_piece_image(
            ref_piece.source_image, ref_piece.bbox_in_source, (255, 0, 0)
        )

        side_names = ["HAUT", "DROITE", "BAS", "GAUCHE"]
        side_name = side_names[suggestion["side"]]

        ref_info = (
            f"Pièce #{ref_piece.id}\n"
            f"Côté à compléter : {side_name}\n"
            f"Tabs: {ref_piece.tabs}"
        )
        self.ref_panel.set_image(ref_img, ref_info)

        piece = suggestion["piece"]
        piece_img = extract_piece_image(piece.source_image, piece.bbox_in_source, (0, 255, 0))

        piece_info = (
            f"Pièce #{piece.id}\n"
            f"Confiance : {suggestion['score']*100:.1f}%\n"
            f"Tabs: {piece.tabs}"
        )
        self.piece_panel.set_image(piece_img, piece_info)

        self.update_stats()

    def handle_feedback(self, fits: bool):
        """Handle user feedback on suggested match."""
        if not self.app.current_suggestion:
            return

        suggestion = self.app.current_suggestion
        piece = suggestion["piece"]
        ref_piece = suggestion["ref_piece"]
        side = suggestion["side"]

        if fits:
            self.app.solver.place_piece(piece.id, suggestion["position"])
        else:
            self.app.solver.reject_match(ref_piece.id, side, piece.id)

        self.load_next_suggestion()

    def update_stats(self):
        """Update statistics display."""
        if not self.app.solver:
            return

        placed = len(self.app.solver.used)
        total = len(self.app.solver.pieces)

        self.stats_bar.update_stats(placed, total)


def main():
    """Run the application"""
    app = OctopuzzleApp()
    app.mainloop()


if __name__ == "__main__":
    main()
