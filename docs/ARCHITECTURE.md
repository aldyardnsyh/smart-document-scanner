# ARCHITECTURE — Demo Mode (Vercel static)

Status: v1.0 · Owner: architect · Refs: `docs/SPEC.md`, `frontend/src/lib/api.ts`

## 1. Konteks
- Satu codebase, dua environment: **Vercel = static-only** (tanpa Python/OpenCV/ONNX/C++), **Railway = compute asli** (pipeline tetap, tidak diubah).
- Vercel tidak menjalankan OCR. Demo menyajikan **data precomputed** dari `outputs/smoke/` dan melabelinya "Demo mode" (SPEC US-01). Label jujur = requirement, bukan kosmetik.
- Konsekuensi: file pengguna tidak pernah dibaca isinya — hanya divalidasi (tipe/ukuran) lalu dipetakan ke fixture berdasarkan `documentType`. Tidak ada klaim kecocokan isi (SPEC ASSUMPTION-002).

## 2. ADR

### ADR-1 — Static export Next.js 16
- **Konteks:** Vercel tanpa runtime Python; deep link `/`, `/scanner`, `/history`, `/results?jobId=` wajib 200.
- **Keputusan:** pertahankan `output: "export"`, `trailingSlash: false`, `images.unoptimized: true` di `frontend/next.config.ts` (sudah ada, tidak diubah).
- **Konsekuensi:** semua data fetching client-side; tidak ada route handler/SSR/`revalidate`. Alternatif "serverless function sebagai proxy" ditolak: tetap tidak punya engine, hanya menambah hop dan biaya.

### ADR-2 — Adapter API, selector demo
- **Konteks:** `frontend/src/lib/api.ts` hari ini selalu `fetch`; di produksi `API_BASE` jatuh ke `""` sehingga memanggil `/api/*` relatif → 404 HTML + error console (melanggar AC-04.2).
- **Keputusan:** `api.ts` jadi satu-satunya seam. `createProcess`/`getJob`/`getHistory`/`deleteJob`/`getHealth`/`pollJob` mendelegasikan ke `frontend/src/lib/demo.ts` bila `NEXT_PUBLIC_DEMO_MODE === "1"` **ATAU** `NEXT_PUBLIC_API_BASE_URL` kosong/tidak diset. Selector dievaluasi sekali saat modul dimuat, **tanpa** cabang `NODE_ENV`.
- **Konsekuensi:** dev lokal dan build Vercel berperilaku identik; railway mode cukup mengisi `NEXT_PUBLIC_API_BASE_URL`. Cabang `localhost:8000` berbasis `NODE_ENV` dihapus agar tidak ambigu.

### ADR-3 — Fixture `Job`/`ScanResult`
- **Konteks:** `outputs/smoke/cli-001-card_on_desk/metadata.json` adalah bentuk **`ScanResult`** (bukan `Job`); path aset absolut `/outputs/...`; 1 fixture penuh = **4.7 MB** (original 1.17 + detected 1.20 + corrected 0.97 + enhanced 1.36), jadi 5 fixture × 4 aset ≈ 23 MB → budget 8 MB jebol.
- **Keputusan:** 5 fixture (business_card, id_card, receipt, paper_document, auto) + 1 record gagal. `Job` = wrapper (id, status, stage, progress, created_at, original_name) + `ScanResult` dari metadata (buang `field_confidence` yang tidak ada di `types.ts`). Aset disalin ke `frontend/public/demo/<slug>/` dan **path ditulis ulang** ke `/demo/<slug>/...`. Budget dijaga: downscale ≤1400px q75, ≤400 KB/file, fixture non-primer hanya `original`+`corrected`; total ≤8 MB diverifikasi sebelum commit. Data pribadi diganti fiktif (nama/telepon/email).
- **Konsekuensi:** aset boleh beda dari run asli asal konsisten per tipe; tab artifact bisa kosong untuk fixture non-primer (UI sudah menangani `corrected?`/`enhanced?` opsional).

### ADR-4 — Persistensi localStorage
- **Keputusan:** key `sds.demo.jobs.v1` (record non-seed + mutasi) dan `sds.demo.deleted.v1` (id seed yang dihapus). Seed deterministik **6 record, 1 gagal**, id stabil (`seed-01`…`seed-06`) agar deep link `?jobId=` reproducible. Semua akses dibungkus `try/catch`; JSON tidak valid atau bentuk salah → reset ke seed.
- **Konsekuensi:** delete bersifat tombstone (seed tetap di bundle, difilter saat baca) sehingga reload konsisten. Quota/private-mode → fallback memori sesi, tanpa crash.

### ADR-5 — Simulasi progres
- **Keputusan:** 5 stage timer (upload → detect → correct → enhance → extract), total ±3–4 dtk, menerima `AbortSignal`; abort → `AbortError`, status dibatalkan, tidak ada record ditulis. Tanpa `fetch`, tanpa `setTimeout` yang tak dibersihkan.
- **Konsekuensi:** durasi deterministik memudahkan QA (AC-02.1); cancel benar-benar menghentikan (AC-02.3).

### ADR-6 — Routing Vercel
- **Konteks:** `vercel.json` belum ada; Root Directory harus `frontend/` karena `package.json` ada di sana.
- **Keputusan:** `frontend/vercel.json` dengan `cleanUrls: true`, `trailingSlash: false`, build `next build`, output `out`. `cleanUrls` memetakan `/scanner` → `scanner.html` (ada di `frontend/out/`) dan `/results?jobId=` resolve ke `results.html` + query dibaca client-side. Jangan commit `frontend/out` (build lama, tanpa demo).
- **Konsekuensi:** deep link aman tanpa rewrite manual; 404 memakai `404.html` hasil export.

## 3. Risiko

| Risiko | Dampak | Mitigasi | Owner |
|---|---|---|---|
| Budget aset 8 MB terlampaui (1 fixture = 4.7 MB) | Deploy lambat, LCP buruk, budget SPEC dilanggar | Downscale ≤1400px q75 ≤400 KB/file; aset parsial untuk fixture non-primer; cek total sebelum commit | frontend |
| Path `/outputs/...` tersisa di metadata | Semua tab artifact 404 di Vercel | Rewrite ke `/demo/<slug>/...` saat copy + grep gate `outputs/` di `public/demo` | frontend |
| `api.ts` fallback `API_BASE=""` memanggil `/api/*` | 404 HTML, error console, AC-04.2 gagal | Selector demo di ADR-2, dievaluasi saat load; hapus cabang `NODE_ENV` | frontend |
| localStorage korup / quota / Safari private | Halaman blank atau history kosong | `try/catch` + validasi bentuk → reset ke seed; fallback memori sesi | frontend |

## 4. Verdict

**FEASIBLE_WITH_CHANGES.** Arsitektur static export sudah benar dan tidak perlu runtime baru; semua risiko yang tersisa bersifat data/aset, bukan desain sistem. Perubahan wajib sebelum rilis: (1) buat `frontend/src/lib/demo.ts` + seam di `api.ts`, (2) buat `frontend/vercel.json`, (3) penuhi budget aset 8 MB dengan rewrite path — tanpa ketiganya demo tidak bisa dianggap selesai.

## 5. File yang disentuh

- **FE (kode):** `frontend/src/lib/demo.ts` (baru: seed, fixtures, progres, storage), `frontend/src/lib/api.ts` (seam saja), `frontend/src/screens/ScannerPage.tsx`, `HistoryPage.tsx`, `ResultsPage.tsx` (panggil API yang sama; tanpa logika demo), `frontend/src/components/JobProgress.tsx` (abort), `frontend/next.config.ts` (tidak diubah).
- **FE (aset & konfig):** `frontend/public/demo/<slug>/` (baru, ≤8 MB), `frontend/vercel.json` (baru), `frontend/public/brand/logo.png` (tetap).
- **Data:** sumber `outputs/smoke/cli-001-card_on_desk/{metadata.json, original.jpg, processed/corrected_document.jpg, processed/enhanced_document.jpg, debug/document_detected.jpg}`; 4 fixture tipe lain dari `dataset/`/`outputs/` mengikuti pola sama.
- **Dokumen:** `docs/ARCHITECTURE.md` (ini), `docs/DECISIONS.md` (catat ADR-1…6), `README.md` (screenshot + batasan demo). Badge/banner copy milik designer (`docs/DESIGN_SYSTEM.md`), bukan keputusan arsitektur.

## 6. P4 Review (implementasi nyata)

Status: v1.1 · Owner: architect · Metode: baca kode (`read`/`grep`), tanpa build/test.

### 6.1 Verifikasi klaim

| # | Klaim | Hasil | Bukti (file:line) |
|---|---|---|---|
| 1 | Static export + Vercel config ada & konsisten (outputDirectory, cleanUrls) | **PASS** | `frontend/next.config.ts:4` (`output: "export"`, `trailingSlash:false`, `images.unoptimized`); `vercel.json:2-6` (`buildCommand` → `frontend/out`, `outputDirectory: frontend/out`, `cleanUrls:true`); `.vercelignore:3-5,14-15` mengecualikan `dataset/`, `outputs/`, `bin/`, `frontend/out` |
| 2 | Seam demo di `api.ts`: selector deterministik, tanpa fallback `NODE_ENV`, `getJob` async-safe | **PASS** | `api.ts:4-5` (hanya `NEXT_PUBLIC_DEMO_MODE==="1"` atau `API_BASE` kosong; tidak ada `NODE_ENV`); `api.ts:37,48,53,60,65,74-83` delegasi per fungsi; `api.ts:48` `Promise.resolve().then(...)` sehingga throw sinkron dari `demo.getJob` tetap jadi rejection; selector deterministik di `demo.ts:97-110` |
| 3 | `demo.ts`: seed 6 record, localStorage versioned, delete tombstone, progres 5 stage + `AbortSignal`, tanpa fetch | **PASS** | `demo-fixtures.json:2` (6 record: seed-01…06, 1 gagal = seed-05); `demo.ts:6-7` key `sds.demo.jobs.v1` / `sds.demo.deleted.v1`; `demo.ts:158-169` tombstone seed + hapus user job; `demo.ts:88-95` (6 entri termasuk `queued`, 5 stage pipeline sesuai `JobProgress.tsx:5-11`); `demo.ts:205-226` abort + cleanup timer; `0` kemunculan `fetch(` |
| 4 | Path fixture `/demo/...`, tanpa `/outputs/`, total <8 MB | **PASS** | 21 path unik di `demo-fixtures.json`, semuanya `/demo/...`; grep `/outputs/` = 0; total `frontend/public/demo` = **1.10 MB**; 21/21 file ada |
| 5 | UI: badge demo (AppShell), banner sukses+gagal (ResultsPage), catatan Scanner/History, docs `id="demo"` | **PASS** | `AppShell.tsx:96-108`; `ResultsPage.tsx:69-77` (gagal) & `107-115` (sukses); `ScannerPage.tsx:245-246`; `HistoryPage.tsx:58-59,109`; `frontend/app/docs/page.tsx:81` |
| 6 | Tidak ada regresi jalur nyata (non-demo tetap `request()`) | **PASS** | `api.ts:44,49,54,61,66`; `pollJob` non-demo `api.ts:85-95`. Diff layar hanya menambah cabang `DEMO_MODE` (`git diff` 6 file, +151/−20), tidak mengubah pemanggilan selain import |
| 7 | Tidak ada file lane lain diubah di luar scope | **PASS** | `git status --short`: modifikasi hanya 6 file `frontend/` (AppShell, api.ts, 3 screens, styles.css). Sisa entri untracked = aset demo/konfig/`docs/` + artefak lokal (`.vs/`, `bin/`) |

### 6.2 Deviasi dari rencana

1. **Lokasi `vercel.json`** — ADR-6 menyebut `frontend/vercel.json`; implementasi ada di root (`vercel.json:1-7`) dengan `--prefix frontend`. Fungsional setara, tetapi config ini hanya terbaca bila Vercel Root Directory = repo root. Kalau project di-set ke `frontend/`, file ini diabaikan → `outputDirectory`/`cleanUrls` hilang. (deviasi dokumen + risiko konfigurasi)
2. **ADR-4 "fallback memori sesi" tidak ada** — `demo.ts:54-62` (`writeList`) menelan error quota/private mode tanpa cache memori, dan `finish()` (`demo.ts:128`) mengandalkan storage. Di Safari private mode / quota penuh, job user hilang setelah redirect → `getJob` melempar `Job not found` (`demo.ts:151-155`) sehingga alur upload→hasil gagal. (deviasi + risiko AC-02)
3. **Selector nama file vs fixture gagal** — `demo.ts:99-100`: `no_document` → seed-05 (gagal), tetapi `blank` → seed-06 (sukses, 0 field), padahal fixture gagal bernama `blank-desk-photo.jpg` (`demo-fixtures.json`, seed-05). Jalur gagal hanya tercapai via nama file `no_document`; seed-06 berstatus `completed` dengan 0 field meski komentar `ResultsPage.tsx:55-58` menyiratkan capture kosong harus tampil gagal.
4. **Aset lebih lengkap dari rencana** — ADR-3 menyebut fixture non-primer hanya `original`+`corrected`; implementasi menyediakan 4 artefak untuk semua fixture sukses (21 file, 1.10 MB) sehingga jauh di bawah budget 8 MB. Tidak berbahaya.
5. **`DEMO_MODE` aktif secara default** bila `NEXT_PUBLIC_API_BASE_URL` tidak diset (`api.ts:5`). Konsisten dengan ADR-2, tetapi dev lokal yang menyalakan FastAPI/Docker tanpa env var akan diam-diam masuk demo; QA harus menyalakan env var untuk menguji jalur nyata.
6. **Dead code & higiene** — `demo.ts:4` (`demoMode`) tidak dipakai; `.vs/` untracked dan tidak ada di `.gitignore` (hanya `.vscode/`), `bin/` juga untracked (tercantum di `.vercelignore`, bukan `.gitignore`).

### 6.3 Verdict

**FEASIBLE_WITH_CHANGES.** Kontrak `api.ts` ↔ `demo.ts` ↔ fixture koheren, static export dan routing `/docs#demo`, `/results?jobId=` konsisten, dan semua klaim demo terbukti di kode nyata. Perubahan wajib sebelum rilis: (1) tambahkan cache memori untuk job user di `demo.ts` saat storage tidak tersedia agar upload→hasil tidak pecah di private mode, (2) selaraskan lokasi `vercel.json` dengan Root Directory Vercel yang sebenarnya (perbaiki ADR-6 atau pindahkan file), (3) putuskan apakah capture kosong (seed-06) harus tampil gagal dan rapikan selector `blank`/`no_document`; higiene: buang `demoMode`, masukkan `.vs/` ke `.gitignore`.