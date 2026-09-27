# Smart Document Scanner & OCR Service

A document scanning pipeline that detects a card or document in a photograph, corrects the
perspective, enhances it for legibility, reads it with a neural OCR engine, and emits
structured JSON with a confidence and provenance for every field.

**Live demo:** <https://smart-document-scanner-production.up.railway.app/>

The deployed instance runs the same `Dockerfile` as this repository, built by Railway from the
committed source. The three ways to run it behave identically:

| | How |
| --- | --- |
| Deployed | Open [the live demo](https://smart-document-scanner-production.up.railway.app/) and upload an image |
| Docker | `docker build -t smart-document-scanner . && docker run -p 8000:8000 smart-document-scanner` |
| Local | `uvicorn api:app --host 127.0.0.1 --port 8000`, or `python app.py --input ./dataset` for the CLI |

See [Setup instructions](#setup-instructions) for the local prerequisites, and
[Deployment](#deployment) for how the hosted instance is provisioned.

Recognising one card takes roughly 45 seconds on CPU, because the engine reads four
preprocessing variants and scores the best crop. The service itself responds immediately.

## Contents

- [Stack](#stack)
- [Setup instructions](#setup-instructions)
- [Docker usage](#docker-usage)
- [Deployment](#deployment)
- [Example output](#example-output)
- [Architecture overview](#architecture-overview)
- [Algorithm explanation](#algorithm-explanation)
- [Preprocessing decisions](#preprocessing-decisions)
- [OCR approach](#ocr-approach)
- [Dataset](#dataset)
- [Accuracy](#accuracy)
- [Error analysis](#error-analysis)
- [Testing instructions](#testing-instructions)
- [Assumptions](#assumptions)
- [Tradeoffs](#tradeoffs)
- [Known limitations](#known-limitations)
- [Performance notes](#performance-notes)
- [Repository layout](#repository-layout)

---

## Stack

| Layer         | Choice                                     |
| ------------- | ------------------------------------------ |
| Language      | Python 3.11                                |
| Imaging       | OpenCV 4.14 (`opencv-python-headless`)   |
| Native module | C++17, compiled in a separate Docker stage |
| OCR           | RapidOCR (PP-OCRv6) on ONNX Runtime, CPU   |
| Service       | FastAPI + Uvicorn                          |
| UI            | Next.js 16, static export, React 19        |
| Tests         | pytest, Playwright                         |

---

## Setup instructions

### Requirements

- Docker (recommended), or
- Python 3.11+, a C++17 compiler, and Node 22 for the frontend

### Run with Docker

```bash
docker build -t smart-document-scanner .
docker run -p 8000:8000 smart-document-scanner
```

Open [http://localhost:8000](http://localhost:8000). The build compiles the C++ module, exports the frontend, and
verifies that the OCR engine initialises. If the engine cannot load, the build fails rather than
producing a container that accepts uploads it cannot read.

The same image is what runs [the live demo](https://smart-document-scanner-production.up.railway.app/),
so a local build and the deployed service behave identically.

With Compose:

```bash
docker compose up --build
```

### Run locally

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # or: source .venv/bin/activate
pip install -r requirements.txt
pip install --no-deps -r requirements-ocr.txt
pip install vendor/antlr4-python3-runtime-4.9.3.tar.gz
```

The three install steps are deliberate. `rapidocr` declares `opencv-python`, the non-headless
build, which links `libGL`; installing it alongside `opencv-python-headless` produces a broken
`cv2` import, so the OCR package is installed with `--no-deps` and its real requirements are
listed explicitly in `requirements.txt`.

The vendored source distribution is required because `omegaconf 2.3.1` depends on
`antlr4-python3-runtime==4.9.3` exactly, that version is no longer published, and a current
4.13 release makes the engine fail at import with `Could not deserialize ATN with version 3 (expected 4)`. It is 114 KB of pure Python and must be installed after `requirements.txt`.

Build the C++ module and the frontend:

```bash
g++ -std=c++17 -O3 -o bin/document_enhancer src/cpp_module/enhancer.cpp
cd frontend && npm ci && npm run build
```

The C++ accelerator is optional at run time. The pipeline falls back to the Python
implementation and reports which one it used in `enhancement.accelerator`.

### CLI

The batch CLI processes a directory of images and writes one folder per image. This walkthrough
uses the bundled dataset, so it works immediately after setup.

**1. Process a whole directory**

`--input` accepts a directory, and the directory is walked recursively, so nested folders are
picked up too. Every supported image inside becomes its own job and its own output folder.

The bundled `dataset/` holds 11 images, so this single command runs all of them:

```bash
python app.py --input ./dataset --output ./outputs
```

An interactive terminal prints a session header, then one block per image:

```
   ____  ____  ____     Smart Document Scanner
  / ___||  _ \/ ___|    detect - correct - enhance - read - parse
  \___ \| | | \___ \    document detection and structured extraction
   ___) | |_| |___) |
  |____/|____/|____/

  SDS  input : dataset
  SDS  images: 11
  SDS  output: outputs
--------------------------------------------------------------
[1/11] Processing dataset/card_blank.jpg
  24% detect: Document candidates analyzed
  52% correct: Perspective corrected
  68% enhance: Enhancement complete
 100% complete: Processing complete, 0 of 0 recognised fields extracted
[2/11] Processing dataset/card_blurry.jpg
  24% detect: Document candidates analyzed
  68% enhance: Enhancement complete
 100% complete: Processing complete, 7 of 9 recognised fields extracted
...
[11/11] Processing dataset/no_document.jpg
  24% detect: Document candidates analyzed
 100% complete: Processing complete, 0 of 0 recognised fields extracted
Processed 11 image(s). Summary: outputs/batch_summary.json
```

Expect roughly 50 seconds per image, so the full dataset takes around ten minutes. Each block
ends with the honest result: how many field types were recovered, out of how many the parser can
produce for that document type. `card_blank` and `no_document` legitimately report `0 of 0`,
because nothing readable was found; both are recorded as failures rather than empty successes.

**What a directory run produces**

One folder per image, named `cli-<number>-<original name>`, plus a summary of the whole batch:

```
outputs/
  batch_summary.json
  cli-001-card_blank/
    original.jpg
    metadata.json
    debug/document_detected.jpg
    processed/corrected_document.jpg
    processed/enhanced_document.jpg
  cli-002-card_blurry/
    ...
  cli-011-no_document/
    ...
```

`batch_summary.json` holds the result of every job in the run, which is what the scorer reads in
step 5. Open any single `metadata.json` to inspect one document in full.

**2. Process a single image**

```bash
python app.py --input ./dataset/card_lowlight.jpg --output ./outputs
```

**3. Process a folder of your own**

```bash
# any directory, nested folders included
python app.py --input ~/scans/receipts --output ./outputs
```

`--input` takes a single path, and a directory is walked recursively with `rglob`, so nested
folders are picked up automatically. Non-image files are skipped. To process a specific subset,
either stage the files into their own folder, or run the CLI once per file.

Each run writes `batch_summary.json` listing every job, which is what the scorer reads in step 5.

**4. Inspect the artefacts**

Each run creates `outputs/<job_id>/`:

| Path                                 | Contents                                |
| ------------------------------------ | --------------------------------------- |
| `metadata.json`                    | The full response contract. Start here. |
| `original.jpg`                     | The uploaded image, unmodified          |
| `debug/document_detected.jpg`      | Detected contour and corner overlay     |
| `processed/corrected_document.jpg` | Perspective-corrected top-down scan     |
| `processed/enhanced_document.jpg`  | Enhanced image that was fed to OCR      |

```bash
# print just the extracted fields
python -c "import json;d=json.load(open('outputs/cli-001-card_lowlight/metadata.json'));\
[print(f['name'],'=',f['value']) for f in d['fields']['fields']]"
```

**5. Score the run against the ground truth**

```bash
python scripts/evaluate_fields.py ./outputs/batch_summary.json
```

```
file                     mean  keys  exact  miss   fp
-----------------------------------------------------
card_blurry             0.856     8      7     1    0
card_lowlight           0.875     8      7     1    0
...
OVERALL                 0.723    64     43    11    2
```

**6. Use your own images**

Point `--input` at any file or directory. Non-image files are skipped. The scorer needs matching
ground truth in `tests/fixtures/valid_extraction.json`, so skip step 4 for your own images.

| Flag               | Effect                                                                              |
| ------------------ | ----------------------------------------------------------------------------------- |
| `--doc-type`     | `auto` (default), `business_card`, `id_card`, `receipt`, `paper_document` |
| `--no-cpp`       | Disable the native C++ accelerator and use the Python path                          |
| `--fast-denoise` | Cheaper denoising: faster, slightly less clean                                      |
| `--output`       | Output directory, default`outputs/`                                               |

The header is printed only to an interactive terminal. When output is piped or redirected, the
run stays a single machine-readable line so it can be fed to `jq`. The art is plain ASCII, so it
renders the same on a legacy Windows code page as it does on a UTF-8 terminal.

### Does a virtual environment matter?

Yes, and using one is the recommended path on every platform. A virtual environment keeps the
project's pinned dependencies isolated from whatever else is installed, which matters here
because the OCR stack is exact about versions: `omegaconf` and `antlr4` must match, and two
different OpenCV builds in the same interpreter break the `cv2` import. A venv guarantees the
versions this project was tested with.

The one exception is Docker, which needs no venv on the host at all: the image already contains
the interpreter, the dependencies, the compiled C++ module, and the built frontend.

| Environment   | Interpreter           | Native module                          | Use when                             |
| ------------- | --------------------- | -------------------------------------- | ------------------------------------ |
| Docker        | in the image          | built in the image                     | Verifying the setup, or deploying    |
| Local venv    | `.venv`             | build it yourself, or pass`--no-cpp` | Development, quick single-image runs |
| System Python | whatever is installed | build it yourself                      | Not recommended                      |

### API

The same pipeline is exposed over HTTP. Start a local server:

```bash
uvicorn api:app --host 127.0.0.1 --port 8000
```

The service serves the REST API and the built frontend from one process, so
[http://localhost:8000](http://localhost:8000) is both the API root and the UI.

The examples below use a local server. To call the deployed instance instead, set the base URL
once and reuse it:

```bash
# local
export BASE=http://127.0.0.1:8000

# or the public deployment
export BASE=https://smart-document-scanner-production.up.railway.app
```

**Check the service is ready**

```bash
curl http://127.0.0.1:8000/api/health
```

```json
{
  "status": "online",
  "pipeline": ["detect", "correct", "enhance", "ocr", "parse"],
  "ocr_engine": "ppocr-onnxruntime",
  "ocr_engine_available": true,
  "ocr_engine_error": null,
  "cpp_accelerator_available": true
}
```

`ocr_engine_available` is the one to watch. If it is `false`, `ocr_engine_error` says why, and
the service will accept uploads it cannot read. This endpoint is also what the Compose health
check uses.

**Submit an image**

```bash
curl -X POST http://127.0.0.1:8000/api/process -F "file=@./dataset/card_lowlight.jpg"
```

Returns `202 Accepted` with a job to poll:

```json
{
  "id": "a1b2c3d4e5f6",
  "original_name": "card_lowlight.jpg",
  "options": {
    "document_type": "auto",
    "fast_denoise": false,
    "cpp_acceleration": true,
    "ocr_language": "eng+ind"
  },
  "status": "queued",
  "stage": "queued",
  "progress": 0,
  "message": "Waiting for processing",
  "created_at": "2026-09-27T10:14:02Z",
  "updated_at": "2026-09-27T10:14:02Z",
  "result": null,
  "error": null
}
```

**Poll for the result**

Recognition takes tens of seconds, so the endpoint is asynchronous rather than holding the
connection open. `stage`, `progress`, and `message` are what the progress UI renders.

```bash
curl http://127.0.0.1:8000/api/jobs/a1b2c3d4e5f6
```

```json
{
  "id": "a1b2c3d4e5f6",
  "status": "completed",
  "stage": "complete",
  "progress": 100,
  "message": "Processing complete",
  "result": { "...": "the metadata.json described in Example output" }
}
```

`status` moves through `queued` → `processing` → `completed` or `failed`. A failure carries a
reason rather than an empty result:

```json
{
  "id": "a1b2c3d4e5f6",
  "status": "failed",
  "stage": "complete",
  "message": "No document detected",
  "error": {
    "code": "NO_DOCUMENT",
    "message": "No document contour was detected. Try a clearer image with more contrast."
  }
}
```

The `code` is one of `NO_DOCUMENT`, `NO_CONTENT`, or `PROCESSING_ERROR`.

**List history**

```bash
curl "http://127.0.0.1:8000/api/history?document_type=business_card&search=card"
```

All three query parameters are optional: `search` matches the file name, `document_type` and
`status` filter on the recorded value.

```bash
curl "http://127.0.0.1:8000/api/history?status=failed"
```

**Delete a job**

```bash
curl -X DELETE http://127.0.0.1:8000/api/jobs/a1b2c3d4e5f6
```

Removes the record, the upload, and every generated artefact:

```json
{ "deleted": true }
```

### Endpoint reference

| Method     | Path                   | Purpose                           |
| ---------- | ---------------------- | --------------------------------- |
| `GET`    | `/api/health`        | Service and OCR engine status     |
| `POST`   | `/api/process`       | Submit an image, returns a job id |
| `GET`    | `/api/jobs/{job_id}` | Poll a job, or read its result    |
| `GET`    | `/api/history`       | List past jobs, filterable        |
| `DELETE` | `/api/jobs/{job_id}` | Delete a job and its files        |

### API

```bash
uvicorn api:app --host 127.0.0.1 --port 8000
```

Serves the REST API and the built frontend from the same process.

---

## Docker usage

The image is a three-stage build:

1. **`frontend`** — `node:22`, runs `next build` and exports static assets.
2. **`cpp-builder`** — `python:3.11-slim` plus `g++`, compiles `document_enhancer` with
   `-O3`.
3. **`runtime`** — `python:3.11-slim`. Installs the Python and OCR requirements and the vendored
   `antlr4` distribution, copies in the native module and the frontend export, then runs two
   gates: the OCR engine must construct, and the anti-hardcoding guard must pass.

The runtime stage installs only `libstdc++6` and `libgomp1` beyond the Python base, which are
what ONNX Runtime and the native module link against. No model download happens at build or run
time; the PP-OCR weights ship inside the `rapidocr` wheel.

```bash
docker run -p 8000:8000 smart-document-scanner
docker run -p 8000:8000 -v "$(pwd)/my-scans:/app/data" smart-document-scanner
```

`docker-compose.yml` mounts the dataset read-only for batch runs and declares a health check
that fails when `ocr_engine_available` is false, so a container that cannot read documents is
reported unhealthy rather than quietly accepting uploads.

---

## Architecture overview

```
photo
  |
  +-- detect      edge -> morphology -> contours -> approxPolyDP -> quad scoring
  |
  +-- correct     homography from the four corners -> top-down scan
  |
  +-- enhance     Python and C++ candidates for the same stage
  |
  +-- crop        every candidate crop is OCR'd; the winner is chosen on recovered
  |               text coverage, not on confidence
  |
  +-- read        PP-OCR detection -> angle classification -> recognition
  |               four image variants, every reading retained
  |
  +-- parse       layout model -> per-line classification -> cross-variant vote
                  -> evidence-tiered field values
```

Each stage writes its artefact, so any result can be traced back to the pixels that produced it:

```
outputs/<job_id>/
  original.jpg
  debug/document_detected.jpg       contour and corner overlay
  processed/corrected_document.jpg  homography result
  processed/enhanced_document.jpg   enhancement result
  metadata.json                     the full response contract
```

| Module                          | Responsibility                                       |
| ------------------------------- | ---------------------------------------------------- |
| `src/detector.py`             | Contour-based document detection                     |
| `src/perspective.py`          | Corner ordering and homography                       |
| `src/enhancer.py`             | Enhancement, Python and native paths                 |
| `src/ocr_engine.py`           | RapidOCR wrapper, image variants, angle classifier   |
| `src/layout.py`               | Column detection, typography tiers, line model       |
| `src/field_parser.py`         | Field parsing, voting, confidence, residual grouping |
| `src/classifier.py`           | Document-type classification                         |
| `src/pipeline.py`             | Orchestration, crop selection, response contract     |
| `src/jobs.py`                 | Async job lifecycle and outcome reporting            |
| `src/cpp_module/enhancer.cpp` | Native enhancement implementation                    |

---

## Algorithm explanation

### Document detection

Grayscale and blur, then Canny edges at two thresholds. A morphological close joins fragmented
edges, contours are extracted, and `approxPolyDP` reduces each to a polygon. Quadrilaterals are
scored on area relative to the frame, aspect ratio, corner angles, and how much of the contour is
backed by real edge support.

Several candidates are retained instead of trusting the top-ranked one, because a card on a
cluttered desk often has its strongest edge clipped. When the detected quad covers little of the
frame, the full frame is added as a candidate so the crop scorer can compare a clipped
detection against an unclipped one on equal terms.

The response records which candidate won and how, in `detection_method`, `detection_selection`,
and `detection_score`.

### Perspective correction

Corners are ordered top-left, top-right, bottom-right, bottom-left, then fed to
`cv2.getPerspectiveTransform` and `cv2.warpPerspective`. The residual skew the homography does
not remove is reported as `rotation_angle` and handled by the OCR angle classifier.

### Crop selection

Each candidate crop is enhanced, OCR'd, and parsed. Crops are ranked on recovered text
coverage, not on mean token confidence. A tight zoom on one corner is highly confident and nearly
useless, so coverage has to outweigh confidence. Full-frame extraction is always available as a
candidate.

### Parsing

`src/layout.py` projects every detected line box onto the horizontal axis and splits the page
where a wide empty vertical band runs from top to bottom. Assigning a line to the band under its
centre makes the result independent of reading order, which matters because a two-column card
would otherwise interleave its left and right blocks and split a printed address across an
unrelated line.

Each line is then classified by printed label, and where no label is present, by morphology:
street words, region words, job titles, department and institution words. Runs of consecutive
lines that resolve to the same field are merged within their column. Candidates from all four
OCR variants are voted on, and the winner carries a confidence derived from token confidence
and evidence tier.

Text that no rule claims is not discarded. It is grouped into blocks by position, given a name
only where the content supports one, reported under `unclassified`, and offered back to the
address assembler when it continues an address that was cut short by an intervening line.

Fields that match no schema are surfaced rather than dropped, and every field carries a
confidence and a `source` label describing which rule produced it.

---

## Preprocessing decisions

- **Headless OpenCV only.** The non-headless build links `libGL`, which a server container does
  not have, and installing both produces a broken `cv2` import.
- **Four image variants instead of parameter tuning.** PP-OCR has no page-segmentation mode, so
  input diversity is the available lever: as-is, CLAHE-sharpened, adaptive-threshold, and
  shadow-normalised. All four are read and the parser votes across them.
- **The native module is a real accelerator, not a token dependency.** It is invoked as a
  separate process from `src/enhancer.py` and its output is compared against the Python result.
  Which one won is reported in the response.
- **Conservative blank detection.** A document is only called blank on edge density and
  luminance variance together. A clean high-contrast card has low edge density, so a single loose
  threshold would discard real documents.
- **Aspect ratio as a prior, not a constraint.** It biases detection towards cards and papers
  without excluding portrait receipts or A4 sheets.

---

## OCR approach

The engine is PP-OCRv6, distributed as the `rapidocr` package, running on ONNX Runtime on CPU.
The brief permits any open-source OCR library, and PP-OCR was selected over Tesseract because it
outperformed it on this dataset and ships an angle classifier, which matters for the rotated
captures.

Per image, recognition runs over four preprocessed variants. Detection is PP-OCR's text detector,
recognition is its recogniser, and an angle classifier corrects residual skew. Results are
returned as text lines with polygon geometry, so layout analysis works on line boxes rather than
words.

Weights ship inside the wheel, so the container performs no model download at build or run time.

### Dependency note

`rapidocr` configures itself through `omegaconf`, which pins `antlr4-python3-runtime==4.9.3`.
That version has been withdrawn from PyPI. `vendor/antlr4-python3-runtime-4.9.3.tar.gz` supplies
it, and the build installs it last. If the `omegaconf` pin changes, re-check which `antlr4`
version it requires before removing the vendored file.

---

## Example output

A real `metadata.json` for one business card, abridged to the fields that matter. The file
written to `outputs/<job_id>/` contains these plus the full OCR evidence, the candidate list,
and the residual text.

```json
{
  "job_id": "cli-001-card_lowlight",
  "document_detected": true,
  "rotation_angle": 0.0,
  "detection_area_ratio": 0.8852,
  "detection_method": "otsu_min_area_rect",
  "image_width": 1195,
  "image_height": 859,
  "processing_time_ms": 47440.63,
  "ocr_confidence": 0.9963,
  "extracted_field_count": 7,
  "recognised_field_count": 10,
  "extraction_coverage": 0.7,
  "fields": {
    "document_type": "business_card",
    "classification": {
      "document_type": "business_card",
      "score": 95.7
    },
    "fields": [
      {
        "name": "name",
        "value": "TOMOKAZU MARAKAMI",
        "confidence": 0.562,
        "source": "typographic_prominence"
      },
      {
        "name": "organization",
        "value": "STANFORD COMPUTER FORUM",
        "confidence": 0.562,
        "source": "organization_morphology"
      },
      {
        "name": "title",
        "value": "Visiting Scholar",
        "confidence": 0.562,
        "source": "job_title_morphology"
      },
      {
        "name": "address",
        "value": "350 Serra Mall, Packard Bldg, Rm 235, Stanford, CA 94305-9510",
        "confidence": 0.562,
        "source": "street_morphology"
      },
      {
        "name": "phone",
        "value": "1.650.725.7076",
        "confidence": 0.562,
        "source": "label:phone"
      },
      {
        "name": "fax",
        "value": "1.650.724.3648",
        "confidence": 0.562,
        "source": "label:fax"
      },
      {
        "name": "email",
        "value": "tmurakam@stanford.edu",
        "confidence": 0.562,
        "source": "email_shape"
      }
    ]
  }
}
```

Every field carries a `confidence` and a `source` naming the rule that produced it, so a value
can always be traced back to why the parser believed it.

A capture with nothing readable reports a failure rather than an empty success:

```json
{
  "document_detected": true,
  "extracted_field_count": 0,
  "recognised_field_count": 0,
  "extraction_coverage": 0.0,
  "fields": { "document_type": "business_card", "fields": [] }
}
```

with the job reported as `status: "failed"` and the reason
`NO_CONTENT`, "The document was detected, but no readable text was found on it."

## Dataset

The photographs in `dataset/` are from the public
[Ultralytics business cards dataset](https://platform.ultralytics.com/development-stride/datasets/business-cards),
used as an OCR and layout stress test. The set covers the conditions the brief names: low light,
motion blur, heavy sensor noise, partial shadow, rotation, zoom, and a card photographed on a
cluttered desk and on a sheet of paper.

`dataset/no_document.jpg` is generated rather than sourced, because the dataset above contains
no frame without a document and the brief requires a demonstrated failure case. It is a
synthetic gradient with drawn circles and contains no real content.

To use a different dataset, point the CLI at it and update the ground truth in
`tests/fixtures/valid_extraction.json`. The parser holds no vocabulary from these images; the
anti-hardcoding guard fails the build if dataset-specific strings appear in the extraction
source.

---

## Accuracy

Measured over the 10 cards in `dataset`, 9 of which have hand-checked ground truth in
`tests/fixtures/valid_extraction.json`. Scored by `scripts/evaluate_fields.py`, which compares
every key and penalises both misses and unsupported extras.

```bash
python app.py --input ./dataset --output ./outputs
python scripts/evaluate_fields.py ./outputs/batch_summary.json
```

| Metric             | Value                           |
| ------------------ | ------------------------------- |
| Mean per-key score | **72.3%**                 |
| Exact-match rate   | **67.2%** (43 of 64 keys) |
| Keys missing       | 11 of 64                        |
| Unsupported extras | 2                               |

| File                | Mean  | Keys | Exact | Missing | Extras |
| ------------------- | ----- | ---- | ----- | ------- | ------ |
| card_blurry         | 0.856 | 8    | 7     | 1       | 0      |
| card_extreme_noise  | 0.720 | 5    | 3     | 1       | 0      |
| card_hitachi        | 0.556 | 9    | 5     | 3       | 2      |
| card_lowlight       | 0.875 | 8    | 7     | 1       | 0      |
| card_on_desk        | 0.720 | 5    | 3     | 1       | 0      |
| card_on_paper       | 0.450 | 8    | 3     | 1       | 0      |
| card_partial_shadow | 0.875 | 8    | 7     | 1       | 0      |
| card_rotated        | 0.520 | 5    | 2     | 1       | 0      |
| card_zoom           | 0.875 | 8    | 7     | 1       | 0      |

Recognition is not the limiting factor. On `card_lowlight` every printed line is read at 0.99 to
1.00 confidence and `raw_text` carries the complete postal address including the building and
ZIP+4.

---

## Error analysis

The remaining loss is concentrated in three capture conditions.

**`card_on_paper` (0.450).** The card is low-contrast against the sheet and body text from the
page competes with the card's own text, so a line from the surrounding document can win the
`name` slot. This is a segmentation problem.

**`card_rotated` (0.520).** Characters are misread (`Engineeting` for `Engineering`) and a middle
address line is absent from the reading. No parsing recovers text the recogniser did not produce.

**`department` and `division` are the most-missed keys**, in four and two files respectively.
Both are usually printed without a label, so they are recovered through morphology only and land
in the residual group with an inferred name rather than in a typed field.

Detection recall is 11 of 11, and the generated no-document frame is reported as a failure
rather than an empty success.

---

## Testing instructions

```bash
python -m pytest tests/ -q
python scripts/check_dataset_leakage.py
cd frontend && npm run lint && npm run typecheck && npm run test:e2e
```

| Suite                            | Coverage                                         |
| -------------------------------- | ------------------------------------------------ |
| `tests/test_field_parser.py`   | Schema shape, confidence derivation, merge rules |
| `tests/test_generalization.py` | Held-out vocabulary the parser has not seen      |
| `tests/test_no_hardcoding.py`  | Anti-hardcoding guard, derived confidence        |
| `tests/test_scenarios.py`      | The real photographs and the failure case        |

The scenario suite runs the real pipeline over the dataset and asserts detection, document
type, expected tokens, and artefacts per file. It takes roughly eight minutes because difficult
captures escalate through several crops and four OCR variants each.

### Anti-hardcoding guard

`scripts/check_dataset_leakage.py` scans the extraction source for the dataset's proper nouns,
e-mail addresses, and long digit runs, and fails if any appear. Vocabulary is permitted only
where it is general document convention. It runs in CI and as a Docker build gate.

The guard is a backstop, not a proof. It cannot detect a leak phrased as generic-looking text,
which is why the held-out vocabulary tests run alongside it.

---

## Assumptions

- **One primary document per image.** Where several are present the best-scoring candidate wins
  and the response states which one and why.
- **Printed labels are the primary signal.** A card with no labels relies on morphology alone and
  yields less. The brief's own examples are label-driven.
- **Latin script, left to right.** Configured for English; Indonesian is handled incidentally.
- **Cards are wider than tall**, used as a detection prior rather than a hard constraint.
- **Uploads are trusted after validation.** Size and content type are checked; there is no
  authentication tier.

---

## Tradeoffs

| Decision                                | Accepted cost                                               |
| --------------------------------------- | ----------------------------------------------------------- |
| Four OCR variants per image             | Roughly four times the recognition cost of a single pass    |
| Retain every variant's candidates       | Larger memory footprint per job                             |
| Coverage-based crop scoring             | Can prefer a noisier crop with more text over a cleaner one |
| Residual blocks instead of silent drops | The response carries text that is not a typed field         |
| Native module as a subprocess           | Process startup per call, no in-process binding             |
| Rule-based parsing                      | Cannot recover text the recogniser did not produce          |
| CPU-only inference                      | No GPU path; latency scales with crop count                 |
| Single-process job runner               | Not safe for multiple instances                             |

---

## Known limitations

1. **Low-contrast subjects pull in background text.** On `card_on_paper` a line from the
   surrounding sheet can win the `name` slot.
2. **Rotated captures lose characters to recognition itself.** On `card_rotated` text is misread
   and a middle address line is dropped.
3. **Unlabelled lines are inferred, not certain.** `department` and `division` are recovered by
   morphology and are marked as inferred wherever they appear.
4. **No table extraction.** Receipt line items and totals are parsed as fields, not as a table
   structure.
5. **Single-page documents.** Multi-page PDFs are not supported.
6. **No authentication or rate limiting.** The public demo accepts anonymous uploads and has no
   quota, so it is an evaluation deployment and not something to point real traffic at. The
   upload size is capped and the response body is validated, but there is no per-client limit.
7. **Job history is in-memory and per instance.** Records live in the FastAPI process on
   `/app/data`, so a redeploy clears them and history does not merge across instances. Mount a
   volume at `/app/data` to keep it.
8. **Batch CLI is not failure-isolated.** One unreadable file aborts the run. The API isolates
   failures per job.
9. **CPU-bound, so concurrent uploads queue.** The engine reads four variants per image on CPU.
   Parallel uploads are handled one after another, and a burst of traffic will exhaust the
   instance's CPU credit on a free tier.

---

## Performance notes

Indicative figures on the development host, CPU only:

| Stage                     | Cost                          |
| ------------------------- | ----------------------------- |
| Detection and perspective | under 100 ms                  |
| Enhancement, Python       | tens of ms                    |
| Enhancement, native       | a few ms plus process startup |
| OCR, four variants        | roughly 15 s per image        |
| Total per image           | dominated by recognition      |

Mean line confidence is around 99.6% on the legible cards and lower on the shadowed and
low-contrast captures. Latency will differ on other hardware.

In order of expected value, the remaining optimisations are: skip OCR variants that a first pass
shows to be redundant, batch the four variants into a single ONNX session, and cache recognition
results for unchanged crops.

---

## Deployment

### Railway

The repository includes a `railway.json`, so Railway needs no extra configuration: it detects
the `Dockerfile`, builds the image, and serves the app. The app reads its listen port from the
`PORT` environment variable that Railway assigns at runtime, so it works on any assigned port
rather than a hard-coded one.

1. Go to [railway.app](https://railway.app) and sign in with GitHub.
2. Click **New Project → Deploy from GitHub repo**, and select this repository.
3. Railway detects the Dockerfile and starts the build. No other fields need filling in.
4. When the build finishes, open **Settings → Networking → Generate Domain** to get a public
   URL. The app is then reachable at that URL, and the UI is served from the same origin.

Railway calls `/api/health` as its health check. That endpoint reports the live OCR engine, not
just process liveness, so a deployment that cannot load its model is marked unhealthy instead of
being handed traffic.

**Recognising an image takes roughly 45 seconds per card on a free-tier CPU**, so first
processing after a cold start is slow. The service itself is responsive immediately; it is the
OCR step that takes time.

**Volume**: the pipeline writes per-job artefacts to `/app/outputs` and keeps job records in
`/app/data`. On Railway these are on the container filesystem and are lost on redeploy. Add a
Railway volume mounted at `/app/data` if you want history to survive. Image processing itself
does not need persistence.

**Limitations on a free tier**: this workload is CPU-bound and runs four OCR variants per image.
A trial or hobby instance handles low traffic fine, but concurrent uploads will queue behind
each other, and heavy use will run into the plan's resource limits.

### Other platforms

Because the container reads `PORT` and binds to `0.0.0.0`, it also deploys unchanged to Fly.io,
Google Cloud Run, and AWS App Runner. For those, point the platform at the `Dockerfile` and set
the health check path to `/api/health`.

---

## Repository layout

```
api.py                     FastAPI routes, job lifecycle, health contract
app.py                     batch CLI
src/
  detector.py              document detection
  perspective.py           homography and rotation
  enhancer.py              enhancement, Python and native paths
  ocr_engine.py            RapidOCR wrapper, variants, angle classifier
  layout.py                columns, typography tiers, line model
  field_parser.py          field parsing, voting, confidence, residual grouping
  classifier.py            document-type classification
  pipeline.py              orchestration, crop selection, response contract
  jobs.py                  async job lifecycle
  cpp_module/enhancer.cpp  native enhancement
scripts/
  evaluate_fields.py       ground-truth scorer
  check_dataset_leakage.py anti-hardcoding guard
tests/                     pytest suite and fixtures
frontend/                  Next.js UI
dataset/                   benchmark photographs and the failure case
vendor/                    pinned dependency PyPI no longer serves
```
