"""
Generate printable ArUco markers as PNG images or a single PDF.
"""

import argparse
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np
from PIL import Image


def parse_marker_ids(value: Optional[str]) -> List[int]:
    if not value:
        return []
    ids: List[int] = []
    for token in value.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            start, end = token.split("-", maxsplit=1)
            ids.extend(range(int(start), int(end) + 1))
        else:
            ids.append(int(token))
    return sorted(set(ids))


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


def create_markers_pdf(
    aruco_dict,
    marker_ids: List[int],
    output_path: Path,
    marker_size_px: int = 800,
    border_bits: int = 1,
    markers_per_row: int = 3,
    dpi: int = 300,
) -> None:
    """Create a single PDF with multiple markers arranged in a grid."""
    # Generate all marker images
    marker_images = []
    for marker_id in marker_ids:
        marker_img = draw_marker(aruco_dict, marker_id, marker_size_px, border_bits)
        marker_images.append((marker_id, marker_img))
    
    # Calculate grid dimensions
    num_markers = len(marker_images)
    num_rows = (num_markers + markers_per_row - 1) // markers_per_row
    
    # A4 size at given DPI (210mm x 297mm)
    a4_width_px = int(210 / 25.4 * dpi)
    a4_height_px = int(297 / 25.4 * dpi)
    
    # Calculate marker size to fit on page with padding
    padding = int(0.5 / 25.4 * dpi)  # 0.5 inch padding
    available_width = a4_width_px - (2 * padding)
    available_height = a4_height_px - (2 * padding)
    
    marker_cell_width = available_width // markers_per_row
    marker_cell_height = available_height // num_rows
    marker_display_size = min(marker_cell_width, marker_cell_height) - padding
    
    # Create white canvas
    canvas = np.ones((a4_height_px, a4_width_px), dtype=np.uint8) * 255
    
    # Place markers on canvas
    for idx, (marker_id, marker_img) in enumerate(marker_images):
        row = idx // markers_per_row
        col = idx % markers_per_row
        
        # Resize marker to fit
        resized_marker = cv2.resize(marker_img, (marker_display_size, marker_display_size))
        
        # Calculate position (centered in cell)
        x_offset = padding + col * marker_cell_width + (marker_cell_width - marker_display_size) // 2
        y_offset = padding + row * marker_cell_height + (marker_cell_height - marker_display_size) // 2
        
        # Place marker
        canvas[y_offset:y_offset + marker_display_size, 
               x_offset:x_offset + marker_display_size] = resized_marker
        
        # Add label below marker
        label = f"ID: {marker_id}"
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.8
        thickness = 2
        text_size = cv2.getTextSize(label, font, font_scale, thickness)[0]
        text_x = x_offset + (marker_display_size - text_size[0]) // 2
        text_y = y_offset + marker_display_size + text_size[1] + 10
        cv2.putText(canvas, label, (text_x, text_y), font, font_scale, 0, thickness)
    
    # Convert to PIL and save as PDF
    pil_image = Image.fromarray(canvas)
    pil_image.save(output_path, "PDF", resolution=dpi)
    print(f"Created PDF with {len(marker_images)} markers: {output_path}")



def main() -> None:
    parser = argparse.ArgumentParser(description="Generate ArUco marker PNGs")
    parser.add_argument(
        "--output_dir",
        type=Path,
        default=Path("assets/markers"),
        help="Directory to write marker PNGs",
    )
    parser.add_argument(
        "--marker_dict",
        type=str,
        default="DICT_4X4_50",
        help="ArUco dictionary name",
    )
    parser.add_argument(
        "--marker_ids",
        type=str,
        default="0-5",
        help="Marker IDs (e.g. 0-5 or 0,1,2,3)",
    )
    parser.add_argument(
        "--size_px",
        type=int,
        default=800,
        help="Marker image size in pixels",
    )
    parser.add_argument(
        "--border_bits",
        type=int,
        default=1,
        help="Border bits for the marker",
    )
    parser.add_argument(
        "--pdf",
        action="store_true",
        help="Generate a single PDF instead of individual PNGs",
    )
    parser.add_argument(
        "--pdf_output",
        type=Path,
        default=Path("assets/markers/aruco_markers.pdf"),
        help="Output path for PDF file",
    )
    parser.add_argument(
        "--markers_per_row",
        type=int,
        default=3,
        help="Number of markers per row in PDF",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="DPI for PDF output",
    )
    args = parser.parse_args()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    aruco_dict = get_aruco_dictionary(args.marker_dict)
    marker_ids = parse_marker_ids(args.marker_ids)

    if not marker_ids:
        raise ValueError("No marker IDs specified.")

    if args.pdf:
        # Generate PDF with all markers
        create_markers_pdf(
            aruco_dict,
            marker_ids,
            args.pdf_output,
            marker_size_px=args.size_px,
            border_bits=args.border_bits,
            markers_per_row=args.markers_per_row,
            dpi=args.dpi,
        )
    else:
        # Generate individual PNG files
        for marker_id in marker_ids:
            image = draw_marker(aruco_dict, marker_id, args.size_px, args.border_bits)
            output_path = output_dir / f"{args.marker_dict}_id{marker_id}.png"
            if not cv2.imwrite(str(output_path), image):
                raise RuntimeError(f"Failed to write marker image: {output_path}")
        print(f"Generated {len(marker_ids)} markers in {output_dir}")


if __name__ == "__main__":
    main()
