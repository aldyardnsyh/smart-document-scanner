from dataclasses import dataclass
from math import atan2, degrees

import cv2
import numpy as np

Image = np.ndarray


@dataclass(frozen=True)
class DetectionResult:
    detected: bool
    corners: np.ndarray
    debug_image: Image
    rotation_angle: float
    area_ratio: float
    method: str
    selection_score: float
    alternatives: list[np.ndarray]
    alternative_methods: list[str]


def order_points(points: np.ndarray) -> np.ndarray:
    ordered = np.array(points, dtype=np.float32).reshape(4, 2)
    summed = ordered.sum(axis=1)
    difference = ordered[:, 1] - ordered[:, 0]
    return np.array(
        [
            ordered[np.argmin(summed)],
            ordered[np.argmin(difference)],
            ordered[np.argmax(summed)],
            ordered[np.argmax(difference)],
        ],
        dtype=np.int32,
    )


def _quad_is_valid(points: np.ndarray, image_area: float) -> bool:
    contour_area = abs(cv2.contourArea(points))
    if contour_area < image_area * 0.10 or contour_area > image_area * 0.93:
        return False
    lengths = [float(np.linalg.norm(points[index] - points[(index + 1) % 4])) for index in range(4)]
    if min(lengths) < 24:
        return False
    ratio = max(lengths) / max(min(lengths), 1.0)
    return ratio <= 10.0


def _contour_candidates(edges: Image, source: str) -> list[tuple[np.ndarray, str]]:
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    candidates: list[tuple[np.ndarray, str]] = []
    for contour in contours:
        perimeter = cv2.arcLength(contour, True)
        if perimeter < 120:
            continue
        approximation = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(approximation) == 4 and cv2.isContourConvex(approximation):
            candidates.append((approximation.reshape(4, 2), f"{source}_contour"))
        rectangle = cv2.minAreaRect(contour)
        box = cv2.boxPoints(rectangle).astype(np.int32)
        candidates.append((box, f"{source}_min_area_rect"))
    return candidates


def _candidate_metrics(
    gray: Image,
    edges: Image,
    points: np.ndarray,
) -> dict[str, float]:
    height, width = gray.shape
    image_area = float(width * height)
    contour_area = abs(cv2.contourArea(points))
    _, (rect_width, rect_height), _ = cv2.minAreaRect(points)
    rectangle_area = max(float(rect_width * rect_height), 1.0)
    rectangularity = min(contour_area / rectangle_area, 1.0)
    inside = np.zeros((height, width), dtype=np.uint8)
    cv2.fillConvexPoly(inside, points, 255)
    kernel_size = max(3, int(min(height, width) * 0.012) | 1)
    kernel = np.ones((kernel_size, kernel_size), dtype=np.uint8)
    outside = cv2.subtract(np.full((height, width), 255, dtype=np.uint8), inside)
    outside_ring = cv2.subtract(outside, cv2.erode(outside, kernel, iterations=1))
    border = cv2.morphologyEx(inside, cv2.MORPH_GRADIENT, kernel)
    border_count = max(int(np.count_nonzero(border)), 1)
    inside_count = max(int(np.count_nonzero(inside)), 1)
    outside_count = max(int(np.count_nonzero(outside_ring)), 1)
    edge_values = edges > 0
    border_alignment = (
        float(np.count_nonzero(np.logical_and(edge_values, border > 0))) / border_count
    )
    inside_density = float(np.count_nonzero(np.logical_and(edge_values, inside > 0))) / inside_count
    outside_density = (
        float(np.count_nonzero(np.logical_and(edge_values, outside_ring > 0))) / outside_count
    )
    inside_mean = float(np.mean(gray[inside > 0])) if np.any(inside) else 0.0
    outside_mean = float(np.mean(gray[outside_ring > 0])) if np.any(outside_ring) else 0.0
    contrast = min(abs(inside_mean - outside_mean) / 255.0, 1.0)
    area_ratio = contour_area / image_area
    return {
        "area_ratio": area_ratio,
        "rectangularity": rectangularity,
        "border_alignment": border_alignment,
        "inside_density": inside_density,
        "outside_density": outside_density,
        "contrast": contrast,
    }


def _score_candidate(metrics: dict[str, float], method: str) -> float:
    area_ratio = metrics["area_ratio"]
    score = (
        metrics["border_alignment"] * 2.6
        + metrics["rectangularity"] * 1.5
        + metrics["contrast"] * 1.8
        + min(area_ratio, 0.75) * 0.45
        - metrics["outside_density"] * 0.7
    )
    if method.endswith("contour"):
        score += 0.18
    if area_ratio < 0.22:
        score -= (0.22 - area_ratio) * 4.0
    if area_ratio > 0.82:
        score -= 1.2
    return score


def _rank_valid_candidates(
    gray: Image,
    edges: Image,
    candidates: list[tuple[np.ndarray, str]],
    image_area: float,
) -> list[tuple[float, np.ndarray, str, dict[str, float]]]:
    valid: list[tuple[float, np.ndarray, str, dict[str, float]]] = []
    for points, method in candidates:
        if not _quad_is_valid(points, image_area):
            continue
        ordered = order_points(points)
        metrics = _candidate_metrics(gray, edges, ordered)
        valid.append((_score_candidate(metrics, method), ordered, method, metrics))
    return sorted(valid, key=lambda item: item[0], reverse=True)


def _diverse_candidates(
    ranked: list[tuple[float, np.ndarray, str, dict[str, float]]],
    limit: int = 4,
) -> list[tuple[float, np.ndarray, str, dict[str, float]]]:
    selected: list[tuple[float, np.ndarray, str, dict[str, float]]] = []
    for candidate in ranked:
        points = candidate[1]
        area = float(abs(cv2.contourArea(points)))
        center = points.mean(axis=0)
        duplicate = False
        for existing in selected:
            existing_points = existing[1]
            existing_area = float(abs(cv2.contourArea(existing_points)))
            existing_center = existing_points.mean(axis=0)
            relative_area_delta = abs(area - existing_area) / max(area, existing_area)
            center_delta = float(np.linalg.norm(center - existing_center)) / max(
                float(np.linalg.norm(center)),
                1.0,
            )
            if relative_area_delta < 0.08 and center_delta < 0.05:
                duplicate = True
                break
        if not duplicate:
            selected.append(candidate)
        if len(selected) >= limit:
            break
    return selected


def _full_frame_likelihood(gray: Image, edges: Image) -> float:
    height, width = gray.shape
    border_mask = np.zeros((height, width), dtype=np.uint8)
    thickness = max(4, int(min(height, width) * 0.06))
    border_mask[:thickness, :] = 255
    border_mask[-thickness:, :] = 255
    border_mask[:, :thickness] = 255
    border_mask[:, -thickness:] = 255
    border_density = float(np.count_nonzero(np.logical_and(edges > 0, border_mask > 0))) / max(
        int(np.count_nonzero(border_mask)),
        1,
    )
    laplacian_variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    center_density = float(np.count_nonzero(edges > 0)) / edges.size
    return (
        min(border_density / 0.08, 1.0) * 2
        + min(laplacian_variance / 900, 1.0)
        + min(
            center_density / 0.09,
            1.0,
        )
    )


def _full_frame_corners(shape: tuple[int, ...]) -> np.ndarray:
    height, width = shape[:2]
    return np.array(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
        dtype=np.int32,
    )


def draw_detection_debug(
    image: Image,
    corners: np.ndarray,
    area_ratio: float,
    method: str,
    rotation_angle: float,
) -> Image:
    debug = image.copy()
    if corners.size:
        cv2.polylines(debug, [corners], True, (107, 121, 0), 5, cv2.LINE_AA)
        for index, point in enumerate(corners):
            cv2.circle(debug, tuple(point.tolist()), 10, (107, 121, 0), -1, cv2.LINE_AA)
            cv2.circle(debug, tuple(point.tolist()), 4, (255, 255, 255), -1, cv2.LINE_AA)
            cv2.putText(
                debug,
                f"P{index + 1}",
                (int(point[0]) + 12, int(point[1]) - 12),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (64, 64, 64),
                2,
                cv2.LINE_AA,
            )
        label = f"Document {area_ratio * 100:.1f}% | {rotation_angle:.1f} deg | {method}"
    else:
        label = "No document contour detected"
    cv2.rectangle(debug, (16, 16), (min(debug.shape[1] - 16, 720), 62), (255, 255, 255), -1)
    cv2.rectangle(debug, (16, 16), (min(debug.shape[1] - 16, 720), 62), (64, 64, 64), 1)
    cv2.putText(
        debug,
        label,
        (28, 47),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (64, 64, 64),
        2,
        cv2.LINE_AA,
    )
    return debug


def detect_document(image: Image, document_hint: str = "auto") -> DetectionResult:
    if image.size == 0:
        raise ValueError("The uploaded image could not be decoded")
    height, width = image.shape[:2]
    image_area = float(width * height)
    working_scale = min(1.0, 1800.0 / max(height, width))
    resized = (
        cv2.resize(image, None, fx=working_scale, fy=working_scale, interpolation=cv2.INTER_AREA)
        if working_scale < 1
        else image
    )
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    denoised_gray = cv2.medianBlur(gray, 5)
    blurred = cv2.GaussianBlur(denoised_gray, (7, 7), 0)
    edges = cv2.Canny(blurred, 40, 130)
    kernel = np.ones((5, 5), dtype=np.uint8)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
    _, otsu = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    otsu = cv2.morphologyEx(otsu, cv2.MORPH_CLOSE, kernel, iterations=1)
    adaptive_block_size = max(31, min(151, (min(resized.shape[:2]) // 4) * 2 + 1))
    adaptive = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        adaptive_block_size,
        7,
    )
    adaptive = cv2.morphologyEx(adaptive, cv2.MORPH_CLOSE, kernel, iterations=1)
    working_area = float(resized.shape[0] * resized.shape[1])
    all_candidates: list[tuple[np.ndarray, str]] = []
    for candidates in (
        _contour_candidates(edges, "canny"),
        _contour_candidates(otsu, "otsu"),
        _contour_candidates(cv2.bitwise_not(otsu), "otsu_inverted"),
        _contour_candidates(adaptive, "adaptive"),
        _contour_candidates(cv2.bitwise_not(adaptive), "adaptive_inverted"),
    ):
        all_candidates.extend(candidates)
    ranked = _diverse_candidates(_rank_valid_candidates(gray, edges, all_candidates, working_area))
    best_candidate = ranked[0] if ranked else None
    full_frame_score = _full_frame_likelihood(gray, edges)
    prefer_full_frame = document_hint in {"id_card", "receipt", "paper_document"}
    use_full_frame = (best_candidate is None and full_frame_score >= 1.5) or (
        prefer_full_frame and full_frame_score > 1.35
    )
    alternatives: list[np.ndarray] = []
    alternative_methods: list[str] = []
    if use_full_frame:
        best = _full_frame_corners(resized.shape)
        method = "full_frame_scan"
        selection_score = full_frame_score
    elif (
        best_candidate is not None
        and best_candidate[3]["area_ratio"] < 0.16
        and full_frame_score > 2.1
    ):
        best = _full_frame_corners(resized.shape)
        method = "full_frame_text_document"
        selection_score = full_frame_score
    elif best_candidate is None:
        empty = np.empty((0, 2), dtype=np.int32)
        debug = draw_detection_debug(image, empty, 0, "none", 0)
        return DetectionResult(False, empty, debug, 0, 0, "none", full_frame_score, [], [])
    else:
        selection_score, best, method, _ = best_candidate
        alternatives = [item[1] for item in ranked[1:]]
        alternative_methods = [item[2] for item in ranked[1:]]

    def to_original(points: np.ndarray) -> np.ndarray:
        scaled_points = (points / working_scale).astype(np.int32) if working_scale < 1 else points
        scaled_points[:, 0] = np.clip(scaled_points[:, 0], 0, width - 1)
        scaled_points[:, 1] = np.clip(scaled_points[:, 1], 0, height - 1)
        return scaled_points

    best = to_original(best)
    alternatives = [to_original(points) for points in alternatives]
    top_left, top_right, _, _ = order_points(best)
    rotation_angle = degrees(
        atan2(float(top_right[1] - top_left[1]), float(top_right[0] - top_left[0]))
    )
    area_ratio = abs(cv2.contourArea(best)) / image_area
    return DetectionResult(
        True,
        best,
        draw_detection_debug(image, best, area_ratio, method, rotation_angle),
        round(rotation_angle, 2),
        round(area_ratio, 4),
        method,
        round(selection_score, 4),
        alternatives,
        alternative_methods,
    )
