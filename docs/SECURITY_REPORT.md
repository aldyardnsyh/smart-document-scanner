# Security Report — P5 Demo Mode (white-box, static only)

Scope: `frontend/src/lib/demo.ts`, `api.ts`, `demo-fixtures.json`, `ResultsPage.tsx`, `HistoryCard.tsx`, `app/docs/page.tsx`, `vercel.json`, `.vercelignore`. No build/test/server run.

## Findings

### SEC-001 — Realistic NIK pattern in public fixture (Fixed)
Lokasi: `frontend/src/lib/demo-fixtures.json:373-376,422`.
Perbaikan: NIK diganti ke `0000000000000000` (sintetik jelas) di field maupun raw_text; nama/tgl-lahir/alamat fiktif dipertahankan sebagai sample.
Status: Fixed · diverifikasi via grep — tidak ada lagi digit run format-valid.
Verdict: demo aman dirilis; 0 temuan terbuka.

## Pass (verified, no finding)
- PII lain fiktif: `avery@northline.example` (RFC .example), phone `+1 555…` (fictional range) — PASS.
- XSS: tanpa `dangerouslySetInnerHTML`/`innerHTML`/`eval`; fixture dirender sebagai teks JSX (`ResultsPage.tsx:133`, `HistoryCard.tsx:90`); `CodeBlock.tsx:29` pakai `<code>{code}</code>` — PASS.
- localStorage: key versioned (`sds.demo.jobs.v1`), try/catch + guard bentuk (`demo.ts:23-55`), corrupt key dihapus, tanpa token/secret — PASS.
- Secret: hanya `NEXT_PUBLIC_DEMO_MODE`/`NEXT_PUBLIC_API_BASE_URL` (`api.ts:5-7`); `.vercelignore` menutupi `dataset/ outputs/ data/` — PASS.
- `target="_blank"` selalu `rel="noreferrer"` (`OverviewPage.tsx:56`, `AppShell.tsx:93`) — PASS.
- Error demo generik (`Job not found`, `Result not found`), tanpa path absolut/stack — PASS.

Verdict: demo aman dirilis; satu-satunya tindakan: sanitasi NIK fixture (SEC-001).
