"""
Octopuzzle - Desktop assistant to help fill uniform puzzle areas.
Main application with the 3-step workflow (calibrate hole → calibrate pieces → solve).
"""

import argparse
import json
import logging
import os
import queue
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from models import (
    CalibrationData,
    HoleCalibration,
    PuzzlePiece,
    PuzzlePieceDetector,
    PuzzleSolver,
    HoleAnalyzer,
)
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
from image_utils import draw_roi_overlay, extract_piece_image, image_cache

logger = logging.getLogger("octopuzzle")
propagation_logger = logging.getLogger("octopuzzle.propagation")

ROOT_DIR = Path(__file__).resolve().parent
ASSETS_DIR = ROOT_DIR / "assets"
ICON_PNG_PATH = ASSETS_DIR / "octopuzzle_icon.png"
ICON_ICO_PATH = ASSETS_DIR / "octopuzzle_icon.ico"


def parse_roi(value: str) -> Tuple[int, int, int, int]:
    """Parse ROI string formatted as 'x,y,w,h'."""
    try:
        parts = [int(token.strip()) for token in value.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Les coordonnées doivent être fournies au format x,y,w,h."
        ) from exc

    if len(parts) != 4:
        raise argparse.ArgumentTypeError("Le format attendu est x,y,w,h (4 entiers).")

    x, y, w, h = parts
    if w <= 0 or h <= 0:
        raise argparse.ArgumentTypeError("La largeur et la hauteur doivent être positives.")
    return x, y, w, h


def _roi_to_list(roi: Optional[Tuple[int, int, int, int]]) -> Optional[List[int]]:
    return list(roi) if roi else None


def _tuple_from_sequence(sequence: Optional[List[int]]) -> Optional[Tuple[int, int, int, int]]:
    if not sequence:
        return None
    if len(sequence) != 4:
        return None
    return tuple(int(v) for v in sequence)


def _color_to_list(color: Optional[Tuple[int, int, int]]) -> Optional[List[int]]:
    if color is None:
        return None
    return [int(c) for c in color]


def _color_from_sequence(sequence: Optional[List[int]]) -> Optional[Tuple[int, int, int]]:
    if not sequence:
        return None
    if len(sequence) != 3:
        return None
    return tuple(int(c) for c in sequence)


def _serialise_path(path_value: Optional[Union[str, Path]]) -> Optional[str]:
    """Return a POSIX-style string for persistence, relative to the project when possible."""
    if not path_value:
        return None
    path_obj = Path(path_value)
    try:
        relative = path_obj.relative_to(ROOT_DIR)
        return relative.as_posix()
    except Exception:
        return path_obj.as_posix()


def _paths_equal(a: Union[str, Path], b: Union[str, Path]) -> bool:
    """Return True if two paths refer to the same location (best-effort, tolerant)."""
    try:
        path_a = Path(a).expanduser().resolve(strict=False)
        path_b = Path(b).expanduser().resolve(strict=False)
        return path_a == path_b
    except Exception:
        return str(a).replace("\\", "/") == str(b).replace("\\", "/")


def _candidate_paths(path_value: Union[str, Path]) -> List[Path]:
    """Generate plausible filesystem paths for a resource, handling Windows separators."""
    candidates: List[Path] = []
    seen: set[str] = set()

    if path_value is None:
        return candidates

    raw = Path(path_value)

    def add_candidate(candidate: Path) -> None:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            candidates.append(candidate)

    add_candidate(raw.expanduser())

    if isinstance(path_value, str):
        if "\\" in path_value:
            add_candidate(Path(path_value.replace("\\", "/")).expanduser())
        if "/" in path_value:
            add_candidate(Path(path_value.replace("/", os.sep)).expanduser())

    for base in (Path.cwd(), ROOT_DIR):
        if not raw.is_absolute():
            add_candidate(base / raw)
            if isinstance(path_value, str) and "\\" in path_value:
                add_candidate(base / Path(path_value.replace("\\", "/")))

    return candidates


def find_existing_path(path_value: Union[str, Path]) -> Optional[Path]:
    """Return the first candidate path that exists on disk."""
    for candidate in _candidate_paths(path_value):
        if candidate.exists():
            return candidate
    return None


class OctopuzzleApp(tk.Tk):
    """Main application window."""

    def __init__(self, args: Optional[argparse.Namespace] = None):
        super().__init__()

        self.cli_args = args or argparse.Namespace()
        self.save_session_path: Optional[Path] = getattr(self.cli_args, "save_session", None)

        init_theme(self)
        self.title("Octopuzzle")
        self.geometry("1200x820")
        self.minsize(1080, 760)

        self.configure(bg=PALETTE["background"])

        self.icon_image = None
        self._configure_icon()

        # State
        self.puzzle_calibration = HoleCalibration()
        self.pieces_calibration = CalibrationData()
        self.hole_analyzer = HoleAnalyzer()
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

        self.after(150, self._apply_startup_configuration)

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

    def _apply_startup_configuration(self):
        """Load session data or CLI overrides right after the UI is ready."""
        args = self.cli_args

        session_path = getattr(args, "load_session", None)
        if session_path:
            session_path = Path(session_path)
            if session_path.exists():
                try:
                    self.load_session(session_path)
                    logger.info("Session chargée depuis %s", session_path)
                except Exception as exc:
                    logger.exception("Échec du chargement de la session %s", session_path)
                    messagebox.showwarning(
                        "Octopuzzle",
                        f"Impossible de charger la session {session_path}.\n{exc}",
                    )
            else:
                logger.error("Fichier de session introuvable : %s", session_path)
                messagebox.showwarning(
                    "Octopuzzle",
                    f"Le fichier de session {session_path} est introuvable.",
                )

        # Apply CLI overrides after the session load so they can supersede saved values.
        try:
            self.step1.apply_cli_overrides(args)
        except Exception:
            logger.exception("Échec de l'application des options CLI pour l'étape 1.")

        try:
            self.step2.apply_cli_overrides(args)
        except Exception:
            logger.exception("Échec de l'application des options CLI pour l'étape 2.")

    def export_session(self) -> Dict[str, Any]:
        """Export the current calibration/session state to a serialisable dict."""
        return {
            "version": 1,
            "hole": self.step1.export_state(),
            "pieces": self.step2.export_state(),
        }

    def save_session(self, path: Path) -> None:
        """Persist the current session to the given path."""
        try:
            data = self.export_session()
            path = Path(path)
            if path.parent and not path.parent.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
            logger.info("Session sauvegardée dans %s", path)
        except Exception:
            logger.exception("Échec de la sauvegarde de la session %s", path)
            raise

    def load_session(self, path: Path) -> None:
        """Load a session from JSON and apply it to the UI."""
        path = Path(path)
        with path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)

        if not isinstance(payload, dict):
            raise ValueError("Format de session invalide (dict attendu).")

        version = int(payload.get("version", 1))
        if version != 1:
            raise ValueError(f"Version de session non supportée : {version}")

        hole_state = payload.get("hole")
        pieces_state = payload.get("pieces")

        self.show_step(1)
        self.step1.apply_state(hole_state)
        self.step2.apply_state(pieces_state)

    def make_button(self, parent, text: str, command=None, variant: str = "accent"):
        """Factory for themed buttons."""
        style = BUTTON_STYLES.get(variant, BUTTON_STYLES["accent"])
        return ttk.Button(parent, text=text, command=command, style=style)

    def on_close(self):
        """Cleanup and close"""
        try:
            self.step1.stop_auto_propagation()
        except Exception:
            pass
        if self.save_session_path:
            try:
                self.save_session(self.save_session_path)
            except Exception as exc:
                logger.exception("Impossible d'enregistrer la session %s", self.save_session_path)
                messagebox.showwarning(
                    "Octopuzzle",
                    f"Impossible d'enregistrer la session {self.save_session_path}.\n{exc}",
                )
        image_cache.cleanup()
        self.destroy()

    def _configure_icon(self):
        """Set custom window/taskbar icon when available."""
        icon_set = False

        if ICON_ICO_PATH.exists():
            try:
                self.iconbitmap(str(ICON_ICO_PATH))
                icon_set = True
            except Exception as exc:
                print(f"[WARN] Unable to set iconbitmap icon: {exc}")

        if ICON_PNG_PATH.exists():
            try:
                self.icon_image = tk.PhotoImage(file=str(ICON_PNG_PATH))
                self.tk.call("wm", "iconphoto", self._w, self.icon_image)
                icon_set = True
            except Exception as exc:
                print(f"[WARN] Unable to set PhotoImage icon: {exc}")

        if not icon_set:
            print("[INFO] Octopuzzle icon not applied (assets missing or unsupported platform).")


class Step1Frame(tk.Frame):
    """Step 1: Load and analyse the puzzle hole."""

    DEBUG_LAYERS_ORDER = [
        "Masque (overlay)",
        "Carte des états",
        "Contours Canny (propagation)",
        "Zone externe floutée",
    ]

    AUTO_PIXELS_PER_FRAME = 20000
    AUTO_CHUNK_SIZE = 1024

    def __init__(self, parent, app):
        super().__init__(parent, bg=PALETTE["background"])
        self.app = app

        self.base_image = None
        self.analysis = {}
        self.analysis_display = None
        self.param_update_after = None
        self.last_frame_time = time.perf_counter()
        self.auto_pixels_budget = float(self.AUTO_PIXELS_PER_FRAME)
        self.auto_chunk_size = float(self.AUTO_CHUNK_SIZE)
        self._suspend_param_updates = 0
        self.last_render_time = 0.0
        self.force_render = True

        header_frame = tk.Frame(self, bg=PALETTE["background"])
        header_frame.pack(fill=tk.X, pady=(20, 8), padx=24)

        ttk.Label(header_frame, text="Étape 1 · Zone à compléter", style="OctoTitle.TLabel").pack(
            side=tk.LEFT
        )

        debug_frame = tk.Frame(header_frame, bg=PALETTE["background"])
        debug_frame.pack(side=tk.RIGHT)
        self.debug_enabled = tk.BooleanVar(value=True)
        try:
            self.app.hole_analyzer.set_debug(True)
        except Exception:
            propagation_logger.exception("Impossible d'activer le mode debug par défaut.")
        self.debug_toggle = ttk.Checkbutton(
            debug_frame,
            text="Mode debug",
            variable=self.debug_enabled,
            command=self.on_debug_toggle,
            style=CHECKBUTTON_STYLE,
        )
        self.debug_toggle.pack(side=tk.LEFT, padx=(0, 8))

        self.debug_options_frame = tk.Frame(debug_frame, bg=PALETTE["background"])
        self.debug_state_var = tk.BooleanVar(value=True)
        self.debug_canny_var = tk.BooleanVar(value=True)
        self.debug_blur_var = tk.BooleanVar(value=False)
        self.debug_state_cb = ttk.Checkbutton(
            self.debug_options_frame,
            text="État",
            variable=self.debug_state_var,
            command=self._on_debug_option_changed,
            style=CHECKBUTTON_STYLE,
        )
        self.debug_canny_cb = ttk.Checkbutton(
            self.debug_options_frame,
            text="Contours",
            variable=self.debug_canny_var,
            command=self._on_debug_option_changed,
            style=CHECKBUTTON_STYLE,
        )
        self.debug_blur_cb = ttk.Checkbutton(
            self.debug_options_frame,
            text="Flou",
            variable=self.debug_blur_var,
            command=self._on_debug_option_changed,
            style=CHECKBUTTON_STYLE,
        )
        for cb in (self.debug_state_cb, self.debug_canny_cb, self.debug_blur_cb):
            cb.pack(side=tk.LEFT, padx=2)

        self.fps_label = tk.Label(
            debug_frame,
            text="FPS : idle",
            bg=PALETTE["background"],
            fg=PALETTE["muted"],
            font=("Segoe UI", 10),
        )
        self.fps_label.pack(side=tk.LEFT, padx=(0, 8))

        self.debug_layer_var = tk.StringVar(value=self.DEBUG_LAYERS_ORDER[0])
        self.debug_layer_combo = ttk.Combobox(
            debug_frame,
            textvariable=self.debug_layer_var,
            state="readonly",
            width=22,
        )
        self.debug_layer_combo.bind("<<ComboboxSelected>>", lambda _evt: self.render_display())

        self._schedule_fps_idle()

        subheader = tk.Label(
            self,
            text=(
                "Importez la photo du trou à combler. Sélectionnez ensuite la bordure complète et "
                "une zone intérieure homogène pour permettre au détecteur de reconstituer la grille manquante."
            ),
            bg=PALETTE["background"],
            fg=PALETTE["muted"],
            font=("Segoe UI", 11),
            wraplength=900,
            justify=tk.LEFT,
        )
        subheader.pack(pady=(0, 18), padx=24)

        content = tk.Frame(self, bg=PALETTE["background"])
        content.pack(fill=tk.BOTH, expand=True, padx=24, pady=(0, 20))

        controls_container = tk.Frame(
            content,
            bg=PALETTE["panel"],
            highlightbackground=PALETTE["border"],
            highlightthickness=1,
            width=340,
        )
        controls_container.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 16))
        controls_container.pack_propagate(False)

        self.controls_canvas = tk.Canvas(
            controls_container,
            bg=PALETTE["panel"],
            highlightthickness=0,
            bd=0,
        )
        self.controls_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        controls_scrollbar = ttk.Scrollbar(
            controls_container,
            orient=tk.VERTICAL,
            command=self.controls_canvas.yview,
        )
        controls_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.controls_canvas.configure(yscrollcommand=controls_scrollbar.set)

        self.controls_inner = tk.Frame(self.controls_canvas, bg=PALETTE["panel"])
        self.controls_window = self.controls_canvas.create_window(
            (0, 0), window=self.controls_inner, anchor="nw"
        )

        self.controls_inner.bind(
            "<Configure>",
            lambda e: self.controls_canvas.configure(scrollregion=self.controls_canvas.bbox("all")),
        )
        self.controls_canvas.bind(
            "<Configure>",
            lambda e: self.controls_canvas.itemconfigure(self.controls_window, width=e.width),
        )

        self.controls_inner.bind("<Enter>", self._enable_controls_scroll)
        self.controls_inner.bind("<Leave>", self._disable_controls_scroll)

        controls = self.controls_inner
        try:
            self.app.hole_analyzer.set_debug(self.debug_enabled.get())
        except Exception:
            pass
        self.update_debug_controls()

        tk.Label(
            controls,
            text="Calibration",
            font=("Segoe UI Semibold", 12),
            bg=PALETTE["panel"],
            fg=PALETTE["text"],
        ).pack(anchor=tk.W, padx=20, pady=(20, 8))

        self.btn_load = self.app.make_button(controls, "📷 Importer une image", self.load_image)
        self.btn_load.pack(fill=tk.X, padx=20, pady=(0, 12))

        self.btn_select_outer = self.app.make_button(
            controls,
            "1. Définir la bordure du trou",
            lambda: self.activate_mode("outer"),
            variant="secondary",
        )
        self.btn_select_outer.pack(fill=tk.X, padx=20, pady=4)
        self.btn_select_outer.state(["disabled"])

        self.btn_select_inner = self.app.make_button(
            controls,
            "2. Définir la zone interne",
            lambda: self.activate_mode("inner"),
            variant="secondary",
        )
        self.btn_select_inner.pack(fill=tk.X, padx=20, pady=4)
        self.btn_select_inner.state(["disabled"])

        self.btn_refresh = self.app.make_button(
            controls,
            "Recalculer l'analyse",
            self.run_analysis,
            variant="ghost",
        )
        self.btn_refresh.pack(fill=tk.X, padx=20, pady=(6, 10))
        self.btn_refresh.state(["disabled"])

        blur_frame = tk.Frame(controls, bg=PALETTE["panel"])
        blur_frame.pack(fill=tk.X, padx=20, pady=(0, 12))
        tk.Label(
            blur_frame,
            text="Flou (taille du kernel)",
            font=("Segoe UI Semibold", 11),
            bg=PALETTE["panel"],
            fg=PALETTE["text"],
        ).pack(anchor=tk.W, pady=(0, 4))
        self.blur_kernel_var = tk.IntVar(value=5)
        self.blur_kernel_input = ttk.Spinbox(
            blur_frame,
            from_=1,
            to=51,
            increment=2,
            textvariable=self.blur_kernel_var,
            width=8,
        )
        self.blur_kernel_input.pack(anchor=tk.W)

        edges_frame = tk.Frame(controls, bg=PALETTE["panel"])
        edges_frame.pack(fill=tk.X, padx=20, pady=(0, 12))
        tk.Label(
            edges_frame,
            text="Seuils Canny (bord)",
            font=("Segoe UI Semibold", 11),
            bg=PALETTE["panel"],
            fg=PALETTE["text"],
        ).pack(anchor=tk.W, pady=(0, 4))

        thresholds_row = tk.Frame(edges_frame, bg=PALETTE["panel"])
        thresholds_row.pack(fill=tk.X)

        tk.Label(
            thresholds_row,
            text="Bas",
            bg=PALETTE["panel"],
            fg=PALETTE["muted"],
        ).pack(side=tk.LEFT)

        self.canny_low_var = tk.IntVar(value=45)
        low_spin = ttk.Spinbox(
            thresholds_row,
            from_=0,
            to=500,
            increment=5,
            textvariable=self.canny_low_var,
            width=6,
        )
        low_spin.pack(side=tk.LEFT, padx=(8, 16))

        tk.Label(
            thresholds_row,
            text="Haut",
            bg=PALETTE["panel"],
            fg=PALETTE["muted"],
        ).pack(side=tk.LEFT)

        self.canny_high_var = tk.IntVar(value=110)
        high_spin = ttk.Spinbox(
            thresholds_row,
            from_=1,
            to=600,
            increment=5,
            textvariable=self.canny_high_var,
            width=6,
        )
        high_spin.pack(side=tk.LEFT, padx=(8, 0))
        self.blur_kernel_var.trace_add("write", self.on_parameter_changed)
        self.canny_low_var.trace_add("write", self.on_parameter_changed)
        self.canny_high_var.trace_add("write", self.on_parameter_changed)

        gap_frame = tk.Frame(controls, bg=PALETTE["panel"])
        gap_frame.pack(fill=tk.X, padx=20, pady=(0, 12))
        tk.Label(
            gap_frame,
            text="Passage minimal (px)",
            font=("Segoe UI Semibold", 11),
            bg=PALETTE["panel"],
            fg=PALETTE["text"],
        ).pack(anchor=tk.W, pady=(0, 4))
        self.min_gap_var = tk.IntVar(value=5)
        self.min_gap_input = ttk.Spinbox(
            gap_frame,
            from_=1,
            to=50,
            increment=1,
            textvariable=self.min_gap_var,
            width=6,
        )
        self.min_gap_input.pack(anchor=tk.W)
        self.min_gap_var.trace_add("write", self.on_parameter_changed)

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

        propagation_frame = tk.Frame(controls, bg=PALETTE["panel"])
        propagation_frame.pack(fill=tk.X, padx=20, pady=(6, 8))

        self.propagation_status_var = tk.StringVar(value="Propagation : en attente")
        self.propagation_status_label = tk.Label(
            propagation_frame,
            textvariable=self.propagation_status_var,
            bg=PALETTE["panel"],
            fg=PALETTE["accent"],
            font=("Segoe UI Semibold", 11),
            anchor="w",
        )
        self.propagation_status_label.pack(fill=tk.X, pady=(0, 6))

        self.btn_start_propagation = self.app.make_button(
            propagation_frame,
            "▶ Lancer la propagation",
            self.on_start_propagation_clicked,
            variant="accent",
        )
        self.btn_start_propagation.pack(fill=tk.X, pady=(0, 6))
        self.btn_start_propagation.state(["disabled"])

        self.step_mode_var = tk.BooleanVar(value=False)
        self.step_mode_toggle = ttk.Checkbutton(
            propagation_frame,
            text="Mode pas à pas",
            variable=self.step_mode_var,
            command=self.on_step_mode_toggle,
            style=CHECKBUTTON_STYLE,
        )
        self.step_mode_toggle.pack(anchor=tk.W)

        step_buttons = tk.Frame(propagation_frame, bg=PALETTE["panel"])
        step_buttons.pack(fill=tk.X, pady=(6, 0))

        self.btn_step_pixel = self.app.make_button(
            step_buttons,
            "▶ 1 pixel",
            self.step_one_pixel,
            variant="ghost",
        )
        self.btn_step_pixel.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 6))
        self.btn_step_pixel.state(["disabled"])

        self.btn_step_loop = self.app.make_button(
            step_buttons,
            "⟳ 1 boucle",
            self.step_one_loop,
            variant="ghost",
        )
        self.btn_step_loop.pack(side=tk.LEFT, expand=True, fill=tk.X)
        self.btn_step_loop.state(["disabled"])

        self.summary_label = tk.Label(
            controls,
            text="Analyse en attente.",
            bg=PALETTE["panel"],
            fg=PALETTE["muted"],
            font=("Segoe UI", 10),
            wraplength=260,
            justify=tk.LEFT,
        )
        self.summary_label.pack(fill=tk.X, padx=20, pady=(4, 8))

        self.grid_label = tk.Label(
            controls,
            text="",
            bg=PALETTE["panel"],
            fg=PALETTE["muted"],
            font=("Segoe UI", 10),
            wraplength=260,
            justify=tk.LEFT,
        )
        self.grid_label.pack(fill=tk.X, padx=20, pady=(0, 16))

        self.pieces_label = tk.Label(
            controls,
            text="Pièces détectées : —",
            bg=PALETTE["panel"],
            fg=PALETTE["muted"],
            font=("Segoe UI", 10),
            anchor="w",
            wraplength=260,
            justify=tk.LEFT,
        )
        self.pieces_label.pack(fill=tk.X, padx=20, pady=(0, 12))

        self.detected_pieces = None

        self.btn_import_calib = self.app.make_button(
            controls,
            "📂 Charger une calibration…",
            self.import_calibration,
            variant="secondary",
        )
        self.btn_import_calib.pack(fill=tk.X, padx=20, pady=(2, 4))

        self.btn_export_calib = self.app.make_button(
            controls,
            "💾 Sauvegarder la calibration…",
            self.export_calibration,
            variant="secondary",
        )
        self.btn_export_calib.pack(fill=tk.X, padx=20, pady=(0, 12))

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
        self.canvas.on_outer_selected = self.on_outer_selected
        self.canvas.on_inner_selected = self.on_inner_selected

        self.propagation_state = "idle"
        self.propagation_needs_restart = False
        self.last_propagation_stats: Optional[Dict[str, int]] = None

        self.auto_running = False
        self.worker_thread = None
        self.worker_queue = None
        self.worker_stop_event = None
        self.worker_poll_after = None

        self.update_debug_controls()
        self.update_propagation_controls()

    def _on_controls_mousewheel(self, event):
        if event.delta:
            delta = -int(event.delta / 120)
            self.controls_canvas.yview_scroll(delta, "units")
        elif event.num == 4:
            self.controls_canvas.yview_scroll(-3, "units")
        elif event.num == 5:
            self.controls_canvas.yview_scroll(3, "units")
        return "break"

    def _enable_controls_scroll(self, _event):
        self.controls_canvas.bind_all("<MouseWheel>", self._on_controls_mousewheel)
        self.controls_canvas.bind_all("<Button-4>", self._on_controls_mousewheel)
        self.controls_canvas.bind_all("<Button-5>", self._on_controls_mousewheel)

    def _disable_controls_scroll(self, _event):
        self.controls_canvas.unbind_all("<MouseWheel>")
        self.controls_canvas.unbind_all("<Button-4>")
        self.controls_canvas.unbind_all("<Button-5>")

    def activate_mode(self, mode: str):
        if self.base_image is None:
            return
        self.canvas.set_mode(mode)
        if mode == "outer":
            self.summary_label.config(text="Glissez pour englober tout le trou (bord compris).")
        elif mode == "inner":
            self.summary_label.config(text="Glissez pour sélectionner une zone interne sans bord.")

    def load_image(self):
        path = filedialog.askopenfilename(
            title="Sélectionner la zone à compléter",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp")],
        )
        if not path:
            return
        self.load_image_from_path(path, silent=False)

    def load_image_from_path(self, path: Union[str, Path], *, silent: bool = False) -> bool:
        if not path:
            return False

        source_str = str(path)
        resolved_path = None
        img = None

        for candidate in _candidate_paths(path):
            img = cv2.imread(str(candidate))
            if img is not None:
                resolved_path = str(candidate)
                break

        if img is None or resolved_path is None:
            logger.error("Impossible de charger l'image du trou %s", source_str)
            if not silent:
                messagebox.showerror("Octopuzzle", "Impossible de charger cette image.")
            return False

        if resolved_path != source_str:
            logger.debug("Image du trou résolue : %s → %s", source_str, resolved_path)

        self._apply_loaded_image(resolved_path, img)
        return True

    def _apply_loaded_image(self, path: str, img) -> None:
        self.stop_auto_propagation()
        if self.param_update_after is not None:
            try:
                self.after_cancel(self.param_update_after)
            except Exception:
                pass
            self.param_update_after = None

        self.app.puzzle_image_path = path
        self.base_image = img
        self.canvas.load_image(img)
        self.canvas.outer_roi = None
        self.canvas.inner_roi = None
        self.canvas.background_sample = None
        self.canvas.set_mode("none")

        calib = self.app.puzzle_calibration
        calib.outer_roi = None
        calib.inner_roi = None
        calib.background_sample = None

        self.status_display.update_outer_roi(None)
        self.status_display.update_inner_roi(None)
        self.status_display.update_background(None)

        self.summary_label.config(text="Sélectionnez d'abord la bordure complète du trou.")
        self.grid_label.config(text="")
        self.pieces_label.config(text="Pièces détectées : —", fg=PALETTE["muted"])
        self.detected_pieces = None
        self.analysis = {}
        self.analysis_display = None
        self.debug_enabled.set(True)
        try:
            self.app.hole_analyzer.set_debug(True)
        except Exception:
            propagation_logger.exception("Impossible de réactiver le mode debug après chargement.")
        self.app.hole_analyzer.reset()
        self.update_debug_controls()
        self.update_step_controls()
        self.last_frame_time = None
        self.propagation_needs_restart = False
        self.last_propagation_stats = None
        self.update_propagation_controls()

        self.btn_select_outer.state(["!disabled"])
        self.btn_select_inner.state(["disabled"])
        self.btn_refresh.state(["disabled"])
        self.btn_next.state(["disabled"])

    def import_calibration(self):
        """Load a previously saved session via file dialog."""
        path = filedialog.askopenfilename(
            title="Charger une calibration Octopuzzle",
            filetypes=[("Session Octopuzzle", "*.json"), ("Tous les fichiers", "*.*")],
        )
        if not path:
            return
        try:
            self.app.load_session(Path(path))
        except Exception as exc:
            logger.exception("Échec du chargement de la calibration %s", path)
            messagebox.showerror(
                "Octopuzzle",
                f"Impossible de charger la calibration sélectionnée.\n{exc}",
            )

    def export_calibration(self):
        """Save the current session via a file dialog."""
        path = filedialog.asksaveasfilename(
            title="Sauvegarder la calibration Octopuzzle",
            defaultextension=".json",
            filetypes=[("Session Octopuzzle", "*.json"), ("Tous les fichiers", "*.*")],
        )
        if not path:
            return
        try:
            self.app.save_session(Path(path))
        except Exception as exc:
            logger.exception("Échec de la sauvegarde de la calibration %s", path)
            messagebox.showerror(
                "Octopuzzle",
                f"Impossible d'enregistrer la calibration.\n{exc}",
            )

    def export_state(self) -> Dict[str, Any]:
        """Return the calibration state for persistence."""
        return {
            "image_path": _serialise_path(self.app.puzzle_image_path),
            "outer_roi": _roi_to_list(self.app.puzzle_calibration.outer_roi),
            "inner_roi": _roi_to_list(self.app.puzzle_calibration.inner_roi),
            "blur_kernel": int(self.blur_kernel_var.get()),
            "canny_low": int(self.canny_low_var.get()),
            "canny_high": int(self.canny_high_var.get()),
            "min_area": int(self.min_area_var.get()),
            "max_area": int(self.max_area_var.get()),
            "min_gap": int(self.min_gap_var.get()),
        }

    def apply_state(self, state: Optional[Dict[str, Any]]) -> None:
        """Restore calibration state from persisted data."""
        if not state:
            return

        image_path = state.get("image_path")
        if image_path:
            if not self.load_image_from_path(image_path, silent=True):
                logger.warning("Impossible de recharger l'image du trou %s", image_path)

        if "blur_kernel" in state:
            self._set_var_safely(self.blur_kernel_var, int(state["blur_kernel"]))
        if "canny_low" in state:
            self._set_var_safely(self.canny_low_var, int(state["canny_low"]))
        if "canny_high" in state:
            self._set_var_safely(self.canny_high_var, int(state["canny_high"]))
        if "min_area" in state:
            self._set_var_safely(self.min_area_var, int(state["min_area"]))
        if "max_area" in state:
            self._set_var_safely(self.max_area_var, int(state["max_area"]))
        if "min_gap" in state:
            self._set_var_safely(self.min_gap_var, int(state["min_gap"]))

        if self.base_image is None:
            # Without image there is nothing else to restore.
            return

        outer_roi = _tuple_from_sequence(state.get("outer_roi"))
        inner_roi = _tuple_from_sequence(state.get("inner_roi"))

        if outer_roi:
            self.canvas.outer_roi = outer_roi
            self.on_outer_selected(outer_roi)

        if inner_roi:
            self.canvas.inner_roi = inner_roi
            self.on_inner_selected(inner_roi)

    def apply_cli_overrides(self, args: argparse.Namespace) -> None:
        """Apply command-line overrides when launching the app."""
        hole_image = getattr(args, "hole_image", None)
        if hole_image:
            resolved = find_existing_path(hole_image) or Path(hole_image)
            already_loaded = (
                self.app.puzzle_image_path is not None
                and resolved is not None
                and _paths_equal(self.app.puzzle_image_path, resolved)
            )
            if self.base_image is None and resolved is not None:
                self.load_image_from_path(resolved, silent=True)
                logger.info("Image du trou chargée depuis la CLI : %s", resolved)
            elif not already_loaded and resolved is not None:
                self.load_image_from_path(resolved, silent=True)
                logger.info("Image du trou rechargée depuis la CLI : %s", resolved)

        if getattr(args, "blur_kernel", None) is not None:
            self._set_var_safely(self.blur_kernel_var, int(args.blur_kernel))
        if getattr(args, "canny_low", None) is not None:
            self._set_var_safely(self.canny_low_var, int(args.canny_low))
        if getattr(args, "canny_high", None) is not None:
            self._set_var_safely(self.canny_high_var, int(args.canny_high))
        if getattr(args, "min_area", None) is not None:
            self._set_var_safely(self.min_area_var, int(args.min_area))
        if getattr(args, "max_area", None) is not None:
            self._set_var_safely(self.max_area_var, int(args.max_area))
        if getattr(args, "min_gap", None) is not None:
            self._set_var_safely(self.min_gap_var, int(args.min_gap))

        if self.base_image is None:
            outer_roi = getattr(args, "outer_roi", None)
            inner_roi = getattr(args, "inner_roi", None)
            if outer_roi or inner_roi:
                logger.warning(
                    "Options --outer-roi / --inner-roi ignorées : aucune image n'est chargée."
                )
            return

        outer_roi = getattr(args, "outer_roi", None)
        if outer_roi:
            self.canvas.outer_roi = outer_roi
            self.on_outer_selected(outer_roi)

        inner_roi = getattr(args, "inner_roi", None)
        if inner_roi:
            self.canvas.inner_roi = inner_roi
            self.on_inner_selected(inner_roi)

    def on_outer_selected(self, roi):
        self.app.puzzle_calibration.outer_roi = roi
        self.status_display.update_outer_roi(roi)
        self.summary_label.config(text="Bordure détectée. Sélectionnez maintenant la zone interne.")
        self.btn_select_inner.state(["!disabled"])
        self.btn_refresh.state(["!disabled"])
        self.canvas.set_mode("none")
        self.force_render = True
        propagation_logger.info("ROI externe définie : %s", roi)
        self.run_analysis()

    def on_inner_selected(self, roi):
        self.app.puzzle_calibration.inner_roi = roi
        self.status_display.update_inner_roi(roi)
        self.summary_label.config(text="Zone interne définie. Analyse en cours...")
        self.canvas.set_mode("none")
        self.force_render = True
        propagation_logger.info("ROI interne définie : %s", roi)
        self.run_analysis()

    def on_background_selected(self, bg_color):
        # Background sampling is now derived automatically from the zone interne.
        pass

    def on_debug_toggle(self):
        try:
            self.app.hole_analyzer.set_debug(self.debug_enabled.get())
        except Exception:
            propagation_logger.exception("Impossible de basculer le mode debug.")
        self.update_debug_controls()
        self.force_render = True
        current = self.app.hole_analyzer.get_result()
        if current:
            self.apply_analysis_result(current)
        else:
            self.render_display()

    def _on_debug_option_changed(self):
        self.force_render = True
        self.render_display()

    def _set_var_safely(self, var: tk.Variable, value: int) -> None:
        """Assign a tkinter variable without triggering parameter recomputation."""
        self._suspend_param_updates += 1
        try:
            var.set(value)
        finally:
            self._suspend_param_updates = max(0, self._suspend_param_updates - 1)

    def _schedule_fps_idle(self):
        self.after(500, self._fps_idle_tick)

    def _fps_idle_tick(self):
        if not self.winfo_exists():
            return
        if self.last_frame_time is None:
            self.fps_label.config(text="FPS : idle")
        else:
            idle_dt = time.perf_counter() - self.last_frame_time
            if idle_dt > 0.8:
                self.fps_label.config(text="FPS : idle")
                if propagation_logger.isEnabledFor(logging.DEBUG):
                    propagation_logger.debug("Propagation idle détectée (%.3fs sans frame).", idle_dt)
        self._schedule_fps_idle()

    def update_debug_controls(self):
        if self.debug_enabled.get():
            if not self.debug_options_frame.winfo_ismapped():
                self.debug_options_frame.pack(side=tk.LEFT)
            for cb in (self.debug_state_cb, self.debug_canny_cb, self.debug_blur_cb):
                if not cb.winfo_ismapped():
                    cb.pack(side=tk.LEFT, padx=2)
        else:
            for cb in (self.debug_state_cb, self.debug_canny_cb, self.debug_blur_cb):
                if cb.winfo_ismapped():
                    cb.pack_forget()
            if self.debug_options_frame.winfo_ismapped():
                self.debug_options_frame.pack_forget()

    def get_blur_kernel(self) -> int:
        """Return a valid odd kernel size."""
        try:
            value = int(self.blur_kernel_var.get())
        except Exception:
            value = 5
            self._set_var_safely(self.blur_kernel_var, value)
        value = max(1, value)
        if value % 2 == 0:
            value = value + 1 if value < 51 else value - 1
            self._set_var_safely(self.blur_kernel_var, value)
        return value

    def get_canny_thresholds(self) -> Tuple[int, int]:
        """Return sanitised Canny thresholds (low, high)."""
        try:
            low = int(self.canny_low_var.get())
        except Exception:
            low = 45
            self._set_var_safely(self.canny_low_var, low)
        try:
            high = int(self.canny_high_var.get())
        except Exception:
            high = 110
            self._set_var_safely(self.canny_high_var, high)

        low = max(0, low)
        high = max(low + 1, high)

        self._set_var_safely(self.canny_low_var, low)
        self._set_var_safely(self.canny_high_var, high)
        return low, high

    def get_min_gap(self) -> int:
        """Return the minimum passage width (pixels)."""
        try:
            gap = int(self.min_gap_var.get())
        except Exception:
            gap = 5
            self._set_var_safely(self.min_gap_var, gap)
        gap = max(1, gap)
        self._set_var_safely(self.min_gap_var, gap)
        return gap

    def on_parameter_changed(self, *_args):
        """Debounced hook to recompute the propagation when parameters change."""
        if self._suspend_param_updates:
            return
        if self.param_update_after is not None:
            try:
                self.after_cancel(self.param_update_after)
            except Exception:
                pass
            self.param_update_after = None

        if self.base_image is None:
            return
        if not (
            self.app.puzzle_calibration.outer_roi
            and self.app.puzzle_calibration.inner_roi
        ):
            return

        self.param_update_after = self.after(200, self._apply_parameter_update)

    def _apply_parameter_update(self):
        self.param_update_after = None
        self.run_analysis()

    def on_step_mode_toggle(self):
        """Handle toggling of the step-by-step mode."""
        if self.step_mode_var.get():
            self.stop_auto_propagation()
            self.update_step_controls()
            self.update_propagation_controls()
            return

        # Back to auto mode → just refresh control states.
        self.update_step_controls()
        self.update_propagation_controls()

    def update_step_controls(self):
        """Enable or disable stepping buttons."""
        if (
            self.step_mode_var.get()
            and self.analysis
            and self.analysis.get("status") == "ok"
            and not self.analysis.get("complete", False)
        ):
            self.btn_step_pixel.state(["!disabled"])
            self.btn_step_loop.state(["!disabled"])
        else:
            self.btn_step_pixel.state(["disabled"])
            self.btn_step_loop.state(["disabled"])

    def on_start_propagation_clicked(self):
        """Start propagation when the user requests it explicitly."""
        if self.auto_running:
            return
        if not self.analysis or self.analysis.get("status") != "ok":
            return
        if self.analysis.get("complete", False):
            return

        self.propagation_needs_restart = False
        self.start_auto_propagation()

    def _capture_last_propagation_stats(self):
        """Snapshot key metrics from the current analysis before it becomes stale."""
        current = self.analysis or {}
        if current.get("status") != "ok":
            return

        processed = int(current.get("processed_pixels", 0) or 0)
        complete = bool(current.get("complete", False))
        if processed <= 0 and not complete:
            return

        self.last_propagation_stats = {
            "loops": int(current.get("loops_completed", 0) or 0),
            "processed": processed,
            "frozen": int(current.get("frozen_count", 0) or 0),
            "active": int(current.get("active_count", 0) or 0),
            "frontier": int(current.get("frontier_count", 0) or 0),
        }

    def update_propagation_controls(self):
        """Refresh status indicators and start button availability."""
        state = "idle"
        analysis_data = self.analysis if isinstance(self.analysis, dict) else {}
        analysis_ready = analysis_data.get("status") == "ok"
        analysis_complete = bool(analysis_data.get("complete", False)) if analysis_ready else False

        if self.auto_running:
            state = "running"
        elif not analysis_ready:
            state = "idle"
        elif analysis_complete:
            state = "complete"
        elif self.propagation_needs_restart:
            state = "stale"
        else:
            state = "ready"

        self.propagation_state = state

        stats_text = ""
        stats = self.last_propagation_stats or {}
        if state == "stale" and stats:
            stats_text = (
                f"\nDernier run · boucles : {stats.get('loops', 0)} · "
                f"figés : {stats.get('frozen', 0)} · pixels : {stats.get('processed', 0)}"
            )

        status_messages = {
            "idle": "Propagation : en attente",
            "ready": "Propagation : prête à démarrer",
            "stale": "Propagation : périmée (réglages modifiés)",
            "running": "Propagation : en cours",
            "complete": "Propagation : terminée",
        }
        self.propagation_status_var.set(status_messages.get(state, "Propagation : en attente") + stats_text)

        # Update start button
        if self.auto_running or not analysis_ready or analysis_complete or self.step_mode_var.get():
            self.btn_start_propagation.state(["disabled"])
        else:
            self.btn_start_propagation.state(["!disabled"])

        if self.auto_running:
            self.btn_start_propagation.config(text="Propagation en cours…")
        else:
            if self.propagation_needs_restart and analysis_ready and not analysis_complete:
                self.btn_start_propagation.config(text="▶ Relancer la propagation")
            else:
                self.btn_start_propagation.config(text="▶ Lancer la propagation")

    def start_auto_propagation(self):
        """Launch propagation in a background worker and poll results."""
        if self.step_mode_var.get():
            return
        if not self.analysis or self.analysis.get("status") != "ok":
            return
        if self.analysis.get("complete", False):
            return
        if self.auto_running and self.worker_thread and self.worker_thread.is_alive():
            return

        processed = self.analysis.get("processed_pixels", 0)
        frontier = self.analysis.get("frontier_count", 0)
        pending = self.analysis.get("pending_count", 0)
        propagation_logger.info(
            "Auto-propagation démarrée (processed=%d, frontier=%d, pending=%d, budget=%.0f, chunk=%.0f).",
            processed,
            frontier,
            pending,
            self.auto_pixels_budget,
            self.auto_chunk_size,
        )
        self.propagation_needs_restart = False
        self.auto_running = True
        self.force_render = True
        self.worker_queue = queue.Queue(maxsize=2)
        self.worker_stop_event = threading.Event()
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        self._schedule_worker_poll()
        self.update_propagation_controls()

    def _schedule_worker_poll(self):
        if self.worker_poll_after is not None:
            try:
                self.after_cancel(self.worker_poll_after)
            except Exception:
                pass
        self.worker_poll_after = self.after(16, self._poll_worker_queue)

    def _poll_worker_queue(self):
        self.worker_poll_after = None
        queue_ref = self.worker_queue
        if queue_ref is None:
            return

        stop_requested = False
        while True:
            try:
                latest = queue_ref.get_nowait()
            except queue.Empty:
                break
            self.apply_analysis_result(latest)
            status = latest.get("status")
            if status != "ok" or latest.get("complete", False):
                stop_requested = True
                break

        if stop_requested:
            self.stop_auto_propagation()
            return

        if self.auto_running and self.worker_thread and self.worker_thread.is_alive():
            self._schedule_worker_poll()
        else:
            self.auto_running = False

    def _enqueue_worker_result(self, queue_ref: queue.Queue, result: Dict[str, object]) -> None:
        if queue_ref is None:
            return
        try:
            queue_ref.put_nowait(result)
        except queue.Full:
            try:
                queue_ref.get_nowait()
            except queue.Empty:
                pass
            try:
                queue_ref.put_nowait(result)
            except queue.Full:
                pass

    def _worker_loop(self):
        stop_event = self.worker_stop_event
        queue_ref = self.worker_queue
        analyzer = self.app.hole_analyzer

        while stop_event and not stop_event.is_set():
            chunk_size = int(max(1, float(self.auto_chunk_size)))
            result = analyzer.advance_pixels(chunk_size)
            self._enqueue_worker_result(queue_ref, result)

            if result.get("status") != "ok" or result.get("complete", False):
                break

            time.sleep(0.0)

    def stop_auto_propagation(self):
        """Stop the background propagation worker."""
        if self.worker_poll_after is not None:
            try:
                self.after_cancel(self.worker_poll_after)
            except Exception:
                pass
            self.worker_poll_after = None

        if self.worker_stop_event:
            self.worker_stop_event.set()

        worker = self.worker_thread
        if worker and worker.is_alive():
            worker.join(timeout=0.5)

        self.worker_thread = None
        self.worker_stop_event = None
        if self.worker_queue is not None:
            try:
                while True:
                    self.worker_queue.get_nowait()
            except queue.Empty:
                pass
        self.worker_queue = None

        if self.auto_running:
            propagation_logger.debug("Auto-propagation interrompue.")
        self.auto_running = False
        self.force_render = True
        self.update_propagation_controls()

    def apply_analysis_result(self, analysis: Optional[Dict[str, object]]):
        """Store and display the latest analysis snapshot."""
        if analysis is None:
            analysis = {}

        self.analysis = analysis
        if analysis.get("processed_pixels", 0) or analysis.get("complete", False):
            self.propagation_needs_restart = False

        now = time.perf_counter()
        frame_dt = None
        fps_value = None
        if self.last_frame_time is not None and now > self.last_frame_time:
            frame_dt = now - self.last_frame_time
            fps_value = 1.0 / max(1e-6, frame_dt)
            self.fps_label.config(text=f"FPS : {fps_value:.1f}")
        else:
            self.fps_label.config(text="FPS : idle")

        if frame_dt is not None and propagation_logger.isEnabledFor(logging.DEBUG):
            propagation_logger.debug("Frame rendu en %.4fs (FPS ~%.1f)", frame_dt, fps_value or 0.0)

        self.last_frame_time = now

        mean_color = analysis.get("mean_color")
        if mean_color:
            self.app.puzzle_calibration.background_sample = mean_color
            self.canvas.background_sample = mean_color
            self.status_display.update_background(mean_color)

        self.update_summary_from_analysis()
        self.update_step_controls()
        self.update_debug_controls()

        overlay = analysis.get("overlay")
        if overlay is not None:
            self.analysis_display = overlay

        should_render = self.force_render or not self.auto_running or analysis.get("complete", False)
        if not should_render:
            if self.last_render_time <= 0.0 or now - self.last_render_time >= 0.1:
                should_render = True

        display_img = None
        if should_render:
            display_img = self._build_display_image(analysis)
            if display_img is not None:
                self.analysis_display = display_img
                self.canvas.show_image(display_img)
                self.last_render_time = now
                self.force_render = False

        if propagation_logger.isEnabledFor(logging.DEBUG):
            propagation_logger.debug(
                "Snapshot: processed=%d frontier=%d pending=%d active=%d frozen=%d loops=%d fps=%s",
                analysis.get("processed_pixels", 0),
                analysis.get("frontier_count", 0),
                analysis.get("pending_count", 0),
                analysis.get("active_count", 0),
                analysis.get("frozen_count", 0),
                analysis.get("loops_completed", 0),
                f"{fps_value:.1f}" if fps_value is not None else "idle",
            )
        self.update_propagation_controls()

    def update_summary_from_analysis(self):
        """Refresh UI labels based on the current analysis state."""
        analysis = self.analysis or {}
        status = analysis.get("status")

        if status != "ok":
            if status == "missing_rois":
                self.summary_label.config(
                    text="Sélectionnez les deux zones (bord puis intérieur) pour lancer la propagation."
                )
            else:
                self.summary_label.config(text="Propagation indisponible pour cette configuration.")
            self.stop_auto_propagation()
            self.fps_label.config(text="FPS : —")
            self.grid_label.config(text="")
            self.btn_next.state(["disabled"])
            return

        complete = analysis.get("complete", False)
        loops = analysis.get("loops_completed", 0)
        active = analysis.get("active_count", 0)
        frozen = analysis.get("frozen_count", 0)
        processed = analysis.get("processed_pixels", 0)
        frontier = analysis.get("frontier_count", 0)
        pending = analysis.get("pending_count", 0)

        if self.auto_running:
            self.summary_label.config(
                text=f"Propagation en cours · boucle #{loops + 1}. Pixels actifs : {active}."
            )
            self.btn_next.state(["disabled"])
        elif complete:
            loop_text = "1 boucle" if loops == 1 else f"{loops} boucles"
            self.summary_label.config(
                text=f"Propagation terminée ({loop_text}). Pixels figés : {frozen}."
            )
            self.stop_auto_propagation()
            self.btn_next.state(["!disabled"])
        elif self.propagation_needs_restart:
            last_stats = self.last_propagation_stats or {}
            extra = ""
            if last_stats:
                extra = (
                    f"\nDernier run : {last_stats.get('loops', 0)} boucles, "
                    f"{last_stats.get('frozen', 0)} pixels figés."
                )
            self.summary_label.config(
                text="Propagation périmée (réglages modifiés). Relancez-la pour appliquer les changements."
                + extra
            )
            self.btn_next.state(["disabled"])
        else:
            self.summary_label.config(
                text="Propagation prête. Cliquez sur « ▶ Lancer la propagation » pour continuer."
            )
            self.btn_next.state(["disabled"])

        color = analysis.get("mean_color")
        color_text = ""
        if color:
            color_text = f"\nCouleur moyenne : RGB({color[2]}, {color[1]}, {color[0]})."

        self.grid_label.config(
            text=(
                f"Pixels traités : {processed} · Front actif : {frontier}"
                f" · En attente : {pending}{color_text}"
            )
        )

    def step_one_pixel(self):
        """Advance the propagation by a single pixel."""
        if (
            not self.step_mode_var.get()
            or not self.analysis
            or self.analysis.get("status") != "ok"
            or self.analysis.get("complete", False)
        ):
            return

        self.stop_auto_propagation()
        analysis = self.app.hole_analyzer.advance_pixels(1)
        self.apply_analysis_result(analysis)

    def step_one_loop(self):
        """Advance the propagation by one full loop."""
        if (
            not self.step_mode_var.get()
            or not self.analysis
            or self.analysis.get("status") != "ok"
            or self.analysis.get("complete", False)
        ):
            return

        self.stop_auto_propagation()
        analysis = self.app.hole_analyzer.advance_loop()
        self.apply_analysis_result(analysis)

    def run_analysis(self):
        if self.base_image is None:
            return

        self.stop_auto_propagation()
        if self.param_update_after is not None:
            try:
                self.after_cancel(self.param_update_after)
            except Exception:
                pass
            self.param_update_after = None
        self.force_render = True
        self.last_render_time = 0.0
        self._capture_last_propagation_stats()

        outer = self.app.puzzle_calibration.outer_roi
        inner = self.app.puzzle_calibration.inner_roi

        if not outer or not inner:
            self.btn_refresh.state(["disabled"])
            self.analysis = {}
            self.analysis_display = draw_roi_overlay(self.base_image, outer, inner)
            self.summary_label.config(
                text="Sélectionnez les deux zones (bord puis intérieur) pour lancer la propagation."
            )
            self.grid_label.config(text="")
            self.fps_label.config(text="FPS : —")
            self.btn_next.state(["disabled"])
            self.update_step_controls()
            self.update_debug_controls()
            self.render_display()
            return

        self.btn_refresh.state(["!disabled"])

        blur_kernel = self.get_blur_kernel()
        canny_low, canny_high = self.get_canny_thresholds()
        min_gap = self.get_min_gap()
        self.auto_pixels_budget = float(self.AUTO_PIXELS_PER_FRAME)
        self.auto_chunk_size = float(self.AUTO_CHUNK_SIZE)
        propagation_logger.info(
            "Analyse lancée (blur=%d, canny=(%d,%d), gap=%d, outer=%s, inner=%s).",
            blur_kernel,
            canny_low,
            canny_high,
            min_gap,
            outer,
            inner,
        )

        analysis = self.app.hole_analyzer.prepare(
            self.base_image, outer, inner, blur_kernel, canny_low, canny_high, min_gap
        )
        if analysis.get("status") != "ok":
            propagation_logger.warning("Analyse échouée (statut=%s).", analysis.get("status"))
            self.propagation_needs_restart = False
            self.apply_analysis_result(analysis)
            return

        self.propagation_needs_restart = self.last_propagation_stats is not None
        self.apply_analysis_result(analysis)

        if self.detected_pieces is not None:
            self.pieces_label.config(
                text=f"Pièces détectées à l'intérieur : {self.detected_pieces}",
                fg=PALETTE["accent"] if self.detected_pieces else PALETTE["muted"],
            )

        self.update_propagation_controls()

    def render_display(self):
        if self.base_image is None:
            return
        display_img = self._build_display_image()
        if display_img is None:
            return
        self.canvas.show_image(display_img)
        self.analysis_display = display_img
        self.last_render_time = time.perf_counter()
        self.force_render = False

    def _build_display_image(self, analysis: Optional[Dict[str, object]] = None):
        if self.base_image is None:
            return None
        analysis = analysis or self.analysis or {}
        if self.debug_enabled.get():
            debug_img = self._compose_debug_image()
            if debug_img is not None:
                return debug_img
        overlay = analysis.get("overlay") if analysis else None
        if overlay is not None:
            return overlay
        return draw_roi_overlay(
            self.base_image,
            self.app.puzzle_calibration.outer_roi,
            self.app.puzzle_calibration.inner_roi,
        )

    def _compose_debug_image(self) -> Optional[np.ndarray]:
        if self.base_image is None:
            return None
        composite = self.base_image.copy()
        analyzer = self.app.hole_analyzer
        if not analyzer:
            return composite

        if self.debug_blur_var.get():
            blur = analyzer.get_blur_image()
            if blur is not None:
                composite = cv2.addWeighted(composite, 0.5, blur, 0.5, 0)

        if self.debug_canny_var.get():
            edges = analyzer.get_edges_image()
            if edges is not None:
                mask = edges.any(axis=2)
                composite[mask] = edges[mask]

        if self.debug_state_var.get():
            state = analyzer.get_state_overlay()
            geometry = analyzer.get_roi_geometry()
            mask = analyzer.get_mask()
            if state is not None and geometry and mask is not None:
                origin_x, origin_y, width, height = geometry
                local_comp = composite[origin_y : origin_y + height, origin_x : origin_x + width]
                local_state = state[origin_y : origin_y + height, origin_x : origin_x + width]
                border_mask = mask == 1
                if np.any(border_mask):
                    blend = (
                        0.4 * local_comp[border_mask].astype(np.float32)
                        + 0.6 * local_state[border_mask].astype(np.float32)
                    )
                    local_comp[border_mask] = blend.astype(np.uint8)
            elif state is not None:
                composite = cv2.addWeighted(composite, 0.4, state, 0.6, 0)

        return composite

    def next_step(self):
        if not self.app.puzzle_image_path:
            return

        calib = CalibrationData(
            roi=self.app.puzzle_calibration.inner_roi,
            background_sample=self.app.puzzle_calibration.background_sample,
            min_area=self.min_area_var.get(),
            max_area=self.max_area_var.get(),
        )

        detector = PuzzlePieceDetector(calib)
        self.app.puzzle_pieces = detector.detect_pieces(
            self.app.puzzle_image_path, "puzzle_state"
        )

        self.detected_pieces = len(self.app.puzzle_pieces)
        self.pieces_label.config(
            text=f"Pièces détectées à l'intérieur : {self.detected_pieces}",
            fg=PALETTE["accent"] if self.detected_pieces else PALETTE["warning"],
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

        self._configure_piece_images(list(paths), silent=False)

    def _configure_piece_images(self, paths: List[str], *, silent: bool) -> bool:
        """Apply loaded piece images and refresh the UI."""
        if not paths:
            return False

        first_img = None
        resolved_first_path: Optional[str] = None
        for candidate in _candidate_paths(paths[0]):
            first_img = cv2.imread(str(candidate))
            if first_img is not None:
                resolved_first_path = str(candidate)
                break

        if first_img is None or resolved_first_path is None:
            logger.error("Impossible de charger la première image de pièces %s", paths[0])
            if not silent:
                messagebox.showerror("Octopuzzle", "Impossible de charger la première image.")
            return False

        resolved_paths: List[str] = [resolved_first_path]
        for raw_path in paths[1:]:
            existing = find_existing_path(raw_path)
            if existing:
                resolved_paths.append(str(existing))
            else:
                resolved_paths.append(str(Path(raw_path)))

        self.app.pieces_image_paths = resolved_paths
        self.current_image_index = 0

        image_names = [f"Image {i+1}" for i in range(len(resolved_paths))]
        self.image_selector["values"] = image_names
        if image_names:
            self.image_selector.current(0)

        self.canvas.load_image(first_img)
        self.status_label.config(
            text=f"{len(resolved_paths)} images chargées. Ajustez la calibration si nécessaire."
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
        return True

    def on_image_changed(self, event):
        """Handle image selection change."""
        self.current_image_index = self.image_selector.current()
        if 0 <= self.current_image_index < len(self.app.pieces_image_paths):
            path = self.app.pieces_image_paths[self.current_image_index]
            img = cv2.imread(str(path))
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
                img = cv2.imread(str(self.app.pieces_image_paths[self.current_image_index]))
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
        current_path = str(self.app.pieces_image_paths[self.current_image_index])
        pieces, debug_img = detector.detect_with_debug(current_path)

        if debug_img is not None:
            self.canvas.show_debug_image(debug_img)
            self.status_label.config(
                text=f"{len(pieces)} pièces détectées dans l'image sélectionnée."
            )

    def export_state(self) -> Dict[str, Any]:
        """Return the calibration state for available pieces."""
        images = [
            value
            for value in (_serialise_path(path) for path in self.app.pieces_image_paths)
            if value
        ]
        return {
            "images": images,
            "roi": _roi_to_list(self.app.pieces_calibration.roi),
            "background_sample": _color_to_list(self.app.pieces_calibration.background_sample),
            "min_area": int(self.min_area_var.get()),
            "max_area": int(self.max_area_var.get()),
        }

    def apply_state(self, state: Optional[Dict[str, Any]]) -> None:
        """Restore calibration for the pieces step."""
        if not state:
            return

        images_raw = [str(p) for p in (state.get("images") or []) if p]
        if images_raw:
            loaded = self._configure_piece_images(images_raw, silent=True)
            if not loaded:
                logger.warning("Impossible de recharger les images de pièces depuis la session.")

        if "min_area" in state:
            value = int(state["min_area"])
            self.min_area_var.set(value)
            self.app.pieces_calibration.min_area = value
        if "max_area" in state:
            value = int(state["max_area"])
            self.max_area_var.set(value)
            self.app.pieces_calibration.max_area = value

        if not self.app.pieces_image_paths:
            return

        roi = _tuple_from_sequence(state.get("roi"))
        if roi:
            self.canvas.roi = roi
            self.on_roi_selected(roi)

        bg = _color_from_sequence(state.get("background_sample"))
        if bg:
            self.canvas.background_sample = bg
            self.on_background_selected(bg)

    def apply_cli_overrides(self, args: argparse.Namespace) -> None:
        """Currently unused placeholder for CLI overrides on step 2."""
        _ = args  # Placeholder to avoid unused warnings.

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


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Assistant Octopuzzle")
    parser.add_argument("--hole-image", type=Path, help="Chemin de l'image du trou à charger au démarrage.")
    parser.add_argument(
        "--outer-roi",
        type=parse_roi,
        help="Coordonnées x,y,w,h de la zone extérieure (calibration trou).",
    )
    parser.add_argument(
        "--inner-roi",
        type=parse_roi,
        help="Coordonnées x,y,w,h de la zone intérieure (calibration trou).",
    )
    parser.add_argument("--blur-kernel", type=int, help="Taille du noyau de flou gaussien (impair).")
    parser.add_argument("--canny-low", type=int, help="Seuil bas de Canny.")
    parser.add_argument("--canny-high", type=int, help="Seuil haut de Canny.")
    parser.add_argument("--min-area", type=int, help="Surface minimale pour la détection de pièces.")
    parser.add_argument("--max-area", type=int, help="Surface maximale pour la détection de pièces.")
    parser.add_argument("--min-gap", type=int, help="Largeur minimale (px) pour franchir un passage lors de la propagation.")
    parser.add_argument("--load-session", type=Path, help="Charger un fichier de session JSON existant.")
    parser.add_argument("--save-session", type=Path, help="Enregistrer la session à la fermeture.")
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Niveau global des logs (par défaut WARNING).",
    )
    parser.add_argument("--log-file", type=Path, help="Chemin d'un fichier où écrire les logs.")
    parser.add_argument(
        "--log-propagation",
        action="store_true",
        help="Active les logs détaillés de la propagation du trou.",
    )
    return parser.parse_args(argv)


def configure_logging(args: argparse.Namespace) -> None:
    """Configure logging according to CLI options."""
    level_name = getattr(args, "log_level", "INFO")
    level = getattr(logging, level_name.upper(), logging.INFO)

    handlers: List[logging.Handler] = []

    log_file = getattr(args, "log_file", None)
    if log_file:
        log_path = Path(log_file)
        if log_path.parent and not log_path.parent.exists():
            log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))

    handlers.append(logging.StreamHandler())

    logging.basicConfig(
        level=level,
        handlers=handlers,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        force=True,
    )

    if getattr(args, "log_propagation", False):
        logging.getLogger("octopuzzle.propagation").setLevel(logging.DEBUG)


def main(argv: Optional[List[str]] = None):
    """Run the application"""
    args = parse_args(argv)
    configure_logging(args)
    app = OctopuzzleApp(args)
    app.mainloop()


if __name__ == "__main__":
    main()
