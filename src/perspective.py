from math import hypot

import cv2
import numpy as np

from .detector import order_points

Image = np.ndarray


def four_point_transform(image: Image, corners: np.ndarray) -> Image:
    if image.size == 0:
        raise ValueError("The image is empty")
    points = order_points(corners)
    top_left, top_right, bottom_right, bottom_left = points
    width_a = hypot(
        float(bottom_right[0] - bottom_left[0]),
        float(bottom_right[1] - bottom_left[1]),
    )
    width_b = hypot(
        float(top_right[0] - top_left[0]),
        float(top_right[1] - top_left[1]),
    )
    height_a = hypot(
        float(top_right[0] - bottom_right[0]),
        float(top_right[1] - bottom_right[1]),
    )
    height_b = hypot(
        float(top_left[0] - bottom_left[0]),
        float(top_left[1] - bottom_left[1]),
    )
    output_width = max(1, int(round(max(width_a, width_b))))
    output_height = max(1, int(round(max(height_a, height_b))))
    destination = np.array(
        [
            [0, 0],
            [output_width - 1, 0],
            [output_width - 1, output_height - 1],
            [0, output_height - 1],
        ],
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(points.astype(np.float32), destination)
    return cv2.warpPerspective(
        image,
        transform,
        (output_width, output_height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
