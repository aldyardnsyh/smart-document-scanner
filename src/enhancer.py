import subprocess
from pathlib import Path

import cv2
import numpy as np

from .config import CPP_ENHANCER_PATH

Image = np.ndarray


def _python_enhance(image: Image, fast_denoise: bool) -> Image:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if fast_denoise:
        denoised = cv2.fastNlMeansDenoising(gray, None, 12, 7, 21)
    else:
        denoised = cv2.bilateralFilter(gray, 5, 35, 35)
    clahe = cv2.createCLAHE(clipLimit=2.4, tileGridSize=(8, 8))
    contrasted = clahe.apply(denoised)
    threshold = cv2.adaptiveThreshold(
        contrasted,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        9,
    )
    kernel = np.ones((2, 2), dtype=np.uint8)
    threshold = cv2.morphologyEx(threshold, cv2.MORPH_OPEN, kernel)
    blurred = cv2.GaussianBlur(contrasted, (0, 0), 1.1)
    sharpened = cv2.addWeighted(blurred, 1.7, contrasted, -0.7, 0)
    return cv2.cvtColor(cv2.addWeighted(sharpened, 0.68, threshold, 0.32, 0), cv2.COLOR_GRAY2BGR)


def _cpp_enhance(
    image: Image,
    output_path: Path,
    binary_path: Path,
    fast_denoise: bool,
) -> Image | None:
    if not binary_path.exists():
        return None
    output_path.parent.mkdir(parents=True, exist_ok=True)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape
    input_path = output_path.with_name(f"{output_path.stem}_cpp_input.raw")
    raw_output_path = output_path.with_name(f"{output_path.stem}_cpp_output.raw")
    gray.astype(np.uint8).tofile(input_path)
    command = [
        str(binary_path),
        str(input_path),
        str(raw_output_path),
        "31",
        str(width),
        str(height),
    ]
    if fast_denoise:
        command.append("--fast-denoise")
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=45, check=False)
        if completed.returncode != 0:
            return None
        processed = np.fromfile(raw_output_path, dtype=np.uint8)
        if processed.size != gray.size:
            return None
        enhanced = cv2.cvtColor(processed.reshape(gray.shape), cv2.COLOR_GRAY2BGR)
        if not cv2.imwrite(str(output_path), enhanced):
            return None
        return enhanced
    except (OSError, subprocess.TimeoutExpired):
        return None
    finally:
        input_path.unlink(missing_ok=True)
        raw_output_path.unlink(missing_ok=True)


def enhance_image(
    image: Image,
    output_path: Path | None = None,
    binary_path: Path = CPP_ENHANCER_PATH,
    cpp_acceleration: bool = True,
    fast_denoise: bool = False,
) -> tuple[Image, dict[str, str]]:
    enhanced: Image | None = None
    accelerator = "python"
    if cpp_acceleration and output_path is not None:
        enhanced = _cpp_enhance(image, output_path, binary_path, fast_denoise)
        if enhanced is not None:
            accelerator = "cpp"
    if enhanced is None:
        enhanced = _python_enhance(image, fast_denoise)
        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(output_path), enhanced)
    return enhanced, {"accelerator": accelerator, "threshold": "adaptive_gaussian"}
