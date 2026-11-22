# Setup API Keys — Real Mode (5 menit)

Real mode memakai dua API murah (total ~$0.04 per jam video):
- **Groq** → transkripsi (Whisper large-v3-turbo), ada free tier
- **DeepSeek** → pemilihan klip (deepseek-flash), bayar per token (receh)

## 1. Ambil key

| Provider | Langkah | Bentuk key |
|---|---|---|
| **Groq** | buka https://console.groq.com → login Google → **API Keys** → *Create API Key* | `gsk_...` |
| **DeepSeek** | buka https://platform.deepseek.com → daftar/login → **API keys** → *Create new secret key* (perlu isi saldo minimal ~$2 via menu Top up) | `sk-...` |

Kedua key **hanya ditampilkan sekali** saat dibuat — langsung salin.

## 2. Simpan ke `.env`

```bash
cd ~/ai-clipper
cp .env.example .env
# edit .env, isi GROQ_API_KEY dan DEEPSEEK_API_KEY
```

`.env` sudah masuk pola ignore standar — **jangan pernah commit atau share isinya**.

## 3. Jalankan server lewat launcher

```
start.bat          (double-click di Explorer, atau jalankan dari terminal)
```

`start.bat` membaca `.env` lalu menjalankan `server.py` di http://127.0.0.1:8765. (Jalankan `python server.py` langsung hanya kalau key sudah di-export di shell.)

## 4. Tes Real mode

1. Buka http://127.0.0.1:8765 → isi **YouTube URL** (atau path file video lokal) → mode **Real mode** → *Start clipping*.
2. Di job page, stepper akan jalan nyata: Ingest (yt-dlp mengunduh) → ASR (Groq) → Normalize → Select (DeepSeek) → Render (ffmpeg) → Package.
3. Video 10–30 menit selesai dalam beberapa menit di laptop; biaya API < $0.01 untuk itu.

Alternatif CLI langsung:
```bash
python clipper.py run "https://www.youtube.com/watch?v=..." --lang id --target-len 45 --max-clips 10
```

## Troubleshooting

| Gejala | Penyebab / solusi |
|---|---|
| `GROQ_API_KEY environment variable is not set` | server dijalankan bukan lewat `start.bat`, atau `.env` belum diisi |
| `yt-dlp not installed` | `uv tool install yt-dlp` (sudah terpasang di mesin ini per 23 Sep 2026) |
| `FileNotFoundError: Input file not found` | path file salah/URL dikirim di mode file — cek bentuk input |
| Job `failed` dengan error 401/403 dari Groq/DeepSeek | key salah atau saldo DeepSeek habis |
| Ingin tes tanpa API key | mode **Demo (fake)** di UI, atau `python clipper.py run --fake <nama>` |

Biaya nyata per jam video sumber: **≈ $0.04** (ASR $0.036 + LLM $0.004) — 30 video 1 jam/bulan ≈ $1.20.
