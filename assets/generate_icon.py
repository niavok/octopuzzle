"""Generate the Octopuzzle icon (PNG + ICO) from scratch.

Usage:
    python assets/generate_icon.py
Requires Pillow (PIL) to be installed.
"""

from pathlib import Path
from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parent


def draw_octopus(base_size: int = 256) -> Image.Image:
    """Create the RGBA image containing the Octopuzzle mascot."""
    img = Image.new("RGBA", (base_size, base_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx, cy = base_size // 2, base_size // 2
    head_radius = int(base_size * 0.34)
    head_color = (112, 99, 211, 255)
    outline_color = (32, 24, 73, 255)

    # Head
    bbox = [cx - head_radius, cy - head_radius, cx + head_radius, cy + head_radius]
    draw.ellipse(bbox, fill=head_color, outline=outline_color, width=6)

    # Eyes
    eye_radius = int(base_size * 0.07)
    eye_offset_x = int(base_size * 0.13)
    eye_offset_y = int(base_size * 0.09)
    pupil_radius = int(base_size * 0.03)
    for dx in (-eye_offset_x, eye_offset_x):
        ex, ey = cx + dx, cy - eye_offset_y
        draw.ellipse([ex - eye_radius, ey - eye_radius, ex + eye_radius, ey + eye_radius], fill=(240, 243, 255, 255))
        draw.ellipse([ex - pupil_radius, ey - pupil_radius, ex + pupil_radius, ey + pupil_radius], fill=outline_color)

    # Tentacles
    num_tentacles = 5
    base_y = cy + head_radius - int(base_size * 0.04)
    tentacle_length = int(base_size * 0.34)
    tentacle_width = int(base_size * 0.15)
    for i in range(num_tentacles):
        center_x = cx - (num_tentacles - 1) * tentacle_width // 2 + i * tentacle_width
        top = base_y
        bottom = top + tentacle_length
        left = center_x - tentacle_width // 2
        right = center_x + tentacle_width // 2
        draw.rounded_rectangle([left, top, right, bottom], radius=tentacle_width // 2, fill=head_color, outline=outline_color, width=4)

    # Puzzle piece (held by middle tentacle)
    piece_size = int(base_size * 0.3)
    piece_x = cx - piece_size // 2
    piece_y = base_y + tentacle_length - piece_size // 2 - int(base_size * 0.05)
    piece_color = (255, 214, 102, 255)
    piece_outline = (182, 140, 46, 255)
    draw.rounded_rectangle([piece_x, piece_y, piece_x + piece_size, piece_y + piece_size], radius=int(piece_size * 0.23), fill=piece_color, outline=piece_outline, width=5)

    tab_width = piece_size // 3
    draw.rounded_rectangle([piece_x + tab_width, piece_y - tab_width // 2, piece_x + 2 * tab_width, piece_y + tab_width // 2], radius=tab_width // 2, fill=piece_color, outline=piece_outline, width=4)
    draw.rounded_rectangle([piece_x + piece_size - tab_width // 2, piece_y + tab_width, piece_x + piece_size + tab_width // 2, piece_y + 2 * tab_width], radius=tab_width // 2, fill=piece_color, outline=piece_outline, width=4)

    # Highlight on head
    highlight_bbox = [cx - head_radius + int(base_size * 0.07), cy - head_radius + int(base_size * 0.04), cx + head_radius - int(base_size * 0.07), cy + head_radius - int(base_size * 0.16)]
    draw.arc(highlight_bbox, start=210, end=330, fill=(255, 255, 255, 140), width=12)

    return img


def main():
    ASSETS.mkdir(exist_ok=True)
    img = draw_octopus()
    png_path = ASSETS / "octopuzzle_icon.png"
    ico_path = ASSETS / "octopuzzle_icon.ico"

    img.save(png_path, format="PNG")
    img.save(ico_path, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"Icon regenerated: {png_path}")


if __name__ == "__main__":
    main()
