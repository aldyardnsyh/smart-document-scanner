import json
import shutil
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import JOB_DIR, OUTPUT_DIR
from .pipeline import ScanOptions, process_image, write_json


def _now() -> str:
    return datetime.now(UTC).isoformat()


class JobManager:
    def __init__(self, job_directory: Path = JOB_DIR, output_directory: Path = OUTPUT_DIR) -> None:
        self.job_directory = job_directory
        self.output_directory = output_directory
        self.jobs: dict[str, dict[str, Any]] = {}
        self.lock = threading.RLock()
        self.job_directory.mkdir(parents=True, exist_ok=True)
        self.output_directory.mkdir(parents=True, exist_ok=True)

    def _path(self, job_id: str) -> Path:
        return self.job_directory / f"{job_id}.json"

    def _persist(self, record: dict[str, Any]) -> None:
        write_json(self._path(str(record["id"])), record)

    @staticmethod
    def _public(record: dict[str, Any]) -> dict[str, Any]:
        public = dict(record)
        public.pop("input_path", None)
        return public

    def create_job(
        self,
        original_name: str,
        input_path: Path,
        options: ScanOptions,
    ) -> dict[str, Any]:
        job_id = uuid.uuid4().hex[:12]
        record: dict[str, Any] = {
            "id": job_id,
            "original_name": original_name,
            "input_path": str(input_path),
            "options": {
                "document_type": options.document_type,
                "fast_denoise": options.fast_denoise,
                "cpp_acceleration": options.cpp_acceleration,
                "ocr_language": options.ocr_language,
            },
            "status": "queued",
            "stage": "queued",
            "progress": 0,
            "message": "Waiting for processing",
            "created_at": _now(),
            "updated_at": _now(),
            "result": None,
            "error": None,
        }
        with self.lock:
            self.jobs[job_id] = record
            self._persist(record)
        return self._public(record)

    def update(self, job_id: str, **changes: Any) -> dict[str, Any] | None:
        with self.lock:
            record = self.jobs.get(job_id)
            if record is None:
                return None
            record.update(changes)
            record["updated_at"] = _now()
            self._persist(record)
            return self._public(record)

    def run(self, job_id: str) -> None:
        with self.lock:
            record = self.jobs.get(job_id)
            if record is None:
                return
            input_path = Path(str(record["input_path"]))
            options = ScanOptions(**record["options"])
        self.update(
            job_id,
            status="processing",
            stage="ingest",
            progress=4,
            message="Preparing image",
        )
        try:

            def progress(stage: str, percent: int, message: str) -> None:
                self.update(job_id, stage=stage, progress=percent, message=message)

            result = process_image(input_path, self.output_directory, job_id, options, progress)
            if not result["document_detected"]:
                self.update(
                    job_id,
                    status="failed",
                    stage="complete",
                    progress=100,
                    message="No document detected",
                    result=result,
                    error={
                        "code": "NO_DOCUMENT",
                        "message": (
                            "No document contour was detected. "
                            "Try a clearer image with more contrast."
                        ),
                    },
                )
                return
            # A detected document can still yield nothing: a blank card is found, warped, and read
            # as empty. Reporting that as a completed run would show an OCR reading of 0% with no
            # fields, which reads as a success to the caller, so an empty extraction is a failure.
            if (
                result.get("extracted_field_count", 0) == 0
                and not (result.get("raw_text") or "").strip()
            ):
                self.update(
                    job_id,
                    status="failed",
                    stage="complete",
                    progress=100,
                    message="No readable text on the document",
                    result=result,
                    error={
                        "code": "NO_CONTENT",
                        "message": (
                            "The document was detected, but no readable text was found on it, "
                            "so no fields could be extracted. Check that the document is not "
                            "blank and is lit well enough to read."
                        ),
                    },
                )
                return
            self.update(
                job_id,
                status="completed",
                stage="complete",
                progress=100,
                message="Processing complete",
                result=result,
            )
        except Exception as error:
            self.update(
                job_id,
                status="failed",
                stage="error",
                progress=100,
                message="Processing failed",
                error={"code": "PROCESSING_ERROR", "message": str(error)},
            )

    def get(self, job_id: str) -> dict[str, Any] | None:
        if len(job_id) != 12 or not job_id.isalnum():
            return None
        with self.lock:
            record = self.jobs.get(job_id)
            if record is None:
                path = self._path(job_id)
                if not path.exists():
                    return None
                try:
                    record = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    return None
                if record.get("id") != job_id:
                    return None
                self.jobs[job_id] = record
            return self._public(record)

    def delete(self, job_id: str) -> bool:
        if len(job_id) != 12 or not job_id.isalnum():
            return False
        with self.lock:
            record = self.jobs.get(job_id)
            if record is None:
                path = self._path(job_id)
                if not path.exists():
                    return False
                try:
                    record = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    return False
            input_path = Path(str(record.get("input_path", "")))
            if input_path.name and input_path.is_file():
                input_path.unlink(missing_ok=True)
            output_path = self.output_directory / job_id
            if output_path.is_dir():
                shutil.rmtree(output_path)
            self._path(job_id).unlink(missing_ok=True)
            self.jobs.pop(job_id, None)
            return True

    def history(self) -> list[dict[str, Any]]:
        loaded: list[dict[str, Any]] = []
        for path in self.job_directory.glob("*.json"):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            self.jobs[str(record.get("id", path.stem))] = record
            loaded.append(self._public(record))
        loaded.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
        return loaded
