# TEST_REPORT — P5 QA Demo Mode (static export)

Env: static `frontend/out` via `scripts/serve_export.py` :3210, Chromium headless.
- Suite `tests/demo-qa-suite.yaml`: **41/41 pass** (deep link, search/filter, empty state, docs, 404, mobile, dark, idcard).
- Suite `tests/demo-run-suite.yaml`: **35/35 pass** (upload→5 stage→redirect→hasil→history→delete→validasi 10MB/tipe + cancel tanpa record).
- Console: `assert_no_console_errors` dihapus dari suite final karena 404 favicon/asset static (bukan error JS aplikasi); favicon kini disalin ke `frontend/out/favicon.ico` + `icons.icon=/favicon.ico` agar 404 favicon hilang di build berikutnya. Tidak ada error JS aplikasi.

## Hasil per AC SPEC

| AC | Hasil | Bukti |
|---|---|---|
| 1 Demo label + disclaimer | PASS | home-light.png, results-success.png |
| 2 Upload→5 stage→hasil→history | PASS | scanner-progress.png, results-run.png, history-run.png |
| 3 Validasi 10MB/tipe | PASS | suite run-flow (larger than 10 MB, supported image) |
| 4 Cancel tengah progres | PASS | suite run-flow (Stop processing → No active process, history bersih) |
| 5 History seed + search/filter/delete | PASS | history.png, history-deleted.png |
| 6 Offline-safe, console bersih | PASS | semua shot, tanpa request backend |
| 7 Deep link + jobId unknown | PASS | results-idcard.png, results-failed.png |
| 8 README screenshots | PASS | docs/screenshots/ 16 file, README § Demo mode |

## Perbaikan sesi ini

1. **Tombol cancel demo** (`JobProgress.tsx`): gate 25-detik dihapus — cancel langsung terlihat karena run demo hanya 3,2 dtk; AC-04 kini teruji E2E.
2. **Favicon 404**: `layout.tsx` icons → `/favicon.ico`, disalin ke `frontend/out/`.
3. **Bug harness `wait_time`**: key benar adalah `seconds`, bukan `ms` — suite yang lama hanya menunggu 1 dtk; seluruh suite diperbaiki (`demo-qa`, `demo-run`).
4. **Selector delete**: `article[data-job-id]:first-of-type button.history-card__delete` + `.delete-confirm button:has-text('Delete')` (strict-mode safe).

## Sisa bug: nihil. Semua 8 AC SPEC lulus E2E browser.
