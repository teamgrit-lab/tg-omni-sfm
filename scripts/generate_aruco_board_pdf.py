"""
Generate an A4 PDF marker board from a JSON spec.
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np
from PIL import Image


def meters_to_pixels(value_m: float, dpi: int) -> int:
    return int(round(value_m / 0.0254 * dpi))


def load_board_spec(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if "marker_length" not in data:
        raise ValueError("board spec missing marker_length")
    if "page" not in data or "width_m" not in data["page"] or "height_m" not in data["page"]:
        raise ValueError("board spec missing page width/height")
    if "markers" not in data or not data["markers"]:
        raise ValueError("board spec has no markers")
    return data


def get_aruco_dictionary(dict_name: str):
    if not hasattr(cv2, "aruco"):
        raise ImportError(
            "cv2.aruco not available. Install opencv-contrib-python to generate markers."
        )
    try:
        dict_id = getattr(cv2.aruco, dict_name)
    except AttributeError as exc:
        raise ValueError(f"Unknown ArUco dictionary: {dict_name}") from exc
    if hasattr(cv2.aruco, "getPredefinedDictionary"):
        return cv2.aruco.getPredefinedDictionary(dict_id)
    return cv2.aruco.Dictionary_get(dict_id)


def draw_marker(aruco_dict, marker_id: int, size_px: int, border_bits: int) -> np.ndarray:
    if hasattr(cv2.aruco, "generateImageMarker"):
        return cv2.aruco.generateImageMarker(aruco_dict, marker_id, size_px, border_bits)
    image = np.zeros((size_px, size_px), dtype=np.uint8)
    cv2.aruco.drawMarker(aruco_dict, marker_id, size_px, image, borderBits=border_bits)
    return image


def place_marker(
    canvas: np.ndarray,
    marker: np.ndarray,
    center_px: Tuple[int, int],
) -> None:
    height, width = canvas.shape[:2]
    size = marker.shape[0]
    x_center, y_center = center_px
    x0 = int(round(x_center - size / 2))
    y0 = int(round(y_center - size / 2))
    x1 = x0 + size
    y1 = y0 + size
    if x0 < 0 or y0 < 0 or x1 > width or y1 > height:
        raise ValueError("Marker placement exceeds page bounds.")
    canvas[y0:y1, x0:x1] = marker


def build_board_image(
    spec: dict, dpi: int, border_bits: int
) -> Tuple[np.ndarray, Dict[int, List[float]]]:
    page_width_m = float(spec["page"]["width_m"])
    page_height_m = float(spec["page"]["height_m"])
    marker_length_m = float(spec["marker_length"])
    marker_dict_name = spec.get("marker_dict", "DICT_4X4_50")

    width_px = meters_to_pixels(page_width_m, dpi)
    height_px = meters_to_pixels(page_height_m, dpi)
    marker_size_px = meters_to_pixels(marker_length_m, dpi)

    canvas = np.full((height_px, width_px), 255, dtype=np.uint8)
    aruco_dict = get_aruco_dictionary(marker_dict_name)

    markers_m: Dict[int, List[float]] = {}
    for entry in spec["markers"]:
        marker_id = int(entry["id"])
        center_m = entry.get("center_m") or entry.get("center")
        if center_m is None:
            raise ValueError(f"Marker {marker_id} missing center_m")
        center_x_m = float(center_m[0])
        center_y_m = float(center_m[1])
        markers_m[marker_id] = [center_x_m, center_y_m, float(center_m[2]) if len(center_m) > 2 else 0.0]

        center_x_px = meters_to_pixels(center_x_m, dpi)
        center_y_px = meters_to_pixels(center_y_m, dpi)
        # PDF origin is bottom-left; image origin is top-left
        center_y_px = height_px - center_y_px

        marker_img = draw_marker(aruco_dict, marker_id, marker_size_px, border_bits)
        place_marker(canvas, marker_img, (center_x_px, center_y_px))

    return canvas, markers_m


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate ArUco marker board PDF")
    parser.add_argument(
        "--board_spec",
        type=Path,
        required=True,
        help="Path to board spec JSON",
    )
    parser.add_argument(
        "--output_pdf",
        type=Path,
        required=True,
        help="Output PDF path",
    )
    parser.add_argument(
        "--output_png",
        type=Path,
        default=None,
        help="Optional output PNG path for preview",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="DPI used for rasterization",
    )
    parser.add_argument(
        "--border_bits",
        type=int,
        default=1,
        help="Border bits for each marker",
    )
    args = parser.parse_args()

    spec = load_board_spec(args.board_spec)
    canvas, _ = build_board_image(spec, args.dpi, args.border_bits)

    image = Image.fromarray(canvas).convert("L")
    args.output_pdf.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output_pdf, "PDF", resolution=args.dpi)

    if args.output_png:
        args.output_png.parent.mkdir(parents=True, exist_ok=True)
        image.save(args.output_png)

    print(f"PDF saved to: {args.output_pdf}")
    if args.output_png:
        print(f"PNG saved to: {args.output_png}")


if __name__ == "__main__":
    main()
