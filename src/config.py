import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
JOB_DIR = DATA_DIR / "jobs"
OUTPUT_DIR = ROOT_DIR / "outputs"
DEBUG_DIR = OUTPUT_DIR / "debug"
PROCESSED_DIR = OUTPUT_DIR / "processed"
FRONTEND_OUT_DIR = ROOT_DIR / "frontend" / "out"
CPP_ENHANCER_PATH = ROOT_DIR / "bin" / (
    "document_enhancer.exe" if os.name == "nt" else "document_enhancer"
)
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
DOCUMENT_TYPES = {"auto", "business_card", "id_card", "receipt", "paper_document"}


def ensure_directories() -> None:
    for directory in (
        UPLOAD_DIR,
        JOB_DIR,
        OUTPUT_DIR,
        DEBUG_DIR,
        PROCESSED_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)
