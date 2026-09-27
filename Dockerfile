FROM node:22-alpine AS frontend

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./frontend/
RUN npm --prefix frontend ci
COPY frontend ./frontend
RUN npm --prefix frontend run build

FROM python:3.11-slim AS cpp-builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends cmake g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY src/cpp_module ./src/cpp_module
RUN mkdir -p bin \
    && g++ -std=c++17 -O3 -s src/cpp_module/enhancer.cpp -o bin/document_enhancer

FROM python:3.11-slim

# No OCR system package is installed. The OCR engine is PP-OCR executed through ONNX
# Runtime, and its detection, angle-classification and recognition models ship inside the
# `rapidocr` wheel, so the image carries no model download step at build or at run time.
# The C++ accelerator links only libstdc++ and libgomp, which ONNX Runtime also needs.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libstdc++6 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt requirements-ocr.txt ./
# `rapidocr` configures itself through `omegaconf`, which requires one exact
# `antlr4-python3-runtime` version that PyPI no longer serves. Installing the vendored
# source distribution last restores the version `omegaconf` expects. See requirements-ocr.txt.
COPY vendor/antlr4-python3-runtime-4.9.3.tar.gz ./vendor/
# The OCR runtime is installed with `--no-deps` so it cannot pull in the non-headless
# OpenCV build, which would need libGL that a headless container does not ship.
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir --no-deps -r requirements-ocr.txt \
    && pip install --no-cache-dir --no-deps vendor/antlr4-python3-runtime-4.9.3.tar.gz
COPY api.py app.py ./
COPY src ./src
COPY scripts/check_dataset_leakage.py ./scripts/check_dataset_leakage.py
COPY --from=cpp-builder /app/bin/document_enhancer ./bin/document_enhancer
COPY --from=frontend /app/frontend/out ./frontend/out

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OMP_NUM_THREADS=2

# Fail the build rather than ship an image whose OCR cannot start, and assert at build
# time that no ground-truth vocabulary has leaked into the extraction source.
RUN python -c "import onnxruntime, cv2, numpy; from src.ocr_engine import get_engine; assert get_engine() is not None, 'OCR engine failed to initialise'" \
    && python scripts/check_dataset_leakage.py

EXPOSE 8000
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
