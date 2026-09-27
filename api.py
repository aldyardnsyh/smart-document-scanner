import mimetypes
import os
from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.config import (
    ALLOWED_IMAGE_EXTENSIONS,
    CPP_ENHANCER_PATH,
    DOCUMENT_TYPES,
    FRONTEND_OUT_DIR,
    MAX_UPLOAD_BYTES,
    OUTPUT_DIR,
    UPLOAD_DIR,
    ensure_directories,
)
from src.jobs import JobManager
from src.ocr_engine import engine_available, engine_error
from src.pipeline import ScanOptions

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("font/woff2", ".woff2")
ensure_directories()
app = FastAPI(
    title="Smart Document Scanner API",
    version="1.0.0",
    description=(
        "Document detection, perspective correction, enhancement, OCR, and structured extraction."
    ),
)
next_origins = [
    origin.strip() for origin in os.getenv("NEXT_ORIGINS", "").split(",") if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        *next_origins,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
manager = JobManager()
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")


@app.get("/api/health")
def health() -> dict[str, object]:
    return {
        "status": "online",
        "pipeline": ["detect", "correct", "enhance", "ocr", "parse"],
        "ocr_engine": "ppocr-onnxruntime",
        "ocr_engine_available": engine_available(),
        "ocr_engine_error": engine_error(),
        "cpp_accelerator_available": CPP_ENHANCER_PATH.exists(),
    }


@app.post("/api/process", status_code=202)
@app.post("/process", status_code=202, include_in_schema=False)
async def create_process(
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File()],
    doc_type: Annotated[str, Form()] = "auto",
    fast_denoise: Annotated[bool, Form()] = False,
    cpp_acceleration: Annotated[bool, Form()] = True,
) -> dict[str, object]:
    if doc_type not in DOCUMENT_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported document type")
    original_name = Path(file.filename or "document.jpg").name
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Upload a JPG, PNG, WEBP, BMP, or TIFF image")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    await file.close()
    if not content:
        raise HTTPException(status_code=422, detail="The uploaded file is empty")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="The uploaded file exceeds the 10 MB limit")
    input_path = UPLOAD_DIR / f"{uuid_file_name(original_name)}"
    input_path.write_bytes(content)
    options = ScanOptions(
        document_type=doc_type,
        fast_denoise=fast_denoise,
        cpp_acceleration=cpp_acceleration,
    )
    record = manager.create_job(original_name, input_path, options)
    background_tasks.add_task(manager.run, str(record["id"]))
    return record


def uuid_file_name(original_name: str) -> str:
    import uuid

    return f"{uuid.uuid4().hex[:12]}{Path(original_name).suffix.lower()}"


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, object]:
    record = manager.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return record


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str) -> dict[str, bool]:
    if not manager.delete(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    return {"deleted": True}


@app.get("/api/history")
def history(
    search: Annotated[str | None, Query(max_length=100)] = None,
    document_type: str | None = None,
    status: str | None = None,
) -> list[dict[str, object]]:
    records = manager.history()
    if search:
        needle = search.casefold()
        records = [
            record for record in records if needle in str(record["original_name"]).casefold()
        ]
    if document_type and document_type != "all":
        records = [
            record
            for record in records
            if (record.get("result") or {}).get("fields", {}).get("document_type") == document_type
        ]
    if status and status != "all":
        records = [record for record in records if record.get("status") == status]
    return records


if FRONTEND_OUT_DIR.exists():
    next_assets = FRONTEND_OUT_DIR / "_next"
    if next_assets.exists():
        app.mount("/_next", StaticFiles(directory=next_assets), name="next-assets")

    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def frontend(full_path: str) -> FileResponse:
        if full_path.startswith(("api/", "outputs/", "docs", "openapi.json", "_next/")):
            raise HTTPException(status_code=404, detail="Not found")
        export_root = FRONTEND_OUT_DIR.resolve()
        candidates = [
            (export_root / full_path).resolve(),
            (export_root / f"{full_path}.html").resolve(),
            (export_root / full_path / "index.html").resolve(),
        ]
        if full_path.endswith(".txt") and "__next." in full_path:
            prefix, filename = full_path.rsplit("/", 1) if "/" in full_path else ("", full_path)
            route_token, page_token = filename[:-4].rsplit(".", 1)
            nested = (
                f"{prefix}/{route_token}/{page_token}.txt"
                if prefix
                else f"{route_token}/{page_token}.txt"
            )
            candidates.append((export_root / nested).resolve())
        for candidate in candidates:
            if export_root in candidate.parents and candidate.is_file():
                return FileResponse(candidate)
        if Path(full_path).suffix:
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(export_root / "index.html")
