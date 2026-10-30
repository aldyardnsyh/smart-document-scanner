# DESIGN_SYSTEM.md — Demo Mode UI Addendum (app existing)

## 1. Badge topbar
- Class `.api-status--demo`; teks "Demo mode"; `aria-label="Demo mode: sample results"`.
- Warna: teks/ikon `--warning`, latar `--surface-alt` (asumsi token; FE memetakan ke nilai nyata).
- Radius, padding, dan font memakai token existing; tanpa nilai ad-hoc.

## 2. Banner hasil
- `.demo-banner`, `role="note"`, judul "Sample result".
- Copy: "These artifacts come from a stored sample run, not from the file you selected."
- Link "How the demo works" → `/docs#demo` (target 44px vertikal).

## 3. Catatan scanner
- "Your file stays in the browser. Results come from a stored sample run."

## 4. Catatan history
- "Sample records are loaded on first visit, so search, filters, and delete can be tried immediately."

## 5. Empty state (semua dihapus)
- "No records. Reload the page to restore the sample set."

## 6. Judul halaman docs demo
- "How demo mode works"

## 7. Aksesibilitas
- Makna tidak bergantung warna: teks badge + copy banner menyatakan status demo.
- Kontras ≥ 4.5:1 untuk semua teks; badge non-interaktif, link ≥ 44×44px.
- Fokus ring dari token existing, terlihat di atas `--surface-alt`.
- `prefers-reduced-motion` → tanpa transisi/motion pada badge dan banner.

## 8. Responsif
- 375px: badge tetap terlihat; banner stack (judul, copy, link turun baris).
- 768px & 1280px: banner satu baris, jarak antar-elemen pakai spacing token.

## 9. Sengaja TIDAK dilakukan
- Tanpa animasi pulse/blink pada badge, tanpa ilustrasi dekoratif.
- Tanpa modal/popup/toast tambahan — banner inline saja.
- Tanpa warna demo baru (gradient/badge ungu khas "AI") — token existing saja.
- Tanpa jargon marketing atau emoji di copy.

- Catatan: copy berbahasa Inggris mengikuti UI existing.