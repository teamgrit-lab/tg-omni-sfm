"""
Complete pipeline script for processing 360 video and running COLMAP SfM.
Designed to run inside Docker container.
"""

import argparse
import sys
import time
from pathlib import Path

# Ensure we can import from src
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.omni_processor import OmniVideoProcessor


def process_video_to_pinhole(video_path: Path, output_dir: Path, frame_interval: int = 24):
    """
    Step 1: Extract frames from 360 video and convert to pinhole images.
    
    Args:
        video_path: Path to input 360 video
        output_dir: Output directory for processed data
        frame_interval: Extract every N-th frame (lower = more frames)
    """
    print(f"\n{'='*60}")
    print("Step 1: Extracting frames and generating pinhole images")
    print(f"{'='*60}")
    print(f"Input video: {video_path}")
    print(f"Output directory: {output_dir}")
    print(f"Frame interval: {frame_interval} (every {frame_interval}th frame)")
    
    # Configure processor with optimized parameters for 360 video
    params = {
        "fx": 320.0,
        "fy": 320.0,
        "cx": 320.0,
        "cy": 320.0,
        "height": 640,
        "width": 640,
        "fov_h": 90,
        "fov_v": 90,
        "frame_interval": frame_interval,
        "num_steps_yaw": 4,
        "pitches_deg": [-35.0, 35.0],
        "views": {
            "pitch_35_yaw_0": (35, 0),
            "pitch_35_yaw_90": (35, 90),
            "pitch_35_yaw_-90": (35, -90),
            "pitch_35_yaw_180": (35, 180),
            "pitch_-35_yaw_0": (-35, 0),
            "pitch_-35_yaw_90": (-35, 90),
            "pitch_-35_yaw_-90": (-35, -90),
            "pitch_-35_yaw_180": (-35, 180),
        },
    }
    
    processor = OmniVideoProcessor(params)
    pano_images, pinhole_images_data = processor.process_video(str(video_path), output_dir)
    
    print(f"\n✓ Extracted {len(pano_images)} panorama frames")
    print(f"✓ Generated {len(pinhole_images_data)} pinhole images")
    
    return output_dir / "pinhole_images"


def run_command(cmd_list):
    """Executes a command and prints its output."""
    import subprocess
    print(f"\nExecuting: {' '.join(map(str, cmd_list))}")
    try:
        process = subprocess.Popen(
            cmd_list,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
        )
        while True:
            output = process.stdout.readline()
            if output == "" and process.poll() is not None:
                break
            if output:
                print(output.strip())
        rc = process.poll()
        if rc != 0:
            print(f"Error: Command failed with exit code {rc}")
        return rc
    except FileNotFoundError:
        print(f"Error: Command '{cmd_list[0]}' not found.")
        return -1


def run_colmap_sfm(pinhole_dir: Path, output_dir: Path, matcher: str = "sequential"):
    """
    Step 2: Run COLMAP SfM on pinhole images using COLMAP CLI.
    """
    print(f"\n{'='*60}")
    print("Step 2: Running COLMAP SfM")
    print(f"{'='*60}")
    
    import json
    import sqlite3
    import numpy as np
    
    image_path = pinhole_dir / "images"
    camera_config_path = pinhole_dir / "camera_params.json"
    rig_config_path = pinhole_dir / "rig_config.json"
    
    sfm_output = output_dir / "sfm"
    database_path = sfm_output / "database.db"
    sparse_path = sfm_output / "sparse"
    
    sfm_output.mkdir(parents=True, exist_ok=True)
    sparse_path.mkdir(parents=True, exist_ok=True)
    
    if database_path.exists():
        database_path.unlink()
    
    print(f"Image path: {image_path}")
    print(f"Camera config: {camera_config_path}")
    print(f"Rig config: {rig_config_path}")
    print(f"SfM output: {sfm_output}")
    
    # Load configs
    with open(camera_config_path, "r") as f:
        camera_config = json.load(f)
    
    COLMAP_EXE = "colmap"
    
    # --- 1. Feature Extraction ---
    print("\n--- Step 2.1: Feature Extraction ---")
    cmd_feature = [
        COLMAP_EXE,
        "feature_extractor",
        "--database_path", str(database_path),
        "--image_path", str(image_path),
        "--ImageReader.camera_model", "PINHOLE",
        "--ImageReader.single_camera_per_folder", "1",
        "--SiftExtraction.use_gpu", "0",  # Use CPU mode for Docker compatibility
    ]
    if run_command(cmd_feature) != 0:
        print("Feature extraction failed!")
        return sfm_output
    print("✓ Feature extraction complete")
    
    # Update camera parameters in database
    print("\n--- Updating camera parameters in database ---")
    conn = sqlite3.connect(str(database_path))
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM images")
    results = cursor.fetchall()
    name_to_id = {}
    for row in results:
        image_id = row[0]
        image_name = row[1]
        camera_id = row[2]
        name_to_id[image_name] = camera_id

    for cam in camera_config:
        params = np.array([cam["fx"], cam["fy"], cam["cx"], cam["cy"]], dtype=np.float64)
        cam_key = f"{cam['image_prefix']}/{cam['image_name']}"
        camera_id = name_to_id.get(cam_key, 0)
        if camera_id:
            cursor.execute(
                "UPDATE cameras SET params = ? WHERE camera_id = ?",
                (params.tobytes(), camera_id),
            )
    conn.commit()
    conn.close()
    print("✓ Camera parameters updated")
    
    # --- 2. Feature Matching ---
    print(f"\n--- Step 2.2: Feature Matching ({matcher}) ---")
    if matcher == "sequential":
        cmd_matcher = [
            COLMAP_EXE,
            "sequential_matcher",
            "--database_path", str(database_path),
            "--SequentialMatching.loop_detection", "0",  # Disable loop detection (requires vocab tree)
            "--SiftMatching.use_gpu", "0",  # Use CPU mode for Docker compatibility
        ]
    else:
        cmd_matcher = [
            COLMAP_EXE,
            "exhaustive_matcher",
            "--database_path", str(database_path),
            "--SiftMatching.use_gpu", "0",  # Use CPU mode for Docker compatibility
        ]
    
    if run_command(cmd_matcher) != 0:
        print("Feature matching failed!")
        return sfm_output
    print("✓ Feature matching complete")
    
    # --- 3. Apply Rig Configuration ---
    print("\n--- Step 2.3: Applying Rig Configuration ---")
    cmd_rig = [
        COLMAP_EXE,
        "rig_configurator",
        "--database_path", str(database_path),
        "--rig_config_path", str(rig_config_path),
    ]
    if run_command(cmd_rig) != 0:
        print("Rig configuration failed, continuing without rig...")
    else:
        print("✓ Rig configuration applied")
    
    # --- 4. Incremental Mapping ---
    print("\n--- Step 2.4: Incremental Mapping ---")
    cmd_mapper = [
        COLMAP_EXE,
        "mapper",
        "--database_path", str(database_path),
        "--image_path", str(image_path),
        "--output_path", str(sparse_path),
        "--Mapper.ba_refine_focal_length", "0",
        "--Mapper.ba_refine_principal_point", "0",
        "--Mapper.ba_refine_extra_params", "0",
    ]
    if run_command(cmd_mapper) != 0:
        print("Mapping failed!")
        return sfm_output
    print("✓ Incremental mapping complete")
    
    # Check results
    print("\n--- Reconstruction Results ---")
    model_dirs = list(sparse_path.glob("*"))
    for model_dir in model_dirs:
        if model_dir.is_dir():
            print(f"Model found: {model_dir}")
            # Count files
            files = list(model_dir.glob("*"))
            print(f"  Files: {[f.name for f in files]}")
    
    return sfm_output


def main():
    parser = argparse.ArgumentParser(description="Process 360 video and run COLMAP SfM")
    parser.add_argument(
        "--video_path",
        type=Path,
        default=Path("/workspace/data/com3_half.mp4"),
        help="Path to input 360 video"
    )
    parser.add_argument(
        "--output_dir",
        type=Path,
        default=None,
        help="Output directory (default: outputs/<timestamp>)"
    )
    parser.add_argument(
        "--frame_interval",
        type=int,
        default=24,
        help="Extract every N-th frame (lower = more frames, default: 24)"
    )
    parser.add_argument(
        "--matcher",
        default="sequential",
        choices=["sequential", "exhaustive"],
        help="Feature matching method"
    )
    parser.add_argument(
        "--skip_video_processing",
        action="store_true",
        help="Skip video processing if pinhole images already exist"
    )
    parser.add_argument(
        "--pinhole_dir",
        type=Path,
        default=None,
        help="Path to existing pinhole images directory (use with --skip_video_processing)"
    )
    
    args = parser.parse_args()
    
    # Set output directory
    if args.output_dir is None:
        timestamp = time.strftime("%Y%m%d%H%M%S")
        args.output_dir = Path("/workspace/outputs") / timestamp
    
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'#'*60}")
    print("# 360 Video to COLMAP SfM Pipeline")
    print(f"{'#'*60}")
    print(f"Video: {args.video_path}")
    print(f"Output: {args.output_dir}")
    print(f"Frame interval: {args.frame_interval}")
    print(f"Matcher: {args.matcher}")
    
    # Step 1: Process video to pinhole images
    if args.skip_video_processing and args.pinhole_dir:
        pinhole_dir = args.pinhole_dir
        print(f"\nSkipping video processing, using existing: {pinhole_dir}")
    else:
        if not args.video_path.exists():
            print(f"\nError: Video file not found: {args.video_path}")
            sys.exit(1)
        pinhole_dir = process_video_to_pinhole(
            args.video_path, 
            args.output_dir,
            args.frame_interval
        )
    
    # Step 2: Run COLMAP SfM
    sfm_output = run_colmap_sfm(pinhole_dir, args.output_dir, args.matcher)
    
    print(f"\n{'#'*60}")
    print("# Pipeline Complete!")
    print(f"{'#'*60}")
    print(f"Pinhole images: {pinhole_dir}")
    print(f"SfM results: {sfm_output}")
    print(f"Sparse model: {sfm_output / 'sparse'}")


if __name__ == "__main__":
    main()
