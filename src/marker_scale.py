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
class MarkerBoardSpec:
    name: str
    marker_length: float
    marker_dict: str
    markers_m: Dict[int, List[float]]
    page_size_m: Optional[Tuple[float, float]] = None
    marker_separation: Optional[float] = None

    def to_dict(self) -> dict:
        markers = [
            {"id": marker_id, "center_m": center}
            for marker_id, center in sorted(self.markers_m.items())
        ]
        page = None
        if self.page_size_m:
            page = {"width_m": self.page_size_m[0], "height_m": self.page_size_m[1]}
        return {
            "name": self.name,
            "marker_length": self.marker_length,
            "marker_dict": self.marker_dict,
            "markers": markers,
            "page": page,
            "marker_separation": self.marker_separation,
        }


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
    method: str = "marker_size"
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
            "method": self.method,
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


def load_marker_board_spec(board_path: Path) -> MarkerBoardSpec:
    with open(board_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    name = data.get("name") or board_path.stem
    marker_length = float(data["marker_length"])
    marker_dict = data.get("marker_dict", "DICT_4X4_50")
    marker_separation = data.get("marker_separation")
    page_size_m = None
    page = data.get("page") or {}
    if page and "width_m" in page and "height_m" in page:
        page_size_m = (float(page["width_m"]), float(page["height_m"]))

    markers_m: Dict[int, List[float]] = {}
    for entry in data.get("markers", []):
        marker_id = int(entry["id"])
        center = entry.get("center_m") or entry.get("center")
        if center is None or len(center) < 2:
            raise ValueError(f"Marker center missing for id {marker_id}")
        center_vec = [float(center[0]), float(center[1]), float(center[2]) if len(center) > 2 else 0.0]
        markers_m[marker_id] = center_vec

    if not markers_m:
        raise ValueError("Marker board spec has no markers.")

    return MarkerBoardSpec(
        name=name,
        marker_length=marker_length,
        marker_dict=marker_dict,
        markers_m=markers_m,
        page_size_m=page_size_m,
        marker_separation=marker_separation,
    )


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


def _group_observations(
    reconstruction,
    observations: List[MarkerObservation],
    min_observations: int,
) -> Dict[int, List[Tuple[MarkerObservation, object]]]:
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
    return obs_by_marker


def estimate_marker_positions_from_rays(
    reconstruction,
    observations: List[MarkerObservation],
    min_observations: int,
) -> Tuple[Dict[int, np.ndarray], int, int]:
    obs_by_marker = _group_observations(reconstruction, observations, min_observations)
    if not obs_by_marker:
        return {}, 0, 0

    markers_sfm: Dict[int, np.ndarray] = {}
    num_obs = 0
    images_used = set()
    eye = np.eye(3, dtype=np.float64)

    for marker_id, entries in obs_by_marker.items():
        A = np.zeros((3, 3), dtype=np.float64)
        b = np.zeros((3,), dtype=np.float64)
        valid_obs = 0
        for obs, image in entries:
            qvec = np.asarray(image.qvec, dtype=np.float64)
            tvec = np.asarray(image.tvec, dtype=np.float64)
            rot_cw = qvec_to_rotmat(qvec)
            cam_center = -rot_cw.T @ tvec
            v_world = rot_cw.T @ obs.tvec
            norm = float(np.linalg.norm(v_world))
            if norm < 1e-9:
                continue
            direction = v_world / norm
            proj = eye - np.outer(direction, direction)
            A += proj
            b += proj @ cam_center
            valid_obs += 1
            num_obs += 1
            images_used.add(obs.image_name)

        if valid_obs < min_observations:
            continue
        if np.linalg.matrix_rank(A) < 3:
            continue
        markers_sfm[marker_id] = np.linalg.solve(A, b)

    return markers_sfm, num_obs, len(images_used)


def estimate_scale_from_observations(
    reconstruction,
    observations: List[MarkerObservation],
    min_observations: int,
) -> Optional[MarkerScaleResult]:
    obs_by_marker = _group_observations(reconstruction, observations, min_observations)
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
        method="marker_size",
    )


def estimate_scale_from_board_distances(
    reconstruction,
    observations: List[MarkerObservation],
    board_spec: MarkerBoardSpec,
    min_observations: int,
) -> Optional[MarkerScaleResult]:
    markers_sfm, num_obs, images_used = estimate_marker_positions_from_rays(
        reconstruction, observations, min_observations
    )
    if not markers_sfm:
        return None

    common_ids = sorted(set(markers_sfm.keys()) & set(board_spec.markers_m.keys()))
    if len(common_ids) < 2:
        return None

    ratios = []
    for i, marker_i in enumerate(common_ids):
        for marker_j in common_ids[i + 1 :]:
            p_sfm = markers_sfm[marker_i]
            q_sfm = markers_sfm[marker_j]
            d_sfm = float(np.linalg.norm(p_sfm - q_sfm))
            if d_sfm < 1e-9:
                continue
            p_real = np.asarray(board_spec.markers_m[marker_i], dtype=np.float64)
            q_real = np.asarray(board_spec.markers_m[marker_j], dtype=np.float64)
            d_real = float(np.linalg.norm(p_real - q_real))
            if d_real <= 0:
                continue
            ratios.append(d_real / d_sfm)

    if not ratios:
        return None

    scale_meter_per_sfm = float(np.median(ratios))
    if scale_meter_per_sfm <= 0:
        return None
    scale_sfm_per_meter = 1.0 / scale_meter_per_sfm

    errors = []
    for i, marker_i in enumerate(common_ids):
        for marker_j in common_ids[i + 1 :]:
            p_sfm = markers_sfm[marker_i]
            q_sfm = markers_sfm[marker_j]
            d_sfm = float(np.linalg.norm(p_sfm - q_sfm))
            p_real = np.asarray(board_spec.markers_m[marker_i], dtype=np.float64)
            q_real = np.asarray(board_spec.markers_m[marker_j], dtype=np.float64)
            d_real = float(np.linalg.norm(p_real - q_real))
            pred = scale_meter_per_sfm * d_sfm
            errors.append(d_real - pred)
    rmse = float(np.sqrt(np.mean(np.square(errors)))) if errors else 0.0

    markers_sfm_list = {mid: [float(v) for v in pos] for mid, pos in markers_sfm.items()}
    return MarkerScaleResult(
        scale_sfm_per_meter=scale_sfm_per_meter,
        scale_meter_per_sfm=scale_meter_per_sfm,
        rmse_sfm=rmse,
        num_observations=num_obs,
        num_markers=len(common_ids),
        markers_sfm=markers_sfm_list,
        images_used=images_used,
        method="board_distance",
        note=f"board={board_spec.name}",
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
    board_spec: Optional[MarkerBoardSpec] = None,
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
    if board_spec:
        report["board_spec"] = board_spec.to_dict()
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
