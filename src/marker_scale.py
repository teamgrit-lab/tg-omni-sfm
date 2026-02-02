from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
import json

import cv2
import numpy as np
from scipy.spatial.transform import Rotation as R


@dataclass
class MarkerScaleConfig:
    marker_length: float
    marker_dict: str = "DICT_4X4_50"
    marker_ids: Optional[List[int]] = None
    min_observations: int = 2
    image_stride: int = 1
    max_images: Optional[int] = None


@dataclass
class MarkerObservation:
    image_name: str
    marker_id: int
    tvec: np.ndarray


@dataclass
class MarkerScaleResult:
    scale_sfm_per_meter: float
    scale_meter_per_sfm: float
    rmse_sfm: float
    num_observations: int
    num_markers: int
    markers_sfm: Dict[int, List[float]]
    images_used: int
    note: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "scale_sfm_per_meter": self.scale_sfm_per_meter,
            "scale_meter_per_sfm": self.scale_meter_per_sfm,
            "rmse_sfm": self.rmse_sfm,
            "num_observations": self.num_observations,
            "num_markers": self.num_markers,
            "markers_sfm": self.markers_sfm,
            "images_used": self.images_used,
            "note": self.note,
        }


def _require_aruco() -> None:
    if not hasattr(cv2, "aruco"):
        raise ImportError(
            "cv2.aruco not available. Install opencv-contrib-python to enable marker detection."
        )


def _get_aruco_dictionary(dict_name: str):
    _require_aruco()
    try:
        dict_id = getattr(cv2.aruco, dict_name)
    except AttributeError as exc:
        raise ValueError(f"Unknown ArUco dictionary: {dict_name}") from exc
    if hasattr(cv2.aruco, "getPredefinedDictionary"):
        return cv2.aruco.getPredefinedDictionary(dict_id)
    return cv2.aruco.Dictionary_get(dict_id)


def _create_detector_params():
    _require_aruco()
    if hasattr(cv2.aruco, "DetectorParameters"):
        return cv2.aruco.DetectorParameters()
    return cv2.aruco.DetectorParameters_create()


def _detect_markers(gray: np.ndarray, aruco_dict, detector_params):
    if hasattr(cv2.aruco, "ArucoDetector"):
        detector = cv2.aruco.ArucoDetector(aruco_dict, detector_params)
        return detector.detectMarkers(gray)
    return cv2.aruco.detectMarkers(gray, aruco_dict, parameters=detector_params)


def _build_camera_matrix(cam_params: dict) -> np.ndarray:
    return np.array(
        [
            [cam_params["fx"], 0.0, cam_params["cx"]],
            [0.0, cam_params["fy"], cam_params["cy"]],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )


def load_camera_params(camera_params_path: Path) -> Dict[str, dict]:
    with open(camera_params_path, "r", encoding="utf-8") as f:
        items = json.load(f)
    params_by_name = {}
    for cam in items:
        image_name = f"{cam['image_prefix']}/{cam['image_name']}"
        params_by_name[image_name] = cam
    return params_by_name


def collect_marker_observations(
    image_root: Path,
    camera_params_path: Path,
    config: MarkerScaleConfig,
) -> Tuple[List[MarkerObservation], dict]:
    params_by_name = load_camera_params(camera_params_path)
    image_items = list(params_by_name.items())
    aruco_dict = _get_aruco_dictionary(config.marker_dict)
    detector_params = _create_detector_params()
    dist_coeffs = np.zeros((5, 1), dtype=np.float64)

    observations: List[MarkerObservation] = []
    stats = {
        "images_total": len(image_items),
        "images_processed": 0,
        "images_with_markers": 0,
        "marker_detections": 0,
        "unique_markers": 0,
    }
    found_marker_ids = set()

    for idx, (image_name, cam_params) in enumerate(image_items):
        if config.image_stride > 1 and idx % config.image_stride != 0:
            continue
        if config.max_images and stats["images_processed"] >= config.max_images:
            break

        image_path = image_root / image_name
        if not image_path.exists():
            continue
        image = cv2.imread(str(image_path))
        if image is None:
            continue

        stats["images_processed"] += 1
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = _detect_markers(gray, aruco_dict, detector_params)
        if ids is None or len(ids) == 0:
            continue

        stats["images_with_markers"] += 1
        camera_matrix = _build_camera_matrix(cam_params)
        rvecs, tvecs, _ = cv2.aruco.estimatePoseSingleMarkers(
            corners, config.marker_length, camera_matrix, dist_coeffs
        )
        marker_ids = ids.flatten().tolist()
        for marker_id, tvec in zip(marker_ids, tvecs):
            if config.marker_ids and marker_id not in config.marker_ids:
                continue
            tvec = np.asarray(tvec[0], dtype=np.float64)
            observations.append(
                MarkerObservation(
                    image_name=image_name,
                    marker_id=int(marker_id),
                    tvec=tvec,
                )
            )
            stats["marker_detections"] += 1
            found_marker_ids.add(int(marker_id))

    stats["unique_markers"] = len(found_marker_ids)
    return observations, stats


def qvec_to_rotmat(qvec: Iterable[float]) -> np.ndarray:
    qvec = np.asarray(qvec, dtype=np.float64)
    rotation = R.from_quat([qvec[1], qvec[2], qvec[3], qvec[0]])
    return rotation.as_matrix()


def estimate_scale_from_observations(
    reconstruction,
    observations: List[MarkerObservation],
    min_observations: int,
) -> Optional[MarkerScaleResult]:
    name_to_image = {
        image.name: image
        for image in reconstruction.images.values()
        if getattr(image, "is_registered", True)
    }
    obs_by_marker: Dict[int, List[Tuple[MarkerObservation, object]]] = {}
    for obs in observations:
        image = name_to_image.get(obs.image_name)
        if image is None:
            continue
        obs_by_marker.setdefault(obs.marker_id, []).append((obs, image))

    obs_by_marker = {
        marker_id: items
        for marker_id, items in obs_by_marker.items()
        if len(items) >= min_observations
    }
    if not obs_by_marker:
        return None

    marker_ids = sorted(obs_by_marker.keys())
    marker_index = {marker_id: idx for idx, marker_id in enumerate(marker_ids)}
    used_observations: List[Tuple[int, MarkerObservation, object]] = []
    for marker_id, entries in obs_by_marker.items():
        for obs, image in entries:
            used_observations.append((marker_id, obs, image))

    num_obs = len(used_observations)
    num_markers = len(marker_ids)
    if num_obs * 3 < 1 + 3 * num_markers:
        return None
    A = np.zeros((num_obs * 3, 1 + 3 * num_markers), dtype=np.float64)
    b = np.zeros((num_obs * 3,), dtype=np.float64)

    row = 0
    images_used = set()
    for marker_id, obs, image in used_observations:
        qvec = np.asarray(image.qvec, dtype=np.float64)
        tvec = np.asarray(image.tvec, dtype=np.float64)
        rot_cw = qvec_to_rotmat(qvec)
        cam_center = -rot_cw.T @ tvec
        v_world = rot_cw.T @ obs.tvec

        col = 1 + 3 * marker_index[marker_id]
        A[row : row + 3, 0] = -v_world
        A[row, col] = 1.0
        A[row + 1, col + 1] = 1.0
        A[row + 2, col + 2] = 1.0
        b[row : row + 3] = cam_center
        row += 3
        images_used.add(obs.image_name)

    x, _, rank, _ = np.linalg.lstsq(A, b, rcond=None)
    if rank < 1:
        return None

    scale = float(x[0])
    if abs(scale) < 1e-9:
        return None
    if scale <= 0:
        return None

    markers_sfm: Dict[int, List[float]] = {}
    for marker_id, idx in marker_index.items():
        offset = 1 + 3 * idx
        markers_sfm[marker_id] = [float(v) for v in x[offset : offset + 3]]

    errors = []
    for marker_id, obs, image in used_observations:
        qvec = np.asarray(image.qvec, dtype=np.float64)
        tvec = np.asarray(image.tvec, dtype=np.float64)
        rot_cw = qvec_to_rotmat(qvec)
        cam_center = -rot_cw.T @ tvec
        v_world = rot_cw.T @ obs.tvec
        marker_pos = np.asarray(markers_sfm[marker_id], dtype=np.float64)
        pred = cam_center + scale * v_world
        errors.append(np.linalg.norm(marker_pos - pred))
    rmse = float(np.sqrt(np.mean(np.square(errors)))) if errors else 0.0

    return MarkerScaleResult(
        scale_sfm_per_meter=scale,
        scale_meter_per_sfm=1.0 / scale,
        rmse_sfm=rmse,
        num_observations=num_obs,
        num_markers=num_markers,
        markers_sfm=markers_sfm,
        images_used=len(images_used),
    )


def apply_scale_to_reconstruction(reconstruction, scale_factor: float) -> None:
    if scale_factor <= 0:
        raise ValueError("scale_factor must be positive.")

    for image in reconstruction.images.values():
        if not getattr(image, "is_registered", True):
            continue
        qvec = np.asarray(image.qvec, dtype=np.float64)
        tvec = np.asarray(image.tvec, dtype=np.float64)
        rot_cw = qvec_to_rotmat(qvec)
        cam_center = -rot_cw.T @ tvec
        cam_center_scaled = cam_center * scale_factor
        image.tvec = -rot_cw @ cam_center_scaled

    for point in reconstruction.points3D.values():
        point.xyz = np.asarray(point.xyz, dtype=np.float64) * scale_factor


def write_scale_report(
    report_path: Path,
    result: MarkerScaleResult,
    detection_summary: dict,
    config: MarkerScaleConfig,
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "config": {
            "marker_length": config.marker_length,
            "marker_dict": config.marker_dict,
            "marker_ids": config.marker_ids,
            "min_observations": config.min_observations,
            "image_stride": config.image_stride,
            "max_images": config.max_images,
        },
        "detection_summary": detection_summary,
        "scale_result": result.to_dict(),
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
