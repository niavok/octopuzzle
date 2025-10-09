"""
Octopuzzle - Data Models and Business Logic
Contains: CalibrationData, PuzzlePiece, Detector, Matcher, Solver
"""

import cv2
import numpy as np
import math
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict
from collections import defaultdict


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
    """Analyse the puzzle hole to detect borders and estimate the missing grid."""

    def __init__(self, canny_low=60, canny_high=160):
        self.canny_low = canny_low
        self.canny_high = canny_high

    @staticmethod
    def _cluster_positions(values: List[float], tolerance: float) -> List[int]:
        if not values:
            return []
        values = sorted(values)
        clusters: List[Tuple[float, int]] = []  # (mean, count)
        for val in values:
            if not clusters or abs(val - clusters[-1][0]) > tolerance:
                clusters.append([val, 1])
            else:
                mean, count = clusters[-1]
                new_count = count + 1
                new_mean = (mean * count + val) / new_count
                clusters[-1] = [new_mean, new_count]
        return [int(round(mean)) for mean, _ in clusters]

    def analyze(self, image: np.ndarray, outer_roi: Optional[Tuple[int, int, int, int]],
                inner_roi: Optional[Tuple[int, int, int, int]]) -> Dict[str, object]:
        result: Dict[str, object] = {
            "status": "missing_rois",
            "grid_cells": [],
            "grid_lines": {"vertical": [], "horizontal": []},
            "missing_count": 0,
            "debug_layers": {},
            "border_contour": None,
        }

        if image is None or outer_roi is None or inner_roi is None:
            return result

        x_outer, y_outer, w_outer, h_outer = outer_roi
        x_inner, y_inner, w_inner, h_inner = inner_roi

        x_inner = max(x_outer, x_inner)
        y_inner = max(y_outer, y_inner)
        w_inner = min(w_inner, (x_outer + w_outer) - x_inner)
        h_inner = min(h_inner, (y_outer + h_outer) - y_inner)
        if w_inner <= 0 or h_inner <= 0:
            return result

        outer_crop = image[y_outer : y_outer + h_outer, x_outer : x_outer + w_outer]
        if outer_crop.size == 0:
            return result

        inner_rel = (x_inner - x_outer, y_inner - y_outer, w_inner, h_inner)

        gray_outer = cv2.cvtColor(outer_crop, cv2.COLOR_BGR2GRAY)
        blur_outer = cv2.GaussianBlur(gray_outer, (5, 5), 0)
        outer_mean, outer_std = cv2.meanStdDev(blur_outer)
        outer_sigma = float(outer_std[0][0])
        low_outer = int(max(20, min(120, outer_sigma * 0.75 + 20)))
        high_outer = int(max(low_outer + 40, min(240, outer_sigma * 1.75 + 60)))
        edges_outer = cv2.Canny(blur_outer, low_outer, high_outer)

        ring_mask = np.zeros_like(edges_outer)
        cv2.rectangle(ring_mask, (0, 0), (w_outer - 1, h_outer - 1), 255, thickness=-1)
        cv2.rectangle(
            ring_mask,
            (inner_rel[0], inner_rel[1]),
            (inner_rel[0] + inner_rel[2], inner_rel[1] + inner_rel[3]),
            0,
            thickness=-1,
        )

        border_edges = cv2.bitwise_and(edges_outer, edges_outer, mask=ring_mask)
        kernel = np.ones((3, 3), np.uint8)
        border_edges_clean = cv2.morphologyEx(border_edges, cv2.MORPH_CLOSE, kernel, iterations=2)

        contours, _ = cv2.findContours(border_edges_clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        border_contour_abs = None
        if contours:
            main_contour = max(contours, key=lambda c: cv2.arcLength(c, True))
            border_contour_abs = main_contour + np.array([[[x_outer, y_outer]]])

        inner_crop = image[y_inner : y_inner + h_inner, x_inner : x_inner + w_inner]
        inner_gray = cv2.cvtColor(inner_crop, cv2.COLOR_BGR2GRAY)
        inner_blur = cv2.GaussianBlur(inner_gray, (5, 5), 0)

        _, inner_std = cv2.meanStdDev(inner_blur)
        sigma_inner = float(inner_std[0][0])
        low_inner = int(max(12, min(110, sigma_inner * 1.2 + 15)))
        high_inner = int(max(low_inner + 30, min(220, sigma_inner * 2.3 + 45)))
        edges_inner = cv2.Canny(inner_blur, low_inner, high_inner)

        mean_inner = float(cv2.mean(inner_blur)[0])
        shadow_threshold = max(0, mean_inner - sigma_inner * 0.8 - 5)
        _, shadow_mask = cv2.threshold(inner_blur, shadow_threshold, 255, cv2.THRESH_BINARY_INV)
        edges_inner = cv2.bitwise_and(edges_inner, edges_inner, mask=shadow_mask.astype(np.uint8))
        edges_inner = cv2.morphologyEx(edges_inner, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=1)
        edges_inner = cv2.morphologyEx(edges_inner, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8), iterations=1)

        inner_color_mean = tuple(int(c) for c in cv2.mean(inner_crop)[:3])
        result["mean_color"] = inner_color_mean

        min_line_length = max(20, min(w_inner, h_inner) // 3)
        lines = cv2.HoughLinesP(
            edges_inner,
            rho=1,
            theta=np.pi / 180,
            threshold=60,
            minLineLength=min_line_length,
            maxLineGap=20,
        )

        vertical_positions: List[float] = []
        horizontal_positions: List[float] = []
        if lines is not None:
            for x1, y1, x2, y2 in lines[:, 0]:
                dx = x2 - x1
                dy = y2 - y1
                if dx == 0 and dy == 0:
                    continue
                length = math.hypot(dx, dy)
                if length < min_line_length:
                    continue
                angle = abs(math.degrees(math.atan2(dy, dx)))
                if angle > 90:
                    angle = 180 - angle

                if angle > 65:
                    vertical_positions.append((x1 + x2) / 2.0)
                elif angle < 25:
                    horizontal_positions.append((y1 + y2) / 2.0)

        vertical_lines_rel = [0, w_inner]
        horizontal_lines_rel = [0, h_inner]

        vertical_lines_rel.extend(self._cluster_positions(vertical_positions, tolerance=w_inner * 0.08))
        horizontal_lines_rel.extend(self._cluster_positions(horizontal_positions, tolerance=h_inner * 0.08))

        vertical_lines_rel = sorted(set(int(round(v)) for v in vertical_lines_rel))
        horizontal_lines_rel = sorted(set(int(round(v)) for v in horizontal_lines_rel))

        if len(vertical_lines_rel) < 2:
            vertical_lines_rel = [0, w_inner]
        if len(horizontal_lines_rel) < 2:
            horizontal_lines_rel = [0, h_inner]

        grid_cells: List[Tuple[int, int, int, int]] = []
        for col in range(len(vertical_lines_rel) - 1):
            x_start = vertical_lines_rel[col]
            x_end = vertical_lines_rel[col + 1]
            for row in range(len(horizontal_lines_rel) - 1):
                y_start = horizontal_lines_rel[row]
                y_end = horizontal_lines_rel[row + 1]
                cell_x = x_inner + x_start
                cell_y = y_inner + y_start
                cell_w = max(1, x_end - x_start)
                cell_h = max(1, y_end - y_start)
                grid_cells.append((cell_x, cell_y, cell_w, cell_h))

        missing_count = len(grid_cells)

        debug_layers: Dict[str, np.ndarray] = {}
        border_debug = image.copy()
        if border_contour_abs is not None:
            cv2.drawContours(border_debug, [border_contour_abs], -1, (0, 255, 255), 2, cv2.LINE_AA)
        debug_layers["Contours (bord)"] = border_debug

        border_edges_color = cv2.cvtColor(border_edges_clean, cv2.COLOR_GRAY2BGR)
        border_edges_canvas = np.zeros_like(image)
        border_edges_canvas[y_outer : y_outer + h_outer, x_outer : x_outer + w_outer] = border_edges_color
        debug_layers["Edges anneau"] = border_edges_canvas

        inner_edges_color = cv2.cvtColor(edges_inner, cv2.COLOR_GRAY2BGR)
        inner_edges_canvas = np.zeros_like(image)
        inner_edges_canvas[y_inner : y_inner + h_inner, x_inner : x_inner + w_inner] = inner_edges_color
        debug_layers["Contours internes"] = inner_edges_canvas

        shadow_canvas = np.zeros_like(image)
        shadow_color = cv2.cvtColor(shadow_mask.astype(np.uint8), cv2.COLOR_GRAY2BGR)
        shadow_canvas[y_inner : y_inner + h_inner, x_inner : x_inner + w_inner] = shadow_color
        debug_layers["Masque ombre"] = shadow_canvas

        grid_debug = image.copy()
        for vx in vertical_lines_rel:
            abs_x = x_inner + vx
            cv2.line(grid_debug, (abs_x, y_inner), (abs_x, y_inner + h_inner), (99, 214, 255), 2, cv2.LINE_AA)
        for vy in horizontal_lines_rel:
            abs_y = y_inner + vy
            cv2.line(grid_debug, (x_inner, abs_y), (x_inner + w_inner, abs_y), (99, 214, 255), 2, cv2.LINE_AA)
        debug_layers["Grille estimée"] = grid_debug

        result.update(
            {
                "status": "ok",
                "border_contour": border_contour_abs,
                "grid_cells": grid_cells,
                "grid_lines": {
                    "vertical": [x_inner + int(v) for v in vertical_lines_rel],
                    "horizontal": [y_inner + int(v) for v in horizontal_lines_rel],
                },
                "missing_count": missing_count,
                "debug_layers": debug_layers,
            }
        )

        return result


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
