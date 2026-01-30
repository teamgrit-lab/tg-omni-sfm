# Omni-SFM

<p align="center">
  <h1 align="center"><br><ins>Omni-SFM (WIP)</ins>
  <br>360도 이미지를 위한 Structure-from-Motion 파이프라인</h1>
</p>

<div align="center">
  <a target="_blank" href='https://huggingface.co/spaces/Realcat/omni-sfm'><img src='https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Spaces-blue'></a>
</div>

## 목차

- [개요](#개요)
- [주요 기능](#주요-기능)
- [설치](#설치)
- [사용법](#사용법)
- [설정](#설정)
- [ComfyUI 통합](#comfyui-통합)
- [문제 해결](#문제-해결)
- [라이센스](#라이센스)

## 개요

Omni-SFM은 360도 영상/이미지를 위한 Structure-from-Motion (SfM) 파이프라인 구현입니다. 정방형(equirectangular) 파노라마 영상을 여러 개의 핀홀 카메라 뷰로 변환하고, COLMAP을 사용하여 3D 장면을 재구성합니다. 설정 가능한 뷰 오버랩을 통해 강건한 교차 뷰 특징 매칭을 제공하여 통합된 3D 재구성을 가능하게 합니다.

### 주요 장점

- **360° 비디오 처리**: 정방형 영상에서 프레임을 추출하고 여러 핀홀 뷰를 생성
- **다중 뷰 구성**: 8/16/32 뷰 지원 (pitch/yaw 각도 및 FOV 설정 가능)
- **최적화된 오버랩**: 45° 뷰 오버랩 (90° FOV, 45° yaw 간격)으로 강건한 특징 매칭 보장
- **Docker 지원**: 재현 가능한 처리를 위한 사전 구성된 COLMAP 환경
- **높은 등록률**: 적절한 뷰 구성으로 98% 이상의 이미지 등록률 달성

*카메라 릭 제약 조건을 적용한 희소 재구성*:
![](assets/omni_rec.jpg)

*카메라 릭 정렬을 보여주는 희소 재구성의 확대 뷰*:
![](assets/omni_rec_local.jpg)

## 주요 기능

- 명령줄 COLMAP 및 pycolmap 워크플로우 지원
- 파노라마 이미지 처리 기능
- 릭 기반 SfM 파이프라인
- 확장이 용이한 모듈식 아키텍처

## 설치

### 사전 요구사항

- Python 3.8+
- COLMAP 설치 (명령줄 버전용)
- CUDA 지원 GPU 권장

### 빠른 시작

```bash
# 저장소 클론
git clone https://github.com/teamgrit-lab/tg-omni-sfm.git
cd tg-omni-sfm

# pip로 설치 (권장)
pip install -r requirements.txt
```

### Docker 이미지 빌드 (권장)

```bash
# COLMAP이 포함된 Docker 이미지 빌드
docker build -t omni-sfm-colmap:latest .
```

### 추가 설정

1. 명령줄 COLMAP 사용 시:
   
   플랫폼에 맞는 COLMAP [설치 가이드](https://colmap.github.io/install.html)를 따라주세요.

2. ComfyUI 통합 사용 시:
   
   ComfyUI [설치 가이드](https://github.com/comfyanonymous/ComfyUI)를 따라주세요.

## 사용법

### 빠른 시작: 360° 비디오를 3D 재구성으로 변환

#### 1. GUI 애플리케이션

Gradio UI 애플리케이션 실행:

```bash
python app.py
```

Gradio UI:

![](assets/cover.jpg)

#### 2. Docker 기반 처리 (프로덕션 환경 권장)

COLMAP 3.7을 사용한 재현 가능한 결과:

```python
# 1단계: 360° 비디오에서 핀홀 이미지 생성
docker run --rm \
  -v /절대/경로/tg-omni-sfm:/workspace \
  omni-sfm-colmap:latest \
  python3 -c "
from src.omni_processor import OmniVideoProcessor

processor = OmniVideoProcessor()
params = {
    'video_path': '/workspace/data/your_video.mp4',
    'output_dir': '/workspace/outputs/your_output',
    'frame_interval': 24,  # 24번째 프레임마다 추출
    'views': [
        # 16개 뷰, 45° 오버랩 (pitch ±30°, yaw 0°-315°, 45° 간격)
        {'pitch': 30, 'yaw': 0}, {'pitch': 30, 'yaw': 45},
        {'pitch': 30, 'yaw': 90}, {'pitch': 30, 'yaw': 135},
        {'pitch': 30, 'yaw': 180}, {'pitch': 30, 'yaw': 225},
        {'pitch': 30, 'yaw': 270}, {'pitch': 30, 'yaw': 315},
        {'pitch': -30, 'yaw': 0}, {'pitch': -30, 'yaw': 45},
        {'pitch': -30, 'yaw': 90}, {'pitch': -30, 'yaw': 135},
        {'pitch': -30, 'yaw': 180}, {'pitch': -30, 'yaw': 225},
        {'pitch': -30, 'yaw': 270}, {'pitch': -30, 'yaw': 315}
    ],
    'fov': 90,  # 시야각 (도 단위)
    'output_width': 640,
    'output_height': 640
}
processor.process_video(**params)
print('핀홀 이미지 생성 완료')
"

# 2단계: COLMAP 특징점 추출
docker run --rm \
  -v /절대/경로/tg-omni-sfm:/workspace \
  omni-sfm-colmap:latest \
  bash -c "mkdir -p /workspace/outputs/your_output/sfm/sparse /workspace/outputs/your_output/sfm/database && \
  colmap feature_extractor \
    --database_path /workspace/outputs/your_output/sfm/database/database.db \
    --image_path /workspace/outputs/your_output/pinhole_images/images \
    --ImageReader.camera_model PINHOLE \
    --ImageReader.single_camera_per_folder 1 \
    --SiftExtraction.use_gpu 0 \
    --SiftExtraction.max_image_size 1024"

# 3단계: COLMAP 전수 매칭 (시간 소요: 1.5-2시간, 프레임 수에 따라 달라짐)
docker run --rm \
  -v /절대/경로/tg-omni-sfm:/workspace \
  omni-sfm-colmap:latest \
  colmap exhaustive_matcher \
    --database_path /workspace/outputs/your_output/sfm/database/database.db \
    --SiftMatching.use_gpu 0

# 4단계: COLMAP 증분 매핑
docker run --rm \
  -v /절대/경로/tg-omni-sfm:/workspace \
  omni-sfm-colmap:latest \
  colmap mapper \
    --database_path /workspace/outputs/your_output/sfm/database/database.db \
    --image_path /workspace/outputs/your_output/pinhole_images/images \
    --output_path /workspace/outputs/your_output/sfm/sparse

# 5단계: PLY 포맷으로 내보내기 (선택 사항)
docker run --rm \
  -v /절대/경로/tg-omni-sfm:/workspace \
  omni-sfm-colmap:latest \
  colmap model_converter \
    --input_path /workspace/outputs/your_output/sfm/sparse/0 \
    --output_path /workspace/outputs/your_output/sfm/sparse/0/model.ply \
    --output_type PLY

# 6단계: 결과 시각화
colmap gui \
  --database_path /절대/경로/outputs/your_output/sfm/database/database.db \
  --image_path /절대/경로/outputs/your_output/pinhole_images/images \
  --import_path /절대/경로/outputs/your_output/sfm/sparse/0
```

#### 출력 데이터 구조

```bash
outputs/your_output/
├── pinhole_images/
│   ├── images/
│   │   ├── p30_y0/       # pitch +30°, yaw 0°
│   │   ├── p30_y45/      # pitch +30°, yaw 45°
│   │   ├── p30_y90/      # pitch +30°, yaw 90°
│   │   ├── p30_y135/     # pitch +30°, yaw 135°
│   │   ├── p30_y180/     # pitch +30°, yaw 180°
│   │   ├── p30_y225/     # pitch +30°, yaw 225°
│   │   ├── p30_y270/     # pitch +30°, yaw 270°
│   │   ├── p30_y315/     # pitch +30°, yaw 315°
│   │   ├── p-30_y0/      # pitch -30°, yaw 0°
│   │   ├── p-30_y45/     # pitch -30°, yaw 45°
│   │   ├── p-30_y90/     # pitch -30°, yaw 90°
│   │   ├── p-30_y135/    # pitch -30°, yaw 135°
│   │   ├── p-30_y180/    # pitch -30°, yaw 180°
│   │   ├── p-30_y225/    # pitch -30°, yaw 225°
│   │   ├── p-30_y270/    # pitch -30°, yaw 270°
│   │   └── p-30_y315/    # pitch -30°, yaw 315°
│   ├── camera_params.json
│   └── rig_config.json
└── sfm/
    ├── database/
    │   └── database.db
    └── sparse/
        └── 0/
            ├── cameras.bin       # 카메라 파라미터
            ├── images.bin        # 등록된 이미지
            ├── points3D.bin      # 3D 포인트 클라우드
            ├── model.ply         # 시각화용 PLY 포맷
            └── project.ini
```

### 스크립트

`scripts/` 디렉토리에 여러 스크립트가 포함되어 있습니다:

#### 1. **process_360_video.py**
   360° 비디오를 처리하여 SfM용 핀홀 뷰를 생성합니다.

   **주요 파라미터:**
   - `video_path`: 입력 360° 비디오 경로 (정방형 포맷)
   - `output_dir`: 출력 파일 디렉토리
   - `frame_interval`: N번째 프레임마다 추출 (기본값: 24)
   - `views`: pitch/yaw 각도를 가진 카메라 뷰 구성 리스트
   - `fov`: 시야각 (도 단위, 기본값: 90)
   - `output_width/height`: 출력 핀홀 이미지 해상도

   **사용 예제:**

   ```bash
   python scripts/process_360_video.py \
       --video_path data/video.mp4 \
       --output_dir outputs/my_reconstruction \
       --frame_interval 24 \
       --fov 90
   ```

#### 2. **run_cmd_colmap_rig_sfm.py**
   릭 지원과 함께 명령줄 COLMAP을 사용하여 SfM 파이프라인을 실행합니다.

   **파라미터:**
   - `--image_path`: 입력 이미지 디렉토리 경로 (필수)
   - `--output_path`: 출력 디렉토리 경로 (필수)
   - `--rig_config`: 릭 구성 JSON 파일 경로 (필수)
   - `--camera_config`: 카메라 파라미터 JSON 파일 경로 (필수)
   - `--camera_model`: 카메라 모델 타입 (기본값: "PINHOLE", 옵션: ["PINHOLE", "SIMPLE_PINHOLE", "SIMPLE_RADIAL"])
   - `--visualize`: 희소 재구성 시각화 플래그

   **사용 예제:**

   ```bash
   python scripts/run_cmd_colmap_rig_sfm.py \
       --image_path outputs/my_reconstruction/pinhole_images/images \
       --rig_config outputs/my_reconstruction/pinhole_images/rig_config.json \
       --camera_config outputs/my_reconstruction/pinhole_images/camera_params.json \
       --output_path outputs/my_reconstruction/sfm \
       --visualize
   ```

#### 3. **run_pycolmap_rig_sfm.py**
   릭 지원과 함께 pycolmap을 사용하여 SfM 파이프라인을 실행합니다.

   사용법:

   ```bash
   python scripts/run_pycolmap_rig_sfm.py [옵션]
   ```

## 설정

파이프라인 설정 옵션은 `src/omni_processor.py`를 수정하세요.

### 뷰 구성 최적화

**중요**: 360° 재구성의 성공은 적절한 뷰 오버랩에 달려 있습니다.

- **권장 구성**: 16 뷰 (pitch ±30°, yaw 0°-315°, 45° 간격)
  - FOV: 90°
  - Yaw 간격: 45°
  - **오버랩**: 45° (FOV - yaw 간격 = 90° - 45°)
  - **결과**: 98%+ 이미지 등록률, track length ~9.4

- **잘못된 구성 예시**: 8 뷰 (90° yaw 간격)
  - FOV: 90°
  - Yaw 간격: 90°
  - **오버랩**: 0° (FOV - yaw 간격 = 90° - 90°)
  - **결과**: 8개의 분리된 모델, 교차 뷰 매칭 실패

**핵심 원칙**: `오버랩 = FOV - 각도_간격 > 0` (최소 30-45° 권장)

## 문제 해결

### 일반적인 문제

1. **낮은 이미지 등록률 (<80%)**
   - 원인: 뷰 간 오버랩 부족
   - 해결: yaw 간격을 줄이거나 FOV를 증가 (45° 오버랩 권장)

2. **여러 개의 분리된 모델**
   - 원인: 뷰 간 오버랩 0%
   - 해결: 16 뷰 구성 (45° yaw 간격, 90° FOV) 사용

3. **메모리 부족 (Exhaustive Matching 중)**
   - 원인: 이미지 해상도가 너무 높음
   - 해결: `--SiftExtraction.max_image_size 1024` 사용 또는 더 낮은 값 사용

4. **긴 처리 시간**
   - Exhaustive matching: O(n²) 복잡도
   - 98 프레임 × 16 뷰 = 1568 이미지 → ~1.5-2시간
   - 해결: `frame_interval` 증가 또는 GPU 매칭 사용

### 성능 벤치마크

테스트된 구성 (com3.mp4, 2332 프레임):
- 프레임 추출: 98 프레임 (interval=24) → ~1분
- 핀홀 생성: 1568 이미지 (16 뷰) → ~2분
- 특징점 추출: 1568 이미지 → ~1분
- Exhaustive matching: ~1.5-2시간 (CPU)
- Incremental mapping: ~1.5시간
- **총 소요 시간**: ~3-4시간
- **결과**: 1547/1568 등록 (98.7%), 131K 3D 포인트

## 기여

1. 저장소 포크
2. 기능 브랜치 생성
3. Pull request 제출

## 라이센스

[MIT License](LICENSE)

## 참고 자료

- [COLMAP Documentation](https://colmap.github.io/)
- [py360convert](https://github.com/sunset1995/py360convert)
- [ComfyUI](https://github.com/comfyanonymous/ComfyUI)
