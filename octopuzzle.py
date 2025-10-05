"""
Puzzle Solver with Eel Web Interface

File structure:
puzzle_app.py (this file)
web/
  ├── index.html
  ├── style.css
  └── app.js

Install: pip install eel opencv-python numpy
Run: python puzzle_app.py
"""

import eel
import cv2
import numpy as np
import base64
import json
from dataclasses import dataclass, asdict
from typing import List, Tuple, Optional
from collections import defaultdict
import os

# ============================================================================
# DATA STRUCTURES (same as before)
# ============================================================================

@dataclass
class PuzzlePiece:
    id: int
    source_image: str
    bbox_in_source: Tuple[int, int, int, int]
    category: int
    width: float
    height: float
    tabs: List[int]
    
    def to_dict(self):
        return {
            'id': self.id,
            'source_image': self.source_image,
            'bbox': self.bbox_in_source,
            'category': self.category,
            'width': self.width,
            'height': self.height,
            'tabs': self.tabs
        }


class PuzzlePieceDetector:
    def __init__(self, min_area=500, max_area=50000):
        self.min_area = min_area
        self.max_area = max_area
    
    def detect_pieces(self, image_path: str) -> List[PuzzlePiece]:
        img = cv2.imread(image_path)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        pieces = []
        piece_id = 0
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if self.min_area < area < self.max_area:
                piece = self._analyze_piece(contour, piece_id, image_path)
                if piece:
                    pieces.append(piece)
                    piece_id += 1
        
        return pieces
    
    def _analyze_piece(self, contour, piece_id: int, source: str) -> Optional[PuzzlePiece]:
        x, y, w, h = cv2.boundingRect(contour)
        diag = np.sqrt(w**2 + h**2)
        norm_w = w / diag
        norm_h = h / diag
        tabs = self._detect_tabs(contour, x, y, w, h)
        category = self._compute_category(tabs)
        
        return PuzzlePiece(
            id=piece_id,
            source_image=source,
            bbox_in_source=(x, y, w, h),
            category=category,
            width=norm_w,
            height=norm_h,
            tabs=tabs
        )
    
    def _detect_tabs(self, contour, x, y, w, h) -> List[int]:
        tabs = [0, 0, 0, 0]
        contour_points = contour.reshape(-1, 2)
        
        # Top
        top_points = contour_points[contour_points[:, 1] < y + h * 0.3]
        if len(top_points) > 0:
            min_y = top_points[:, 1].min()
            if min_y < y - 2:
                tabs[0] = 1
            elif abs(min_y - y) < 2:
                tabs[0] = 0
            else:
                tabs[0] = -1
        
        # Right
        right_points = contour_points[contour_points[:, 0] > x + w * 0.7]
        if len(right_points) > 0:
            max_x = right_points[:, 0].max()
            if max_x > x + w + 2:
                tabs[1] = 1
            elif abs(max_x - (x + w)) < 2:
                tabs[1] = 0
            else:
                tabs[1] = -1
        
        # Bottom
        bottom_points = contour_points[contour_points[:, 1] > y + h * 0.7]
        if len(bottom_points) > 0:
            max_y = bottom_points[:, 1].max()
            if max_y > y + h + 2:
                tabs[2] = 1
            elif abs(max_y - (y + h)) < 2:
                tabs[2] = 0
            else:
                tabs[2] = -1
        
        # Left
        left_points = contour_points[contour_points[:, 0] < x + w * 0.3]
        if len(left_points) > 0:
            min_x = left_points[:, 0].min()
            if min_x < x - 2:
                tabs[3] = 1
            elif abs(min_x - x) < 2:
                tabs[3] = 0
            else:
                tabs[3] = -1
        
        return tabs
    
    def _compute_category(self, tabs: List[int]) -> int:
        binary = ''.join(['1' if t != 0 else '0' for t in tabs])
        count = binary.count('1')
        
        if count == 0:
            return 0
        elif count == 1:
            return 1
        elif count == 2:
            if tabs[0] != 0 and tabs[2] != 0:
                return 3
            elif tabs[1] != 0 and tabs[3] != 0:
                return 3
            else:
                return 2
        elif count == 3:
            return 4
        else:
            return 5


class PuzzleMatcher:
    def __init__(self, pieces: List[PuzzlePiece]):
        self.pieces = pieces
        self.by_category = defaultdict(list)
        for piece in pieces:
            self.by_category[piece.category].append(piece)
    
    def find_compatible(self, piece: PuzzlePiece, side: int) -> List[Tuple[PuzzlePiece, int, float]]:
        target_tab = piece.tabs[side]
        if target_tab == 0:
            return []
        
        compatible = []
        opposite_side = (side + 2) % 4
        required_tab = -target_tab
        
        for candidate in self.pieces:
            if candidate.id == piece.id:
                continue
            
            for cand_side in range(4):
                if candidate.tabs[cand_side] == required_tab:
                    score = self._compute_match_score(piece, side, candidate, cand_side)
                    if score > 0:
                        compatible.append((candidate, cand_side, score))
        
        compatible.sort(key=lambda x: x[2], reverse=True)
        return compatible
    
    def _compute_match_score(self, p1: PuzzlePiece, s1: int, p2: PuzzlePiece, s2: int) -> float:
        if s1 in [0, 2]:
            size_diff = abs(p1.width - p2.width)
        else:
            size_diff = abs(p1.height - p2.height)
        
        if size_diff > 0.15:
            return 0.0
        
        score = 1.0 - size_diff * 5
        return max(0, score)


class PuzzleSolver:
    def __init__(self, pieces: List[PuzzlePiece]):
        self.pieces = pieces
        self.matcher = PuzzleMatcher(pieces)
        self.solution = {}
        self.used = set()
        self.failed_matches = set()
    
    def get_best_suggestion(self):
        all_suggestions = []
        
        for (row, col), ref_piece in self.solution.items():
            for drow, dcol, side in [(-1, 0, 0), (0, 1, 1), (1, 0, 2), (0, -1, 3)]:
                neighbor_pos = (row + drow, col + dcol)
                
                if neighbor_pos in self.solution:
                    continue
                
                candidates = self.matcher.find_compatible(ref_piece, side)
                
                for piece, piece_side, score in candidates:
                    if piece.id in self.used:
                        continue
                    
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
        piece = next(p for p in self.pieces if p.id == piece_id)
        self.solution[pos] = piece
        self.used.add(piece_id)
    
    def reject_match(self, ref_piece_id: int, side: int, piece_id: int):
        opposite_side = (side + 2) % 4
        self.failed_matches.add((ref_piece_id, side, piece_id, opposite_side))


# ============================================================================
# EEL WEB INTERFACE
# ============================================================================

# Global state
detector = None
solver = None
images_cache = {}

def image_to_base64(image_path: str, bbox: Optional[Tuple[int, int, int, int]] = None, 
                    highlight_color: Tuple[int, int, int] = (0, 255, 0)) -> str:
    """Convert image to base64 with optional bounding box highlight"""
    img = cv2.imread(image_path)
    
    if bbox:
        x, y, w, h = bbox
        cv2.rectangle(img, (x, y), (x + w, y + h), highlight_color, 3)
        
        # Add piece ID label
        cv2.rectangle(img, (x, y - 30), (x + 100, y), highlight_color, -1)
    
    _, buffer = cv2.imencode('.jpg', img)
    img_base64 = base64.b64encode(buffer).decode('utf-8')
    return f"data:image/jpeg;base64,{img_base64}"


@eel.expose
def load_images(image_paths: List[str]):
    """Load and detect pieces from images"""
    global detector, solver, images_cache
    
    detector = PuzzlePieceDetector(min_area=500, max_area=20000)
    all_pieces = []
    
    for img_path in image_paths:
        if not os.path.exists(img_path):
            continue
        
        pieces = detector.detect_pieces(img_path)
        all_pieces.extend(pieces)
        images_cache[img_path] = cv2.imread(img_path)
    
    solver = PuzzleSolver(all_pieces)
    
    # Place first piece
    if all_pieces:
        solver.place_piece(all_pieces[0].id, (0, 0))
    
    return {
        'total_pieces': len(all_pieces),
        'pieces': [p.to_dict() for p in all_pieces]
    }


@eel.expose
def get_suggestion():
    """Get next piece suggestion"""
    if not solver:
        return None
    
    suggestion = solver.get_best_suggestion()
    
    if not suggestion:
        return None
    
    piece = suggestion['piece']
    ref_piece = suggestion['ref_piece']
    
    # Generate images with highlights
    piece_img = image_to_base64(piece.source_image, piece.bbox_in_source, (0, 255, 0))
    ref_img = image_to_base64(ref_piece.source_image, ref_piece.bbox_in_source, (255, 0, 0))
    
    side_names = ['TOP', 'RIGHT', 'BOTTOM', 'LEFT']
    
    return {
        'piece': piece.to_dict(),
        'piece_image': piece_img,
        'ref_piece': ref_piece.to_dict(),
        'ref_image': ref_img,
        'side_name': side_names[suggestion['side']],
        'side': suggestion['side'],
        'score': suggestion['score'],
        'progress': {
            'placed': len(solver.used),
            'total': len(solver.pieces)
        }
    }


@eel.expose
def submit_feedback(piece_id: int, ref_piece_id: int, side: int, fits: bool, position: list):
    """Handle user feedback on suggested match"""
    if not solver:
        return False
    
    if fits:
        solver.place_piece(piece_id, tuple(position))
    else:
        solver.reject_match(ref_piece_id, side, piece_id)
    
    return True


@eel.expose
def get_stats():
    """Get current solving statistics"""
    if not solver:
        return {}
    
    return {
        'placed': len(solver.used),
        'total': len(solver.pieces),
        'remaining': len(solver.pieces) - len(solver.used),
        'failed_attempts': len(solver.failed_matches)
    }


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    eel.init('web')
    eel.start('index.html', size=(1400, 900), port=8080)