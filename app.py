import argparse
import json
import time
from pathlib import Path

from src.omni_processor import OmniVideoProcessor


def parse_args():
    parser = argparse.ArgumentParser(
        description="Omnidirectional video to pinhole image converter (CLI)"
    )
    parser.add_argument(
        "--input_video",
        type=Path,
        required=True,
        help="입력 비디오 파일 경로",
    )
    parser.add_argument(
        "--output_dir",
        type=Path,
        default=None,
        help="출력 디렉토리 (기본값: outputs/<timestamp>)",
    )
    parser.add_argument("--frame_interval", type=int, default=None, help="프레임 간격")
    parser.add_argument("--width", type=int, default=None, help="출력 이미지 너비")
    parser.add_argument("--height", type=int, default=None, help="출력 이미지 높이")
    parser.add_argument("--fov_h", type=float, default=None, help="가로 FOV (deg)")
    parser.add_argument("--fov_v", type=float, default=None, help="세로 FOV (deg)")
    parser.add_argument(
        "--views_json",
        type=Path,
        default=None,
        help="뷰 설정 JSON (예: {\"pitch_35_yaw_0\": [35, 0], ...})",
    )
    return parser.parse_args()


def load_views(views_json: Path):
    with open(views_json, "r", encoding="utf-8") as f:
        raw = json.load(f)
    views = {}
    for name, value in raw.items():
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ValueError(f"Invalid view format for '{name}': {value}")
        views[name] = (float(value[0]), float(value[1]))
    return views


def build_params(args):
    params = OmniVideoProcessor.default_params.copy()
    if args.frame_interval is not None:
        params["frame_interval"] = args.frame_interval
    if args.width is not None:
        params["width"] = args.width
    if args.height is not None:
        params["height"] = args.height
    if args.fov_h is not None:
        params["fov_h"] = args.fov_h
    if args.fov_v is not None:
        params["fov_v"] = args.fov_v
    if args.views_json is not None:
        params["views"] = load_views(args.views_json)
    return params


def main():
    args = parse_args()
    output_dir = args.output_dir or Path("outputs") / time.strftime("%Y%m%d%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)

    params = build_params(args)
    processor = OmniVideoProcessor(params)
    processor.process_video(str(args.input_video), output_dir)

    print(f"완료: {output_dir}")
    print(f"- pinhole 이미지: {output_dir / 'pinhole_images' / 'images'}")
    print(f"- camera_params.json: {output_dir / 'pinhole_images' / 'camera_params.json'}")
    print(f"- rig_config.json: {output_dir / 'pinhole_images' / 'rig_config.json'}")


if __name__ == "__main__":
    main()
