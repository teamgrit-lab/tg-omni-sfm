"""
Generate printable ArUco markers as PNG images.
"""

import argparse
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np


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
    args = parser.parse_args()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    aruco_dict = get_aruco_dictionary(args.marker_dict)
    marker_ids = parse_marker_ids(args.marker_ids)

    if not marker_ids:
        raise ValueError("No marker IDs specified.")

    for marker_id in marker_ids:
        image = draw_marker(aruco_dict, marker_id, args.size_px, args.border_bits)
        output_path = output_dir / f"{args.marker_dict}_id{marker_id}.png"
        if not cv2.imwrite(str(output_path), image):
            raise RuntimeError(f"Failed to write marker image: {output_path}")
    print(f"Generated {len(marker_ids)} markers in {output_dir}")


if __name__ == "__main__":
    main()
