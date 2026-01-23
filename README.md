#
<p align="center">
  <h1 align="center"><br><ins>Omni-SFM (WIP)</ins>
  <br>Structure-from-Motion pipeline for omnidirectional imagery</h1>
</p>

<div align="center">
  <a target="_blank" href='https://huggingface.co/spaces/Realcat/omni-sfm'><img src='https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Spaces-blue'></a>
</div>

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [Development](#development)
- [License](#license)

## Overview

Omni-SFM is a Structure-from-Motion (SfM) pipeline implementation for omnidirectional imagery. The project provides tools for processing panoramic images and reconstructing 3D scenes using both command-line COLMAP and pycolmap implementations.

*Sparse reconstruction with camera rig constraints*:
![](assets/omni_rec.jpg)

*Close-up view of sparse reconstruction showing camera rig alignment*:
![](assets/omni_rec_local.jpg)

## Features

- Support for both command-line COLMAP and pycolmap workflows
- Panoramic image processing capabilities
- Rig-based SfM pipeline
- Modular architecture for easy extension

## Installation

### Prerequisites

- Python 3.8+
- COLMAP installed (command-line 버전; 도커 이미지는 포함)
- CUDA-enabled GPU recommended

### Quick Start

```bash
# Clone repository
git clone https://github.com/your-repo/omni-sfm.git
cd omni-sfm

# Install with pip (recommended)
pip install -r requirements.txt
```

### Docker

```bash
# Build
docker build -t omni-sfm .

# Run
docker run --rm \
  -v "$(pwd)":/app \
  -v "$(pwd)/outputs":/app/outputs \
  -v "$(pwd)/inputs":/app/inputs \
  omni-sfm \
  --input_video /app/inputs/input.mp4 \
  --output_dir /app/outputs/run1
```

또는 docker-compose:

```bash
docker compose run --rm omni-sfm \
  --input_video /app/inputs/input.mp4 \
  --output_dir /app/outputs/run1
```

> 참고: 이 도커 이미지에는 CUDA 지원 COLMAP이 포함되어 있습니다.  
> NVIDIA GPU 환경에서는 컨테이너에 `--gpus all`을 추가해 GPU 가속을 사용할 수 있습니다.

docker-compose 기본 커맨드들:

```bash
# 1) 360도 영상 -> pinhole 이미지 생성
docker compose run --rm omni-sfm-pinhole

# 2) pinhole 이미지 -> COLMAP SfM
docker compose run --rm omni-sfm-colmap

# 3) 1) + 2) 연속 실행
docker compose run --rm omni-sfm-all
```

GPU 사용 관련:

- 현재 이미지의 COLMAP은 CUDA 빌드입니다.
- GPU 가속을 쓰려면 NVIDIA Container Toolkit이 필요합니다.
- 예: `docker run --gpus all ...` (Linux + NVIDIA GPU 환경 기준)
- macOS에서는 NVIDIA GPU 가속을 사용할 수 없습니다.

docker-compose GPU 프로필:

```bash
# pinhole 단계도 동일하게 gpu 프로필로 실행
docker compose --profile gpu run --rm omni-sfm-pinhole

# COLMAP 단계만 GPU로
docker compose --profile gpu run --rm omni-sfm-colmap-gpu

# pinhole + COLMAP 연속 실행을 GPU로
docker compose --profile gpu run --rm omni-sfm-all-gpu
```

## Usage

### CLI

```bash
python app.py \
  --input_video inputs/input.mp4 \
  --output_dir outputs/run1
```

옵션 예시:

```bash
python app.py \
  --input_video inputs/input.mp4 \
  --output_dir outputs/run1 \
  --frame_interval 24 \
  --width 640 \
  --height 640 \
  --fov_h 90 \
  --fov_v 90
```

뷰를 커스텀하려면 JSON 파일을 넘깁니다:

```bash
python app.py \
  --input_video inputs/input.mp4 \
  --output_dir outputs/run1 \
  --views_json configs/views.json
```

Output data structure:

``` bash
outputs/20250602xxxxxx/pinhole_images
├── images
│   ├── pitch_-35_yaw_-90
│   ├── pitch_-35_yaw_0
│   ├── pitch_-35_yaw_180
│   ├── pitch_-35_yaw_90
│   ├── pitch_35_yaw_-90
│   ├── pitch_35_yaw_0
│   ├── pitch_35_yaw_180
│   └── pitch_35_yaw_90
├── camera_params.json
└── rig_config.json
```

### Scripts

The project includes several scripts in the `scripts/` directory:

1. **run_cmd_colmap_rig_sfm.py**
   Runs the SfM pipeline using command-line COLMAP with rig support.

   **Parameters:**
   - `--image_path`: Path to input images directory (required)
   - `--output_path`: Path to output directory (required)
   - `--rig_config`: Path to rig configuration JSON file (required)
   - `--camera_config`: Path to camera parameters JSON file (required)
   - `--camera_model`: Camera model type (default: "PINHOLE", options: ["PINHOLE", "SIMPLE_PINHOLE", "SIMPLE_RADIAL"])
   - `--visualize`: Flag to visualize the sparse reconstruction

   **Usage Example:**

   ```bash
   python scripts/run_cmd_colmap_rig_sfm.py \
       --image_path inputs/images \
       --rig_config configs/rig.json \
       --camera_config configs/camera.json \
       --output_path outputs/sfm \
       --visualize
   # eg.
   python scripts/run_cmd_colmap_rig_sfm.py \
       --image_path outputs/20250602xxxxxx/pinhole_images/images \
       --rig_config outputs/20250602xxxxxx/pinhole_images/rig.json \
       --camera_config outputs/20250602xxxxxx/pinhole_images/camera.json \
       --output_path outputs/20250602xxxxxx/sfm \
       --visualize
   ```

2. **run_pycolmap_rig_sfm.py**
   Runs the SfM pipeline using pycolmap with rig support.

   Usage:

   ```bash
   python scripts/run_pycolmap_rig_sfm.py [options]
   ```

## Configuration

Modify `src/omni_processor.py` for pipeline configuration options.

### Contributing

1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## License

[MIT License](LICENSE)
