"""
An example for running incremental SfM on 360 spherical panorama images.
"""

import argparse
import json
import os
from pathlib import Path
from typing import List, Optional

import numpy as np
import pycolmap
from pycolmap import logging


def read_json_config(config_path: Path) -> dict:
    """Read a JSON configuration file."""
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_marker_ids(value: Optional[str]) -> Optional[List[int]]:
    if not value:
        return None
    ids = [int(item.strip()) for item in value.split(",") if item.strip()]
    return ids or None


def create_rig_config(
    input_rig_config: dict,
    input_camera_config: dict,
    camera_model: str = "PINHOLE",
) -> pycolmap.RigConfig:
    """Create a RigConfig for the given virtual rotations."""
    rig_cameras = []
    # first img
    first_image = input_camera_config[0]
    camera = pycolmap.Camera(
        camera_id=0,
        model=camera_model,
        params=[
            first_image["fx"],
            first_image["fy"],
            first_image["cx"],
            first_image["cy"],
        ],
        width=first_image["width"],
        height=first_image["height"],
    )
    for idx, params in enumerate(input_rig_config[0]["cameras"]):
        ref_sensor = params.get("ref_sensor", False)
        if ref_sensor:
            cam_from_rig = None
        else:
            wxyz = params["cam_from_rig_rotation"]
            cam_from_ref_rotation = pycolmap.Rotation3d([wxyz[1], wxyz[2], wxyz[3], wxyz[0]])
            cam_from_rig = pycolmap.Rigid3d(cam_from_ref_rotation, np.zeros(3))

        rig_camera = pycolmap.RigConfigCamera(
            {
                "ref_sensor": ref_sensor,
                "image_prefix": params["image_prefix"],
                "cam_from_rig": cam_from_rig,
            }
        )
        # Create a camera for each rig camera
        camera.camera_id = idx
        rig_camera.camera = camera
        rig_cameras.append(rig_camera)

    return pycolmap.RigConfig(cameras=rig_cameras)


def run(args: argparse.Namespace) -> None:
    # Define the paths.
    input_image_path = args.input_image_path
    database_path = args.output_path / "database.db"
    if database_path.exists():
        database_path.unlink()

    rec_path = args.output_path / "sparse"
    rec_path.mkdir(exist_ok=True, parents=True)

    input_camera_config = read_json_config(args.input_camera_config)
    input_rig_config = read_json_config(args.input_rig_config)
    rig_config = create_rig_config(input_rig_config, input_camera_config)
    image_names = [os.path.join(p["image_prefix"], p["image_name"]) for p in input_camera_config]
    pycolmap.set_random_seed(0)
    pycolmap.extract_features(
        database_path,
        input_image_path,
        # image_names,
        # reader_options={"mask_path": mask_dir},
        camera_mode=pycolmap.CameraMode.PER_FOLDER,
    )

    with pycolmap.Database(database_path) as db:
        pycolmap.apply_rig_config([rig_config], db)

    if args.matcher == "sequential":
        pycolmap.match_sequential(
            database_path,
            matching_options=pycolmap.SequentialMatchingOptions(loop_detection=True),
        )
    elif args.matcher == "exhaustive":
        pycolmap.match_exhaustive(database_path)
    elif args.matcher == "vocabtree":
        pycolmap.match_vocabtree(database_path)
    elif args.matcher == "spatial":
        pycolmap.match_spatial(database_path)
    else:
        logging.fatal(f"Unknown matcher: {args.matcher}")

    opts = pycolmap.IncrementalPipelineOptions(
        ba_refine_sensor_from_rig=False,
        ba_refine_focal_length=False,
        ba_refine_principal_point=False,
        ba_refine_extra_params=False,
    )
    recs = pycolmap.incremental_mapping(database_path, input_image_path, rec_path, opts)
    marker_payload = None
    if args.marker_length is not None:
        try:
            from src.marker_scale import (
                MarkerScaleConfig,
                apply_scale_to_reconstruction,
                collect_marker_observations,
                estimate_scale_from_observations,
                write_scale_report,
            )
        except ImportError as exc:
            logging.error(f"Marker scaling unavailable: {exc}")
        else:
            marker_config = MarkerScaleConfig(
                marker_length=args.marker_length,
                marker_dict=args.marker_dict,
                marker_ids=parse_marker_ids(args.marker_ids),
                min_observations=args.marker_min_observations,
                image_stride=args.marker_image_stride,
                max_images=args.marker_max_images,
            )
            try:
                observations, detection_summary = collect_marker_observations(
                    input_image_path, args.input_camera_config, marker_config
                )
            except ImportError as exc:
                logging.error(f"Marker detection unavailable: {exc}")
                observations = []
                detection_summary = {}
            if not observations:
                logging.warning("No marker observations found. Skipping marker scaling.")
            else:
                marker_payload = (
                    marker_config,
                    observations,
                    detection_summary,
                    apply_scale_to_reconstruction,
                    estimate_scale_from_observations,
                    write_scale_report,
                )

    for idx, rec in recs.items():
        logging.info(f"#{idx} {rec.summary()}")
        if not marker_payload:
            continue

        (
            marker_config,
            observations,
            detection_summary,
            apply_scale,
            estimate_scale,
            write_report,
        ) = marker_payload
        scale_result = estimate_scale(rec, observations, marker_config.min_observations)
        if scale_result is None:
            logging.warning("Marker scale estimation failed. Skipping scaling output.")
            continue

        apply_scale(rec, scale_result.scale_meter_per_sfm)
        scaled_dir = rec_path / f"{idx}_{args.marker_scaled_suffix}"
        scaled_dir.mkdir(parents=True, exist_ok=True)
        rec.write(scaled_dir)

        report_path = args.marker_report_path
        if report_path is None:
            report_path = scaled_dir / "marker_scale_report.json"
        elif report_path.suffix == "":
            report_path = report_path / f"marker_scale_{idx}.json"
        write_report(report_path, scale_result, detection_summary, marker_config)
        logging.info(f"Marker-scaled model written to: {scaled_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    date = "20250602010323"
    parser.add_argument(
        "--input_image_path",
        type=Path,
        required=False,
        default=Path(f"outputs/{date}/pinhole_images/images"),
    )
    parser.add_argument(
        "--input_camera_config",
        type=Path,
        required=False,
        default=Path(f"outputs/{date}/pinhole_images/camera_params.json"),
    )
    parser.add_argument(
        "--input_rig_config",
        type=Path,
        required=False,
        default=Path(f"outputs/{date}/pinhole_images/rig_config.json"),
    )
    parser.add_argument(
        "--output_path",
        type=Path,
        required=False,
        default=Path(f"outputs/{date}/sfm"),
    )
    parser.add_argument(
        "--matcher",
        default="sequential",
        choices=["sequential", "exhaustive", "vocabtree", "spatial"],
    )
    parser.add_argument(
        "--marker_length",
        type=float,
        default=None,
        help="Marker size in meters (enables marker-based scale estimation)",
    )
    parser.add_argument(
        "--marker_dict",
        type=str,
        default="DICT_4X4_50",
        help="ArUco dictionary name (e.g. DICT_4X4_50)",
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
        "--marker_scaled_suffix",
        type=str,
        default="marker_scaled",
        help="Suffix for scaled reconstruction output folder",
    )
    parser.add_argument(
        "--marker_report_path",
        type=Path,
        default=None,
        help="Output path for marker scale report (file or directory)",
    )
    run(parser.parse_args())
