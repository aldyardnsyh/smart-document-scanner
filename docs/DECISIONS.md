# DECISIONS

Log keputusan, asumsi, dan eskalasi. **Semua role menulis ke file ini** (append-only).

## Format

### DECISION-XXX
- **Tanggal:**
- **Oleh:** <role>
- **Fase:** P0..P7
- **Konteks:**
- **Keputusan:**
- **Alasan:**
- **Konsekuensi:**

### ASSUMPTION-XXX
- **Tanggal:**
- **Oleh:** <role>
- **Asumsi:**
- **Risiko:** low | medium | high
- **Perlu konfirmasi manusia:** yes | no

### ESCALATION-XXX
- **Tanggal:**
- **Oleh:** <role>
- **Alasan eskalasi:** (5 iterasi / NOT_FEASIBLE / ambigu berisiko / deadlock / butuh kredensial)
- **Konteks:**
- **Opsi:**
  1.
  2.
- **Rekomendasi:**
- **Dampak tiap opsi:**

---

<!-- Entries below -->

### DECISION-001
- **Tanggal:** 2026-10-29
- **Oleh:** architect
- **Fase:** P4
- **Konteks:** `vercel.json` ditempatkan di root repo, sedangkan ADR-6 menyebut `frontend/vercel.json`.
- **Keputusan:** Konfigurasi Vercel memakai `vercel.json` di ROOT repo (`installCommand`/`buildCommand` dengan prefix `frontend`, `outputDirectory: frontend/out`); Root Directory Vercel dibiarkan default (repo root) agar tidak perlu setting tambahan.
- **Alasan:** Satu file konfigurasi di root membuat deploy langsung dari repo root tanpa pengaturan Root Directory terpisah di dashboard Vercel.
- **Konsekuensi:** Satu file konfigurasi, deploy langsung dari repo root; poin path pada ADR-6 dianggap dikoreksi oleh entri ini.

### DECISION-002
- **Tanggal:** 2026-10-30
- **Oleh:** agentic (P6 fix loop)
- **Fase:** P5?P6?P7
- **Konteks:** QA run-flow gagal redirect (wait_time harness pakai key seconds bukan ms), cancel tak terjangkau (gate 25 dtk vs run 3,2 dtk), favicon 404, SEC-001 NIK format-valid.
- **Keputusan:** Cancel langsung tampil; icons?/favicon.ico; suite pakai seconds; NIK?0000000000000000; README § Demo mode + 15 screenshot.
- **Alasan:** Semua temuan terkonfirmasi E2E, bukan asumsi; fix minimal tanpa ubah kontrak API/demo.
- **Konsekwensi:** demo-qa 41/41, demo-run 35/35, 8/8 AC SPEC lulus, 0 vuln terbuka ? release gate PASS.

