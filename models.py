"""
Octopuzzle - Data Models and Business Logic
Contains: CalibrationData, PuzzlePiece, Detector, Matcher, Solver
"""

import logging
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict

import cv2
import numpy as np

logger = logging.getLogger("octopuzzle.propagation")

ACTIVE_COLOR = np.array([60, 60, 255], dtype=np.uint8)
FROZEN_COLOR = np.array([212, 190, 6], dtype=np.uint8)


@dataclass
class CalibrationData:
    """Calibration settings for piece detection"""
    roi: Optional[Tuple[int, int, int, int]] = None  # (x, y, w, h)
    background_sample: Optional[Tuple[int, int, int]] = None  # BGR color
    min_area: int = 500
    max_area: int = 50000


@dataclass
class HoleCalibration:
    """Calibration settings specific to the puzzle hole analysis."""
    outer_roi: Optional[Tuple[int, int, int, int]] = None
    inner_roi: Optional[Tuple[int, int, int, int]] = None
    background_sample: Optional[Tuple[int, int, int]] = None


@dataclass
class PuzzlePiece:
    """Represents a detected puzzle piece"""
    id: int
    source_image: str  # Path to source image
    bbox_in_source: Tuple[int, int, int, int]  # (x, y, w, h)
    category: int  # Based on tab configuration
    width: float  # Normalized width
    height: float  # Normalized height
    tabs: List[int]  # [top, right, bottom, left]: 1=out, -1=in, 0=flat
    piece_type: str = "available"  # "puzzle_state" or "available"


class PuzzlePieceDetector:
    """Detects puzzle pieces in images using OpenCV"""

    def __init__(self, calibration: Optional[CalibrationData] = None):
        self.calibration = calibration or CalibrationData()

    def detect_pieces(self, image_path: str, piece_type: str = "available") -> List[PuzzlePiece]:
        """Detect all pieces in an image"""
        img = cv2.imread(image_path)
        if img is None:
            return []

        # Apply ROI if calibrated
        roi_offset = (0, 0)
        if self.calibration.roi:
            x, y, w, h = self.calibration.roi
            img = img[y:y+h, x:x+w]
            roi_offset = (x, y)

        # Preprocessing
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Background removal if calibrated
        if self.calibration.background_sample:
            img_masked = self._remove_background(img, self.calibration.background_sample)
            gray = cv2.cvtColor(img_masked, cv2.COLOR_BGR2GRAY)

        # Adaptive threshold for better piece detection
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        binary = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                      cv2.THRESH_BINARY, 11, 2)

        # Morphological operations to clean up
        kernel = np.ones((3, 3), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)

        # Find contours
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        pieces = []
        piece_id = 0

        for contour in contours:
            area = cv2.contourArea(contour)
            if self.calibration.min_area < area < self.calibration.max_area:
                piece = self._analyze_piece(contour, piece_id, image_path, piece_type, roi_offset)
                if piece:
                    pieces.append(piece)
                    piece_id += 1

        return pieces

    def detect_with_debug(self, image_path: str) -> Tuple[List[PuzzlePiece], np.ndarray]:
        """Detect pieces and return debug image with contours"""
        img = cv2.imread(image_path)
        if img is None:
            return [], None

        original = img.copy()

        # Apply ROI if calibrated
        roi_offset = (0, 0)
        if self.calibration.roi:
            x, y, w, h = self.calibration.roi
            img = img[y:y+h, x:x+w]
            roi_offset = (x, y)
            # Draw ROI on original
            cv2.rectangle(original, (x, y), (x+w, y+h), (255, 0, 255), 3)

        # Preprocessing
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Background removal if calibrated
        if self.calibration.background_sample:
            img_masked = self._remove_background(img, self.calibration.background_sample)
            gray = cv2.cvtColor(img_masked, cv2.COLOR_BGR2GRAY)

        # Adaptive threshold
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        binary = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                      cv2.THRESH_BINARY, 11, 2)

        # Morphological operations
        kernel = np.ones((3, 3), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)

        # Find contours
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        pieces = []
        piece_id = 0

        # Draw all contours on original image
        debug_img = original.copy()

        for contour in contours:
            area = cv2.contourArea(contour)

            # Adjust contour coordinates for ROI
            contour_adjusted = contour.copy()
            if self.calibration.roi:
                contour_adjusted[:, 0, 0] += roi_offset[0]
                contour_adjusted[:, 0, 1] += roi_offset[1]

            if self.calibration.min_area < area < self.calibration.max_area:
                # Valid piece - draw in green
                cv2.drawContours(debug_img, [contour_adjusted], -1, (0, 255, 0), 3)
                piece = self._analyze_piece(contour, piece_id, "", "available", roi_offset)
                if piece:
                    pieces.append(piece)
                    # Draw piece ID
                    x, y, w, h = cv2.boundingRect(contour)
                    text_x = x + roi_offset[0]
                    text_y = y + roi_offset[1]
                    cv2.putText(debug_img, f"#{piece_id}", (text_x, text_y-10),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    piece_id += 1
            else:
                # Invalid piece (too small/large) - draw in red
                cv2.drawContours(debug_img, [contour_adjusted], -1, (0, 0, 255), 2)
                cv2.putText(debug_img, f"Area:{int(area)}",
                           (contour_adjusted[0][0][0], contour_adjusted[0][0][1]),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

        # Add legend
        cv2.putText(debug_img, f"Found {len(pieces)} pieces | {len(contours)} contours total",
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 0), 2)
        cv2.putText(debug_img, f"Legend: GREEN=valid pieces | RED=rejected (area)",
                   (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.putText(debug_img, f"Area range: {self.calibration.min_area}-{self.calibration.max_area} px²",
                   (10, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

        return pieces, debug_img

    def _remove_background(self, img, bg_color: Tuple[int, int, int], tolerance=30):
        """Remove background based on color sample"""
        lower = np.array([max(0, c - tolerance) for c in bg_color])
        upper = np.array([min(255, c + tolerance) for c in bg_color])
        mask = cv2.inRange(img, lower, upper)
        mask_inv = cv2.bitwise_not(mask)
        result = cv2.bitwise_and(img, img, mask=mask_inv)
        return result

    def _analyze_piece(self, contour, piece_id: int, source: str, piece_type: str, roi_offset=(0, 0)) -> Optional[PuzzlePiece]:
        """Analyze contour to extract piece information"""
        x, y, w, h = cv2.boundingRect(contour)

        # Adjust for ROI offset
        x += roi_offset[0]
        y += roi_offset[1]

        diag = np.sqrt(w**2 + h**2)
        norm_w = w / diag if diag > 0 else 0
        norm_h = h / diag if diag > 0 else 0

        tabs = self._detect_tabs(contour, x - roi_offset[0], y - roi_offset[1], w, h)
        category = self._compute_category(tabs)

        return PuzzlePiece(
            id=piece_id,
            source_image=source,
            bbox_in_source=(x, y, w, h),
            category=category,
            width=norm_w,
            height=norm_h,
            tabs=tabs,
            piece_type=piece_type
        )

    def _detect_tabs(self, contour, x, y, w, h) -> List[int]:
        """Detect tabs on each side: 1=out, -1=in, 0=flat"""
        if w <= 0 or h <= 0:
            return [0, 0, 0, 0]

        # Work on a binary mask of the contour so we can analyse per-side profiles
        contour_local = contour.copy()
        contour_local[:, 0, 0] -= x
        contour_local[:, 0, 1] -= y

        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.drawContours(mask, [contour_local], -1, 255, thickness=-1)

        def classify(mask_side: np.ndarray) -> int:
            """Return tab type for a mask oriented with the side facing 'up'."""
            h_side, w_side = mask_side.shape
            if h_side == 0 or w_side == 0:
                return 0

            start = int(w_side * 0.2)
            end = int(w_side * 0.8)
            if end <= start:
                start, end = 0, w_side

            strip = mask_side[:, start:end] if (end - start) > 0 else mask_side
            column_pixels = strip > 0
            if column_pixels.size == 0 or not column_pixels.any():
                return 0

            valid_cols = column_pixels.any(axis=0)
            if not valid_cols.any():
                return 0

            top_indices = np.argmax(column_pixels[:, valid_cols], axis=0)
            max_depth = float(top_indices.max()) / max(h_side, 1)
            mean_depth = float(top_indices.mean()) / max(h_side, 1)
            coverage_ratio = float(valid_cols.sum()) / column_pixels.shape[1]

            # Deep indent -> inward tab
            if max_depth > 0.18 or mean_depth > 0.12:
                return -1

            # Narrow coverage -> outward tab
            if coverage_ratio < 0.65:
                return 1

            return 0

        tabs = [
            classify(mask),                     # Top
            classify(np.rot90(mask, k=1)),      # Right
            classify(np.rot90(mask, k=2)),      # Bottom
            classify(np.rot90(mask, k=-1))      # Left
        ]

        return [int(t) for t in tabs]

    def _compute_category(self, tabs: List[int]) -> int:
        """Compute piece category based on tab configuration"""
        count = sum(1 for t in tabs if t != 0)

        if count == 0:
            return 0  # No tabs
        elif count == 1:
            return 1  # Corner
        elif count == 2:
            # Check if opposite sides
            if (tabs[0] != 0 and tabs[2] != 0) or (tabs[1] != 0 and tabs[3] != 0):
                return 3  # Opposite sides
            else:
                return 2  # Adjacent sides
        elif count == 3:
            return 4  # Three sides
        else:
            return 5  # All sides


class HoleAnalyzer:
    """Simple mask-based propagation from the inner ROI towards the outer ROI."""

    def __init__(self):
        self.state: Optional[Dict[str, object]] = None
        self.debug_enabled = False

    def reset(self) -> None:
        """Clear any previous analysis state."""
        self.state = None

    def set_debug(self, enabled: bool) -> None:
        """Enable or disable building of debug layers."""
        self.debug_enabled = bool(enabled)

    def prepare(
        self,
        image: np.ndarray,
        outer_roi: Optional[Tuple[int, int, int, int]],
        inner_roi: Optional[Tuple[int, int, int, int]],
        blur_kernel: int = 5,
        canny_low: int = 45,
        canny_high: int = 110,
        closing_radius: int = 5,
        opening_radius: int = 0,
        closing_enabled: bool = True,
        opening_enabled: bool = False,
        edge_min_area: int = 0,
    ) -> Dict[str, object]:
        """Initialise the propagation state and return the first snapshot."""
        self.reset()
        base_result = self._empty_result("missing_rois")

        if image is None or outer_roi is None or inner_roi is None:
            return base_result

        x_outer, y_outer, w_outer, h_outer = outer_roi
        x_inner, y_inner, w_inner, h_inner = inner_roi

        # Clamp the inner ROI to the outer ROI bounds.
        x_inner = max(x_outer, x_inner)
        y_inner = max(y_outer, y_inner)
        right_outer = x_outer + w_outer
        bottom_outer = y_outer + h_outer
        w_inner = min(w_inner, right_outer - x_inner)
        h_inner = min(h_inner, bottom_outer - y_inner)
        if w_inner <= 0 or h_inner <= 0:
            return base_result

        h_img, w_img = image.shape[:2]
        if w_img == 0 or h_img == 0:
            return base_result

        kernel = max(1, int(blur_kernel))
        if kernel % 2 == 0:
            kernel += 1

        canny_low = max(0, int(canny_low))
        canny_high = max(canny_low + 1, int(canny_high))

        x_inner_local = x_inner - x_outer
        y_inner_local = y_inner - y_outer

        crop = image[y_outer:bottom_outer, x_outer:right_outer].copy()
        gray_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        if kernel > 1:
            blurred_crop = cv2.GaussianBlur(crop, (kernel, kernel), 0)
            blurred_gray = cv2.GaussianBlur(gray_crop, (kernel, kernel), 0)
        else:
            blurred_crop = crop.copy()
            blurred_gray = gray_crop.copy()

        edges = cv2.Canny(blurred_gray, canny_low, canny_high)
        closing_radius = max(1, int(closing_radius))
        opening_radius = max(1, int(opening_radius))
        if closing_radius % 2 == 0:
            closing_radius += 1
        if opening_radius % 2 == 0:
            opening_radius += 1

        if closing_enabled and closing_radius > 1:
            kernel_close = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE, (closing_radius, closing_radius)
            )
            edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel_close)

        if opening_enabled and opening_radius > 1:
            kernel_open = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE, (opening_radius, opening_radius)
            )
            edges = cv2.morphologyEx(edges, cv2.MORPH_OPEN, kernel_open)

        edge_min_area = max(0, int(edge_min_area))
        if edge_min_area > 0:
            binary = (edges > 0).astype(np.uint8)
            num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
            filtered = np.zeros_like(edges)
            for label_idx in range(1, num_labels):
                if stats[label_idx, cv2.CC_STAT_AREA] >= edge_min_area:
                    filtered[labels == label_idx] = 255
            edges = filtered

        mask = np.zeros((h_outer, w_outer), dtype=np.uint8)
        interior_mask = np.zeros((h_outer, w_outer), dtype=bool)

        if w_inner > 2 and h_inner > 2:
            interior_mask[
                y_inner_local + 1 : y_inner_local + h_inner - 1,
                x_inner_local + 1 : x_inner_local + w_inner - 1,
            ] = True
        edges[
            y_inner_local : y_inner_local + h_inner,
            x_inner_local : x_inner_local + w_inner,
        ] = 0

        border_pixels = set()
        for xs in range(x_inner_local, x_inner_local + w_inner):
            mask[y_inner_local, xs] = 1
            border_pixels.add((y_inner_local, xs))
            edges[y_inner_local, xs] = 0
            if h_inner > 1:
                y_bottom = y_inner_local + h_inner - 1
                mask[y_bottom, xs] = 1
                border_pixels.add((y_bottom, xs))
                edges[y_bottom, xs] = 0

        for ys in range(y_inner_local, y_inner_local + h_inner):
            mask[ys, x_inner_local] = 1
            border_pixels.add((ys, x_inner_local))
            edges[ys, x_inner_local] = 0
            if w_inner > 1:
                x_right = x_inner_local + w_inner - 1
                mask[ys, x_right] = 1
                border_pixels.add((ys, x_right))
                edges[ys, x_right] = 0

        frontier = deque(sorted(border_pixels))
        complete = len(frontier) == 0
        active_count = len(frontier)

        mean_color = tuple(
            int(c)
            for c in cv2.mean(
                crop[y_inner_local : y_inner_local + h_inner, x_inner_local : x_inner_local + w_inner]
            )[:3]
        )

        overlay_full = image.copy()
        overlay_local = overlay_full[y_outer:bottom_outer, x_outer:right_outer]
        overlay_local[:] = crop
        overlay_local[mask == 1] = ACTIVE_COLOR

        edges_overlay_full = np.zeros_like(image)
        edges_overlay_local = edges_overlay_full[y_outer:bottom_outer, x_outer:right_outer]
        edges_overlay_local[edges > 0] = np.array([0, 255, 255], dtype=np.uint8)

        blur_full = image.copy()
        blur_full[y_outer:bottom_outer, x_outer:right_outer] = blurred_crop

        self.state = {
            "image": image,
            "origin": (x_outer, y_outer),
            "width": w_outer,
            "height": h_outer,
            "mask": mask,
            "interior_mask": interior_mask,
            "frontier": frontier,
            "next_frontier": deque(),
            "loop_remaining": len(frontier),
            "loops_completed": 0,
            "processed_pixels": 0,
            "complete": complete,
            "active_count": active_count,
            "frozen_count": 0,
            "blur_kernel": kernel,
            "edges": edges,
            "edges_overlay_full": edges_overlay_full,
            "blur_full": blur_full,
            "mean_color": mean_color,
            "canny_low": canny_low,
            "canny_high": canny_high,
            "closing_enabled": bool(closing_enabled),
            "closing_radius": closing_radius,
            "opening_enabled": bool(opening_enabled),
            "opening_radius": opening_radius,
            "edge_min_area": edge_min_area,
            "overlay_full": overlay_full,
            "overlay_local": overlay_local,
        }

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                (
                    "Propagation initialisée (inner=%s outer=%s frontier=%d mean_color=%s "
                    "closing=%s/%d opening=%s/%d edge_min=%d)"
                ),
                (x_inner, y_inner, w_inner, h_inner),
                outer_roi,
                len(frontier),
                mean_color,
                closing_enabled,
                closing_radius,
                opening_enabled,
                opening_radius,
                edge_min_area,
            )

        return self._build_result(status="ok")

    def advance_pixels(self, count: int = 1) -> Dict[str, object]:
        """Advance the propagation by a fixed number of pixels."""
        if not self.state or count <= 0:
            return self._build_result()

        while count > 0 and not self.state["complete"]:
            if not self._ensure_frontier_ready():
                break
            if not self.state["frontier"]:
                break

            y, x = self.state["frontier"].popleft()
            if self.state["mask"][y, x] != 1:
                continue

            self.state["loop_remaining"] = max(0, self.state["loop_remaining"] - 1)
            self._process_pixel(y, x)
            self.state["processed_pixels"] += 1
            count -= 1

            if self.state["loop_remaining"] == 0:
                self._start_next_loop()

        if logger.isEnabledFor(logging.DEBUG) and self.state:
            logger.debug(
                "advance_pixels terminé: processed=%d frontier=%d pending=%d loops=%d complete=%s",
                self.state["processed_pixels"],
                len(self.state["frontier"]),
                len(self.state["next_frontier"]),
                self.state["loops_completed"],
                self.state["complete"],
            )
        return self._build_result()

    def advance_loop(self) -> Dict[str, object]:
        """Process the current frontier (one full loop)."""
        if not self.state or self.state["complete"]:
            return self._build_result()

        if not self._ensure_frontier_ready():
            return self._build_result()

        iterations = self.state["loop_remaining"]
        for _ in range(iterations):
            if not self.state["frontier"]:
                break

            y, x = self.state["frontier"].popleft()
            if self.state["mask"][y, x] != 1:
                continue

            self.state["loop_remaining"] = max(0, self.state["loop_remaining"] - 1)
            self._process_pixel(y, x)
            self.state["processed_pixels"] += 1

        self._start_next_loop()
        if logger.isEnabledFor(logging.DEBUG) and self.state:
            logger.debug(
                "advance_loop terminé: processed=%d frontier=%d pending=%d loops=%d complete=%s",
                self.state["processed_pixels"],
                len(self.state["frontier"]),
                len(self.state["next_frontier"]),
                self.state["loops_completed"],
                self.state["complete"],
            )
        return self._build_result()

    def run_to_completion(self, max_loops: Optional[int] = None) -> Dict[str, object]:
        """Run the propagation until no active pixels remain."""
        if not self.state:
            return self._build_result()

        loops_done = 0
        while not self.state["complete"]:
            self.advance_loop()
            loops_done += 1
            if max_loops is not None and loops_done >= max_loops:
                break

        return self._build_result()

    def get_result(self) -> Dict[str, object]:
        """Return the current analysis result."""
        return self._build_result()

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #

    def _ensure_frontier_ready(self) -> bool:
        """Ensure there is a frontier to process."""
        if not self.state:
            return False

        while self.state["frontier"] and self.state["mask"][self.state["frontier"][0][0], self.state["frontier"][0][1]] != 1:
            self.state["frontier"].popleft()

        if self.state["frontier"]:
            if self.state["loop_remaining"] == 0:
                self.state["loop_remaining"] = len(self.state["frontier"])
            return True

        if self.state["next_frontier"]:
            self._start_next_loop()
            return not self.state["complete"]

        self.state["complete"] = True
        self.state["loop_remaining"] = 0
        return False

    def _start_next_loop(self) -> None:
        """Promote the next frontier or mark completion."""
        if not self.state:
            return

        while self.state["frontier"] and self.state["mask"][self.state["frontier"][0][0], self.state["frontier"][0][1]] != 1:
            self.state["frontier"].popleft()

        if self.state["frontier"] and self.state["loop_remaining"] > 0:
            return

        if self.state["next_frontier"]:
            self.state["frontier"] = self.state["next_frontier"]
            self.state["next_frontier"] = deque()
            self.state["loop_remaining"] = len(self.state["frontier"])
            self.state["loops_completed"] += 1
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "Boucle suivante démarrée: loops=%d frontier=%d",
                    self.state["loops_completed"],
                    len(self.state["frontier"]),
                )
        else:
            self.state["frontier"] = deque()
            self.state["loop_remaining"] = 0
            self.state["complete"] = True
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "Propagation complétée après %d boucles.",
                    self.state["loops_completed"],
                )

    def _process_pixel(self, y: int, x: int) -> None:
        """Transition a single pixel from frontier to frozen and grow the mask outward."""
        if not self.state:
            return

        mask = self.state["mask"]
        edges = self.state["edges"]
        width = self.state["width"]
        height = self.state["height"]
        interior = self.state["interior_mask"]

        self.state["active_count"] = max(0, self.state["active_count"] - 1)

        freeze_pixel = edges[y, x] > 0
        neighbours = self._neighbours(y, x, width, height)

        for ny, nx in neighbours:
            if interior[ny, nx]:
                continue
            if mask[ny, nx] == 2:
                continue
            if edges[ny, nx] > 0:
                freeze_pixel = True
                continue
            if mask[ny, nx] == 0:
                mask[ny, nx] = 1
                self.state["next_frontier"].append((ny, nx))
                self.state["active_count"] += 1

        mask[y, x] = 2
        self.state["frozen_count"] += 1
        if freeze_pixel and not self.state["next_frontier"]:
            for ny, nx in neighbours:
                if interior[ny, nx] or mask[ny, nx] != 0:
                    continue
                mask[ny, nx] = 1
                self.state["next_frontier"].append((ny, nx))
                self.state["active_count"] += 1
                break
        overlay = self.state["overlay_local"]
        overlay[y, x] = FROZEN_COLOR

    @staticmethod
    def _neighbours(y: int, x: int, width: int, height: int) -> List[Tuple[int, int]]:
        neighbours = []
        if x > 0:
            neighbours.append((y, x - 1))
        if x + 1 < width:
            neighbours.append((y, x + 1))
        if y > 0:
            neighbours.append((y - 1, x))
        if y + 1 < height:
            neighbours.append((y + 1, x))
        return neighbours

    def _build_result(self, status: str = "ok") -> Dict[str, object]:
        if not self.state:
            return self._empty_result(status)

        overlay = self._ensure_overlay()

        active = int(self.state.get("active_count", 0))
        frozen = int(self.state.get("frozen_count", 0))

        debug_layers = self._build_debug_layers(overlay) if self.debug_enabled else {}

        return {
            "status": status,
            "overlay": overlay,
            "mask": None,
            "debug_layers": debug_layers,
            "complete": self.state["complete"],
            "loops_completed": self.state["loops_completed"],
            "processed_pixels": self.state["processed_pixels"],
            "loop_remaining": self.state["loop_remaining"],
            "frontier_count": len(self.state["frontier"]),
            "pending_count": len(self.state["next_frontier"]),
            "active_count": active,
            "frozen_count": frozen,
            "blur_kernel": self.state["blur_kernel"],
            "mean_color": self.state["mean_color"],
            "canny_low": self.state["canny_low"],
            "canny_high": self.state["canny_high"],
            "closing_enabled": self.state.get("closing_enabled", True),
            "closing_radius": self.state.get("closing_radius", 5),
            "opening_enabled": self.state.get("opening_enabled", False),
            "opening_radius": self.state.get("opening_radius", 0),
            "edge_min_area": self.state.get("edge_min_area", 0),
        }

    def _ensure_overlay(self) -> np.ndarray:
        if not self.state:
            return np.zeros((1, 1, 3), dtype=np.uint8)
        return self.state["overlay_full"]

    def _build_debug_layers(self, overlay: np.ndarray) -> Dict[str, np.ndarray]:
        if not self.debug_enabled or not self.state:
            return {}

        debug: Dict[str, np.ndarray] = {}
        overlay_full = self.state.get("overlay_full")
        if overlay_full is not None:
            debug["Masque (overlay)"] = overlay_full
            debug["Carte des états"] = overlay_full

        edges_overlay = self.state.get("edges_overlay_full")
        if edges_overlay is not None:
            debug["Contours Canny (propagation)"] = edges_overlay

        blur_full = self.state.get("blur_full")
        if blur_full is not None:
            debug["Zone externe floutée"] = blur_full

        return debug

    def get_state_overlay(self) -> Optional[np.ndarray]:
        if not self.state:
            return None
        return self.state.get("overlay_full")

    def get_edges_image(self) -> Optional[np.ndarray]:
        if not self.state:
            return None
        return self.state.get("edges_overlay_full")

    def get_blur_image(self) -> Optional[np.ndarray]:
        if not self.state:
            return None
        return self.state.get("blur_full")

    def get_mask(self) -> Optional[np.ndarray]:
        if not self.state:
            return None
        return self.state["mask"].copy()

    def get_roi_geometry(self) -> Optional[Tuple[int, int, int, int]]:
        if not self.state:
            return None
        origin_x, origin_y = self.state["origin"]
        return origin_x, origin_y, self.state["width"], self.state["height"]

    @staticmethod
    def _empty_result(status: str) -> Dict[str, object]:
        return {
            "status": status,
            "overlay": None,
            "mask": None,
            "debug_layers": {},
            "complete": False,
            "loops_completed": 0,
            "processed_pixels": 0,
            "loop_remaining": 0,
            "frontier_count": 0,
            "pending_count": 0,
            "active_count": 0,
            "frozen_count": 0,
            "blur_kernel": None,
            "mean_color": None,
            "canny_low": None,
            "canny_high": None,
        }


class PuzzleMatcher:
    """Finds compatible pieces based on tab matching"""

    def __init__(self, pieces: List[PuzzlePiece]):
        self.pieces = pieces
        self.by_category = defaultdict(list)
        for piece in pieces:
            self.by_category[piece.category].append(piece)

    def find_compatible(self, piece: PuzzlePiece, side: int) -> List[Tuple[PuzzlePiece, int, float]]:
        """Find pieces that can connect to given piece on given side"""
        target_tab = piece.tabs[side]
        if target_tab == 0:
            return []

        compatible = []
        required_tab = -target_tab  # Opposite tab type

        for candidate in self.pieces:
            if candidate.id == piece.id:
                continue

            # Check all sides of candidate
            for cand_side in range(4):
                if candidate.tabs[cand_side] == required_tab:
                    score = self._compute_match_score(piece, side, candidate, cand_side)
                    if score > 0:
                        compatible.append((candidate, cand_side, score))

        compatible.sort(key=lambda x: x[2], reverse=True)
        return compatible

    def _compute_match_score(self, p1: PuzzlePiece, s1: int, p2: PuzzlePiece, s2: int) -> float:
        """Compute compatibility score between two pieces"""
        # For horizontal connections, check width similarity
        if s1 in [0, 2]:  # Top or bottom
            size_diff = abs(p1.width - p2.width)
        else:  # Left or right
            size_diff = abs(p1.height - p2.height)

        if size_diff > 0.15:
            return 0.0

        score = 1.0 - size_diff * 5
        return max(0, score)


class PuzzleSolver:
    """Manages puzzle solving state and suggestions"""

    def __init__(self, pieces: List[PuzzlePiece]):
        self.pieces = pieces
        self.matcher = PuzzleMatcher(pieces)
        self.solution = {}  # {(row, col): PuzzlePiece}
        self.used = set()  # Set of piece IDs already placed
        self.failed_matches = set()  # Failed match attempts

    def get_best_suggestion(self):
        """Get best next piece suggestion"""
        all_suggestions = []

        # For each placed piece, check all 4 sides
        for (row, col), ref_piece in self.solution.items():
            for drow, dcol, side in [(-1, 0, 0), (0, 1, 1), (1, 0, 2), (0, -1, 3)]:
                neighbor_pos = (row + drow, col + dcol)

                # Skip if position already filled
                if neighbor_pos in self.solution:
                    continue

                # Find compatible pieces
                candidates = self.matcher.find_compatible(ref_piece, side)

                for piece, piece_side, score in candidates:
                    # Skip if piece already used
                    if piece.id in self.used:
                        continue

                    # Skip if this match was already rejected
                    opposite_side = (side + 2) % 4
                    if (ref_piece.id, side, piece.id, opposite_side) in self.failed_matches:
                        continue

                    all_suggestions.append({
                        'position': neighbor_pos,
                        'piece': piece,
                        'side': side,
                        'ref_piece': ref_piece,
                        'score': score
                    })

        if not all_suggestions:
            return None

        return max(all_suggestions, key=lambda x: x['score'])

    def place_piece(self, piece_id: int, pos: Tuple[int, int]):
        """Place a piece at given position"""
        piece = next(p for p in self.pieces if p.id == piece_id)
        self.solution[pos] = piece
        self.used.add(piece_id)

    def reject_match(self, ref_piece_id: int, side: int, piece_id: int):
        """Mark a match as failed"""
        opposite_side = (side + 2) % 4
        self.failed_matches.add((ref_piece_id, side, piece_id, opposite_side))
