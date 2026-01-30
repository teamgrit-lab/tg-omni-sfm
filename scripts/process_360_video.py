"""
Script to process 360 video and run COLMAP SfM pipeline.
This extracts frames from 360 video, converts to pinhole images,
and prepares for COLMAP processing.
"""

import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.omni_processor import OmniVideoProcessor


def main():
    # Input video path
    video_path = Path(__file__).parent.parent / "data" / "com3_half.mp4"
    
    if not video_path.exists():
        print(f"Error: Video file not found at {video_path}")
        return None
    
    # Output directory with timestamp
    timestamp = time.strftime("%Y%m%d%H%M%S")
    output_dir = Path(__file__).parent.parent / "outputs" / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Processing video: {video_path}")
    print(f"Output directory: {output_dir}")
    
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
        "frame_interval": 12,  # Extract more frames for better reconstruction
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
    
    print("Extracting frames and generating pinhole images...")
    pano_images, pinhole_images_data = processor.process_video(str(video_path), output_dir)
    
    print(f"\nProcessing complete!")
    print(f"Total panorama frames extracted: {len(pano_images)}")
    print(f"Total pinhole images generated: {len(pinhole_images_data)}")
    print(f"Output saved to: {output_dir}")
    print(f"\nPinhole images are in: {output_dir / 'pinhole_images' / 'images'}")
    print(f"Camera params: {output_dir / 'pinhole_images' / 'camera_params.json'}")
    print(f"Rig config: {output_dir / 'pinhole_images' / 'rig_config.json'}")
    
    return str(output_dir)


if __name__ == "__main__":
    output_path = main()
    if output_path:
        print(f"\n=== OUTPUT_DIR: {output_path} ===")
