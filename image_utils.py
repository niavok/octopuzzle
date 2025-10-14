"""
Image utilities for Octopuzzle
Handles conversions between OpenCV, PIL, and Tk-compatible formats
"""

import cv2
import numpy as np
from PIL import Image, ImageTk
from typing import Tuple, Optional, List, Dict
import tempfile
import os


class ImageCache:
    """Cache for loaded images to avoid repeated file I/O"""

    def __init__(self):
        self._cache = {}  # {path: cv2_image}
        self._temp_files = []  # Track temp files for cleanup

    def load(self, path: str) -> Optional[np.ndarray]:
        """Load image from cache or file"""
        if path in self._cache:
            return self._cache[path]

        img = cv2.imread(path)
        if img is not None:
            self._cache[path] = img
        return img

    def store(self, img: np.ndarray, prefix="temp_") -> str:
        """Store image to temp file and cache it"""
        temp_path = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg', prefix=prefix).name
        cv2.imwrite(temp_path, img)
        self._cache[temp_path] = img
        self._temp_files.append(temp_path)
        return temp_path

    def cleanup(self):
        """Remove all temp files"""
        for path in self._temp_files:
            try:
                os.unlink(path)
            except:
                pass
        self._temp_files.clear()
        self._cache.clear()


# Global image cache
image_cache = ImageCache()


def cv2_to_photoimage(
    cv_img: np.ndarray,
    max_width: int = None,
    max_height: int = None,
    scale: Optional[float] = None,
) -> Tuple[ImageTk.PhotoImage, int, int]:
    """
    Convert OpenCV image to a Tk PhotoImage
    Returns: (PhotoImage, display_width, display_height)
    """
    if cv_img is None:
        return None, 0, 0

    # Convert BGR to RGB
    rgb_img = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)

    # Get original dimensions
    height, width = rgb_img.shape[:2]
    display_width, display_height = width, height

    # Resize if needed
    if scale is not None:
        if scale <= 0:
            raise ValueError("scale must be positive")
        display_width = max(1, int(round(width * scale)))
        display_height = max(1, int(round(height * scale)))
        if scale < 1.0:
            interpolation = cv2.INTER_AREA
        else:
            interpolation = cv2.INTER_NEAREST
        rgb_img = cv2.resize(rgb_img, (display_width, display_height), interpolation=interpolation)
    elif max_width or max_height:
        resize_scale = 1.0
        if max_width and width > max_width:
            resize_scale = min(resize_scale, max_width / width)
        if max_height and height > max_height:
            resize_scale = min(resize_scale, max_height / height)

        if resize_scale < 1.0:
            display_width = int(width * resize_scale)
            display_height = int(height * resize_scale)
            rgb_img = cv2.resize(rgb_img, (display_width, display_height), interpolation=cv2.INTER_AREA)

    # Convert to PIL Image
    pil_img = Image.fromarray(rgb_img)

    # Convert to PhotoImage
    photo = ImageTk.PhotoImage(pil_img)

    return photo, display_width, display_height


def _apply_roi_overlay(img: np.ndarray, roi: Tuple[int, int, int, int],
                       color: Tuple[int, int, int], thickness: int = 4) -> np.ndarray:
    """Utility to draw a single ROI overlay with provided color and thickness."""
    x, y, w, h = roi

    overlay = img.copy()

    overlay[:y, :] = overlay[:y, :] * 0.55
    overlay[y:y+h, :x] = overlay[y:y+h, :x] * 0.55
    overlay[y:y+h, x+w:] = overlay[y:y+h, x+w:] * 0.55
    overlay[y+h:, :] = overlay[y+h:, :] * 0.55

    cv2.addWeighted(overlay, 0.65, img, 0.35, 0, img)

    cv2.rectangle(img, (x, y), (x+w, y+h), color, thickness)

    marker_size = 12
    cv2.line(img, (x, y), (x + marker_size, y), color, thickness)
    cv2.line(img, (x, y), (x, y + marker_size), color, thickness)
    cv2.line(img, (x + w, y), (x + w - marker_size, y), color, thickness)
    cv2.line(img, (x + w, y), (x + w, y + marker_size), color, thickness)
    cv2.line(img, (x, y + h), (x + marker_size, y + h), color, thickness)
    cv2.line(img, (x, y + h), (x, y + h - marker_size), color, thickness)
    cv2.line(img, (x + w, y + h), (x + w - marker_size, y + h), color, thickness)
    cv2.line(img, (x + w, y + h), (x + w, y + h - marker_size), color, thickness)

    return img


def draw_roi_overlay(cv_img: np.ndarray, roi: Optional[Tuple[int, int, int, int]],
                     secondary_roi: Optional[Tuple[int, int, int, int]] = None) -> np.ndarray:
    """
    Draw one or two ROI overlays on the image.
    The primary ROI uses the accent color, the secondary ROI uses cyan.
    """
    if cv_img is None:
        return cv_img

    img = cv_img.copy()
    if roi:
        img = _apply_roi_overlay(img, roi, (99, 102, 241), thickness=5)

    if secondary_roi:
        img = _apply_roi_overlay(img, secondary_roi, (99, 214, 255), thickness=4)

    return img


def draw_selection_rect(cv_img: np.ndarray, x: int, y: int, w: int, h: int,
                        color=(66, 135, 245), thickness=2) -> np.ndarray:
    """
    Draw selection rectangle on image (for real-time drag feedback)
    Returns: new image with rectangle
    """
    if cv_img is None:
        return None

    img = cv_img.copy()
    cv2.rectangle(img, (x, y), (x+w, y+h), color, thickness)
    return img


def get_background_color(cv_img: np.ndarray, roi: Tuple[int, int, int, int]) -> Tuple[int, int, int]:
    """
    Get average background color from ROI
    Returns: (B, G, R) tuple
    """
    if cv_img is None or roi is None:
        return None

    x, y, w, h = roi
    roi_img = cv_img[y:y+h, x:x+w]

    # Calculate average color in BGR
    avg_color = cv2.mean(roi_img)[:3]

    return tuple(int(c) for c in avg_color)


def draw_piece_highlight(cv_img: np.ndarray, bbox: Tuple[int, int, int, int],
                        color=(0, 255, 0), label: str = "") -> np.ndarray:
    """
    Draw highlight around piece with optional label
    Returns: new image with highlight
    """
    if cv_img is None or bbox is None:
        return cv_img

    img = cv_img.copy()
    x, y, w, h = bbox

    # Draw rectangle
    cv2.rectangle(img, (x, y), (x+w, y+h), color, 3)

    # Draw label if provided
    if label:
        # Background for text
        cv2.rectangle(img, (x, y-30), (x+100, y), color, -1)
        # Text
        cv2.putText(img, label, (x+5, y-8),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    return img


def draw_grid_overlay(cv_img: np.ndarray, grid_cells: List[Tuple[int, int, int, int]],
                      vertical_lines: List[int], horizontal_lines: List[int],
                      color: Tuple[int, int, int] = (99, 214, 255)) -> np.ndarray:
    """
    Draw an estimated grid overlay on the provided image.
    """
    if cv_img is None:
        return cv_img

    img = cv_img.copy()
    for x in vertical_lines:
        cv2.line(img, (x, 0), (x, img.shape[0]), color, 2, lineType=cv2.LINE_AA)
    for y in horizontal_lines:
        cv2.line(img, (0, y), (img.shape[1], y), color, 2, lineType=cv2.LINE_AA)

    for idx, (x, y, w, h) in enumerate(grid_cells, start=1):
        cv2.rectangle(img, (x, y), (x + w, y + h), color, 2, lineType=cv2.LINE_AA)
        cv2.putText(img, str(idx), (x + 8, y + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 1, cv2.LINE_AA)

    return img


def resize_to_fit(cv_img: np.ndarray, max_width: int, max_height: int) -> np.ndarray:
    """
    Resize image to fit within max dimensions while preserving aspect ratio
    Returns: resized image
    """
    if cv_img is None:
        return None

    height, width = cv_img.shape[:2]

    # Calculate scale
    scale = 1.0
    if width > max_width:
        scale = min(scale, max_width / width)
    if height > max_height:
        scale = min(scale, max_height / height)

    if scale < 1.0:
        new_width = int(width * scale)
        new_height = int(height * scale)
        return cv2.resize(cv_img, (new_width, new_height))

    return cv_img


def extract_piece_image(source_path: str, bbox: Tuple[int, int, int, int],
                       highlight_color=(0, 255, 0)) -> Optional[np.ndarray]:
    """
    Extract and highlight a piece from source image
    Returns: image with piece highlighted
    """
    img = image_cache.load(source_path)
    if img is None:
        return None

    # Draw highlight
    return draw_piece_highlight(img, bbox, highlight_color)
