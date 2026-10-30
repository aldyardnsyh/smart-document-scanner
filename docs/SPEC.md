# SPEC — Demo Mode Vercel

Status: v1.0 · Owner: analyst · Sumber: `docs/BRIEF.md` (read-only)
Istilah baku: **demo mode** (hasil precomputed), **run demo** (satu eksekusi simulasi), **history** (daftar run demo).

## 1. Tujuan demo

Website Smart Document Scanner tetap dapat diakses publik di Vercel dan **memperlihatkan seluruh fitur serta data seolah berjalan** — dengan hasil precomputed yang jujur dilabeli demo, bukan OCR live.

### Batasan utama (konsekuensi, bukan solusi teknis)
1. **Tanpa compute engine** — tidak ada Python/OpenCV/ONNX/C++ runtime di Vercel; tidak ada pemrosesan gambar nyata saat runtime.
2. **Tanpa storage persisten** — tidak ada filesystem/DB tulis permanen; data bertahan hanya di sisi klien.
3. **Aset hasil terbatas** — variasi hasil hanya dari aset nyata yang sudah ada di repo (`outputs/smoke/`, `dataset/`), bukan hasil analisis file yang diunggah pengguna.

## 2. User story

### US-01 — Indikator demo yang jujur (Must)
Sebagai pengunjung, saya ingin tahu bahwa ini demo dengan hasil precomputed, agar saya tidak salah mengira sedang memakai OCR live.
- **AC-01.1** Given saya membuka halaman mana pun, When halaman selesai dimuat, Then label **"Demo mode"** terlihat tanpa scroll, dan tooltip/teks pendukung menyatakan hasil adalah sample run tersimpan.
- **AC-01.2** Given saya menyelesaikan satu run demo, When halaman hasil tampil, Then banner menyatakan "hasil contoh tersimpan, bukan pemrosesan file Anda" dan tidak ada klaim akurasi live.
- **AC-01.3** Given saya membaca README, When mencari kata "demo", Then ada bagian yang menjelaskan mekanisme demo dan batasannya dalam ≤1 paragraf.

### US-02 — Alur upload → progres → hasil → history (Must)
Sebagai pengunjung, saya ingin mencoba alur lengkap seperti produk asli, agar saya memahami cara kerja aplikasi.
- **AC-02.1** Given saya di `/scanner` dengan file gambar valid ≤10MB, When saya memilih file dan menekan proses, Then tampil 5 stage progres berurutan dan berakhir pada halaman hasil.
- **AC-02.2** Given file >10MB atau tipe tidak didukung, When saya memilihnya, Then muncul pesan validasi dan run tidak dimulai.
- **AC-02.3** Given progres sedang berjalan, When saya menekan cancel, Then progres berhenti, status = dibatalkan, dan tidak ada record baru di history.
- **AC-02.4** Given run selesai, When saya kembali ke `/history`, Then record run tersebut ada di urutan teratas.
- **AC-02.5** Given saya memilih tipe dokumen (auto/business_card/id_card/receipt/paper_document), When run selesai, Then jenis hasil dan field yang tampil konsisten dengan tipe yang dipilih; minimal 4 tipe menghasilkan konten berbeda.

### US-03 — History ter-seed dan dapat dikelola (Must)
Sebagai pengunjung, saya ingin history sudah berisi data, agar fitur pencarian/filter/hapus bisa langsung dicoba.
- **AC-03.1** Given saya pertama kali membuka `/history` (storage kosong), When halaman dimuat, Then tampil **≥6 record seed**, termasuk **≥1 record berstatus gagal**.
- **AC-03.2** Given history tampil, When saya mengetik kata kunci atau memilih filter tipe/status, Then daftar terfilter dan jumlah hasil berubah sesuai; filter tanpa hasil menampilkan empty state.
- **AC-03.3** Given saya menghapus satu record dan mengonfirmasi dialog, When halaman di-reload, Then record tetap hilang.
- **AC-03.4** Given saya menghapus lalu membatalkan dialog, When daftar diperiksa, Then record masih ada.

### US-04 — Demo offline-safe (Must)
Sebagai pengunjung, saya ingin demo tetap berfungsi tanpa backend, agar tidak ada halaman error meski API tidak tersedia.
- **AC-04.1** Given jaringan diblokir untuk request backend, When saya menjalankan alur US-02 dan US-03, Then seluruh alur selesai tanpa error yang terlihat pengguna.
- **AC-04.2** Given DevTools Network terbuka, When saya memakai semua halaman, Then tidak ada request ke host backend Python/Railway dan tidak ada error console.
- **AC-04.3** Given status health tidak dapat dijangkau, When halaman dimuat, Then status menampilkan kondisi demo (bukan spinner tanpa akhir atau crash).

### US-05 — Deep link & dokumentasi screenshot (Must)
Sebagai pengunjung dan reviewer, saya ingin setiap halaman dapat dibuka langsung dan terdokumentasi, agar hasilnya bisa dinilai tanpa klik manual.
- **AC-05.1** Given saya membuka `/`, `/scanner`, `/history`, `/results?jobId=<seed-id>` secara langsung, When halaman dimuat, Then tidak ada 404 dan konten sesuai halaman.
- **AC-05.2** Given `jobId` tidak dikenal, When `/results` dibuka, Then tampil state "tidak ditemukan" dengan tautan kembali, bukan layar kosong/crash.
- **AC-05.3** Given README dibuka, When saya scroll, Then ada screenshot untuk landing, scanner, progres, hasil (tab artifact + field), history, tema terang & gelap, tampilan mobile, dan 404.
- **AC-05.4** Given viewport 375px, When saya membuka tiap halaman, Then tidak ada scroll horizontal dan navigasi mobile dapat dipakai.

## 3. MoSCoW

| Prioritas | Item |
|---|---|
| **Must** | US-01 label demo jujur · US-02 alur end-to-end deterministik + validasi 10MB · US-03 history ≥6 seed (termasuk 1 gagal) + search/filter/delete persisten · US-04 offline-safe tanpa backend · US-05 deep link + README screenshot |
| **Should** | 4 tab artifact (original/detection/corrected/enhanced) · field + confidence + coverage + raw JSON · tema light/dark persisten · 5 tipe dokumen dengan hasil berbeda · skeleton/empty/error state |
| **Could** | Toggle denoise & C++ accelerator sebagai state visual · API docs page · animasi transisi progres · tombol download artifact |
| **Won't** | OCR live di Vercel · upload tersimpan permanen · multi-user/auth · analitik penggunaan · penggantian pipeline Railway/Docker (tetap dipertahankan) |

## 4. Asumsi
- **ASSUMPTION-001**: seed history dan hasil run disimpan di sisi klien (localStorage), cukup untuk demo single-user.
- **ASSUMPTION-002**: hasil run demo memetakan file upload ke aset precomputed terdekat; tidak ada klaim kecocokan isi file.
- **ASSUMPTION-003**: "nol error console" diukur pada build produksi, bukan dev server.

## 5. Checklist selesai untuk QA (8 poin)

1. [ ] Label "Demo mode" terlihat di semua halaman + disclaimer hasil precomputed di halaman hasil.
2. [ ] Upload valid → 5 stage progres → hasil → record muncul di history (deterministik, 3x pengulangan sama).
3. [ ] File >10MB dan tipe tidak didukung ditolak dengan pesan jelas.
4. [ ] Cancel di tengah progres menghentikan run tanpa menyisakan record.
5. [ ] History awal ≥6 record termasuk ≥1 gagal; search, filter tipe/status, delete + konfirmasi berfungsi dan bertahan setelah reload.
6. [ ] Semua halaman berfungsi dengan backend diblokir; DevTools console bersih (0 error) dan tanpa request backend.
7. [ ] Deep link `/`, `/scanner`, `/history`, `/results?jobId=…` tidak 404; jobId tak dikenal menampilkan state "tidak ditemukan".
8. [ ] README memuat screenshot landing, scanner, progres, hasil, history, light+dark, mobile, dan 404.