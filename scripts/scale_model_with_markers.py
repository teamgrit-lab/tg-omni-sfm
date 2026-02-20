"""
Scale a COLMAP reconstruction using ArUco marker observations.
"""

import argparse
from pathlib import Path

from typing import List, Optional

import pycolmap

from src.marker_scale import (
    MarkerScaleConfig,
    apply_scale_to_reconstruction,
    collect_marker_observations,
    estimate_scale_from_board_distances,
    estimate_scale_from_observations,
    load_marker_board_spec,
    write_scale_report,
)


def parse_marker_ids(value: Optional[str]) -> Optional[List[int]]:
    if not value:
        return None
    ids = [int(item.strip()) for item in value.split(",") if item.strip()]
    return ids or None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scale a COLMAP model using ArUco markers"
    )
    parser.add_argument(
        "--model_path",
        type=Path,
        required=True,
        help="Path to COLMAP model (sparse/0)",
    )
    parser.add_argument(
        "--image_path",
        type=Path,
        required=True,
        help="Path to input images directory",
    )
    parser.add_argument(
        "--camera_config",
        type=Path,
        required=True,
        help="Path to camera_params.json",
    )
    parser.add_argument(
        "--output_path",
        type=Path,
        required=True,
        help="Output path for scaled model",
    )
    parser.add_argument(
        "--marker_length",
        type=float,
        required=False,
        help="Marker size in meters",
    )
    parser.add_argument(
        "--marker_dict",
        type=str,
        default=None,
        help="ArUco dictionary name",
    )
    parser.add_argument(
        "--marker_ids",
        type=str,
        default=None,
        help="Comma-separated marker IDs to use (default: all)",
    )
    parser.add_argument(
        "--marker_min_observations",
        type=int,
        default=2,
        help="Minimum observations per marker",
    )
    parser.add_argument(
        "--marker_image_stride",
        type=int,
        default=1,
        help="Process every Nth image for marker detection",
    )
    parser.add_argument(
        "--marker_max_images",
        type=int,
        default=None,
        help="Maximum number of images to process for markers",
    )
    parser.add_argument(
        "--report_path",
        type=Path,
        default=None,
        help="Output path for marker scale report (file or directory)",
    )
    parser.add_argument(
        "--marker_board_spec",
        type=Path,
        default=None,
        help="Path to marker board spec JSON (enables board distance scaling)",
    )
    args = parser.parse_args()

    reconstruction = pycolmap.Reconstruction(args.model_path)
    board_spec = None
    if args.marker_board_spec:
        board_spec = load_marker_board_spec(args.marker_board_spec)

    marker_dict = args.marker_dict
    marker_length = args.marker_length
    marker_ids = parse_marker_ids(args.marker_ids)
    if board_spec:
        if marker_dict is None:
            marker_dict = board_spec.marker_dict
        if marker_length is None:
            marker_length = board_spec.marker_length
        if marker_ids is None:
            marker_ids = sorted(board_spec.markers_m.keys())
    if marker_length is None:
        raise RuntimeError("marker_length is required when no board spec is provided.")

    marker_config = MarkerScaleConfig(
        marker_length=marker_length,
        marker_dict=marker_dict or "DICT_4X4_50",
        marker_ids=marker_ids,
        min_observations=args.marker_min_observations,
        image_stride=args.marker_image_stride,
        max_images=args.marker_max_images,
    )
    observations, detection_summary = collect_marker_observations(
        args.image_path, args.camera_config, marker_config
    )
    if not observations:
        raise RuntimeError("No marker observations found.")

    if board_spec:
        scale_result = estimate_scale_from_board_distances(
            reconstruction, observations, board_spec, marker_config.min_observations
        )
    else:
        scale_result = estimate_scale_from_observations(
            reconstruction, observations, marker_config.min_observations
        )
    if scale_result is None:
        raise RuntimeError("Marker scale estimation failed.")

    apply_scale_to_reconstruction(reconstruction, scale_result.scale_meter_per_sfm)
    args.output_path.mkdir(parents=True, exist_ok=True)
    reconstruction.write(args.output_path)

    report_path = args.report_path
    if report_path is None:
        report_path = args.output_path / "marker_scale_report.json"
    elif report_path.suffix == "":
        report_path = report_path / "marker_scale_report.json"
    write_scale_report(report_path, scale_result, detection_summary, marker_config, board_spec)
    print(f"Scaled model written to: {args.output_path}")
    print(f"Scale report: {report_path}")


if __name__ == "__main__":
    main()
