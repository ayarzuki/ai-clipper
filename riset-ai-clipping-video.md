# Riset: AI Clipping Video untuk Shorts — Durasi Platform & Harga Model (Sep 2026)

> Riset 22 Sep 2026. Harga diverifikasi dari halaman vendor / agregator pihak ketiga (tanggal verifikasi per sumber). Selalu cek ulang halaman pricing vendor sebelum commit.

## 1. Durasi & Spesifikasi Platform

| | Instagram Reels | TikTok | YouTube Shorts |
|---|---|---|---|
| **Max durasi** | **3 min** (in-app & upload umum); hingga **20 min** via Reels camera/upload (fitur baru, belum semua akun) | **10 min** universal; **30–60 min** rolling out per region (upload) | **3 min** (klip vertikal/persegi ≤3 min otomatis = Shorts) |
| **Min durasi** | 3 detik | — | 5 detik (total aset) |
| **Catatan algoritma** | Reels >3 min **tidak direkomendasikan ke audiens baru** (official IG Help); sweet spot reach 7–15 detik | Feed favor <3 min | Short >1 min dengan Content ID claim = diblokir; musik Shorts Audio Library max ~90 detik |
| **Resolusi** | 1080×1920 (max 1080p) | 1080×1920 | 1080×1920 (max 1080p) |
| **Aspect ratio** | 9:16 | 9:16 (1:1 & 16:9 di-letterbox) | 9:16 atau 1:1 |
| **Frame rate** | 23–60 fps (30 recommended) | 23–60 fps (30 std, 60 high-motion) | 24–60 fps |
| **Max file size** | 4 GB | 287.6 MB mobile; **4 GB via web/TikTok Studio** | standar YT |
| **Codec / audio** | H.264 MP4 (MOV ok) / AAC stereo 128–256 kbps | H.264 MP4 (HEVC/VP9/MOV ok) / AAC 128 kbps | H.264 MP4 / AAC |
| **Caption** | 2.200 char | 4.000 char (composer) / 2.200 (API) | standar YT |

**Kesimpulan praktis untuk pipeline clipping:**
- **Target produksi satu universal: 9:16, 1080×1920, 30 fps, ≤ 60 detik, hard-ceiling 3 min.** Satu export lolos ke ketiga platform.
- Durasi klip ideal per riset masing-masing: reach IG 7–15 dtk, tutorial 15–60 dtk; TikTok & Shorts <3 min.
- Safe zone TikTok: jangan taruh teks di bottom ~484 px & right ~86 px (UI overlay). Captions on-screen wajib (mayoritas view muted).

Sumber: [IG Help — Record a reel](https://help.instagram.com/270963803047681) (20 min, "over 3 minutes won't be recommended"), [YouTube — Understand three-minute Shorts](https://support.google.com/youtube/answer/15424877), [YouTube — Create Shorts](https://support.google.com/youtube/answer/10343433), [video.yt platform specs](https://video.yt/specs/tiktok-specs) (TikTok 10 min universal / 30–60 min per region, 4 GB via web; verified 2026-05-15).

## 2. Harga "Model" untuk Clipping — dari Termurah ke Termahal

Tiga lapis biaya: **(a) ASR/transkrip**, **(b) LLM penentu highlight**, **(c) render/edit** (ffmpeg = gratis). Generative video model hanya opsional untuk B-roll, bukan inti clipping.

### Tier 0 — DIY (termurah, ~$0.04 per jam sumber)
Pipeline open-source: `yt-dlp/ffmpeg` → `faster-whisper` / Groq Whisper → LLM cari momen viral → `ffmpeg` cut 9:16 + burn caption (Whisper word timestamps) → hasil Shorts.

| Komponen | Pilihan | Harga |
|---|---|---|
| ASR termurah hosted | Groq Whisper-Large-V3-Turbo | **~$0.0006/min ≈ $0.036/jam audio** |
| ASR alternatif | deAPI Whisper large-v3 $0.021/jam; Together/Fireworks $0.001/min ($0.06/jam) | |
| ASR self-host | faster-whisper di GPU sendiri | ~$0.05–0.15/jam (biaya GPU) |
| ASR kaya fitur (diarization) | AssemblyAI Universal-2 $0.0025/min ($0.15/jam, diarization included); Deepgram Nova-3 batch $0.0036/min; OpenAI gpt-4o-mini-transcribe $0.003/min; OpenAI Whisper API $0.006/min ($0.36/jam) | |
| LLM highlight picker | DeepSeek V4.1 Flash $0.15–0.30 in / $0.60–1.20 out per 1M tok (off-peak/peak) | **~$0.003 per jam sumber** |
| LLM alternatif murah | GPT-5.6 Luna $0.20/$1.20; Gemini 3.1 Flash-Lite $0.25/$1.50; Gemini 2.5 Flash-Lite $0.10/$0.40 | $0.004–0.005/jam |
| LLM mid | Gemini 3.8 Flash promo $0.75/$3.75; Claude Haiku 4.5 $1/$5; Claude Sonnet 5 $2/$10; GPT-5.6 Terra $2/$12 | $0.02–0.04/jam |
| LLM flagship | GPT-5.6 Sol $4/$20; Claude Opus 5 $5/$25; GPT-6 Astra / Claude Fable 5.1 $10/$50 | $0.08–0.20/jam |
| Render | ffmpeg (crop 9:16, burn subtitle) | $0 (lokal) / bebas di laptop |

**Total DIY stack termurah (Groq ASR + DeepSeek V4.1 Flash): ≈ $0.039 per jam sumber → 30 video 1-jam/bulan ≈ $1.16/bulan.**
Asumsi LLM: transkrip 1 jam ≈ 12k token masuk, 1,5k token keluar (memilih segmen + hook + caption).

Catatan: cache prompt (diskon 80–98%) & batch API (50%) menekan biaya LLM lagi. Self-hosted Whisper baru menang di atas ~10.000 menit/bulan; di bawah itu API lebih murah.

Sumber: [Speech-to-Text API Pricing 2026](https://convertaudiototext.com/blog/speech-to-text-api-pricing-2026), [Speech-to-Text comparison (dev.to)](https://dev.to/pietrus914/speech-to-text-api-comparison-whisper-api-options-in-2026-400h), [LLM pricing ledger](https://llm.okamomedia.tokyo/en/pricing/) (verified Sep 2026), [UsageBox LLM comparison](https://usagebox.com/articles/llm-api-cost-calculator-comparison-2026), [benchlm LLM pricing](https://benchlm.ai/llm-pricing).

### Tier 1 — SaaS clipping termurah (per jam sumber, billing bulanan)

| Tool | Plan entry | $/jam sumber | Catatan |
|---|---|---|---|
| **Opus Clip Free** | $0 (60 min/bln) | **$0** | watermark, ekspor kadaluarsa 3 hari — satu-satunya free tier layak |
| 2short.ai | Pro $19.90 / 15 jam | ~$1.33 | fitur lengkap di semua plan |
| Vizard | Creator $29 / 600 min (~$2.90/jam); **annual $174/7.200 kredit ≈ $1.45/jam** | $1.45–2.90 | free tier 60 kredit/bln 720p watermark; 4K export |
| Klap | Basic $14 (100 klip), Pro $39 (300), **Pro+ $94 (1.000 klip ≈ $0.09/klip)** | ~$1.25–1.87 | meter per klip jadi, bukan menit |
| Descript | Hobbyist $24 / 600 min | ~$2.40 | editor berbasis teks, cocok untuk rapikan klip |
| Ssemble | Pro $7.50+ | ~$2.25 | 1 kredit = 1 video (≤20 min) — murah untuk volume |
| AutoClip | Starter $19.99 / 200 kredit | ~$6.00 | kuat di auto-posting |
| **Opus Clip** | Starter $15/150 min ($6/jam); Pro $29/300 min ($5.80/jam); annual $174/3.600 kredit ($2.90/jam) | $2.90–6.00 | virality score + ClipAnything; kualitas seleksi terbaik |
| Submagic | Starter $19 + **Magic Clips add-on $19** | bervariasi | meter per upload; caption terbaik, clipping = add-on |

Sumber: [ugcmarketplace AI clipping pricing](https://ugcmarketplace.com/blog/ai-clipping-tool-pricing) (1 Sep 2026), [autoclip pricing compared](https://autoclip.dev/blog/ai-clipping-tool-pricing-compared-2026), [scalereach best clipping tools](https://scalereach.ai/blog/best-ai-video-clipping-tools) (27 Jul 2026), [quickreel pricing compared](https://quickreel.io/blog/ai-clip-tool-pricing-compared), [autoclip best tools Sep 2026](https://autoclip.dev/blog/best-ai-clipping-tools-september-2026).

### Tier 2 — Generative video model (mahal; untuk B-roll/AI hook, bukan clipping murni)

Harga per detik output video (720p video-only kecuali disebut):

| Model | $/detik | 10-dtk ekuivalen | Catatan |
|---|---|---|---|
| Veo 3.1 Lite (720p) | $0.03–0.05 | $0.30–0.50 | termurah; 4/6/8 dtk |
| Runway Gen-4 Turbo | $0.05 | $0.50 | 5 kredit/dtk |
| Wan 2.6/2.7 (via API) | ~$0.05 | $0.50 | 720p default |
| Veo 3.1 Fast / Sora 2 (720p) | $0.08–0.10 | $0.80–1.00 | ⚠️ API Sora 2 **ditutup 24 Sep 2026** |
| Kling 3.0 (720p) / Kling 3.0 Turbo + audio | $0.08–0.13 | $0.80–1.26 | 1080p $0.14–0.168/dtk |
| Runway Gen-4.5 / Seedance 2.0 | $0.12–0.14 | $1.20–1.40 | |
| Veo 3.1 (1080p + audio) | $0.20–0.40 | $2.00–4.00 | audio native |
| Sora 2 Pro | $0.30–0.70 | $3.00–7.00 | termahal; deprecated |

Aturan praktis: **3–4 take per klip final** → kalikan biaya ×3.5. Bulanan untuk 100 klip 8 dtk ≈ $140 (tier murah) sampai ~$1.400 (Sora 2 Pro).

Sumber: [CometAPI AI Video API Pricing](https://www.cometapi.com/ai-video-api-pricing) (Agu 2026), [getaicost video pricing](https://getaicost.com/ai-video-generation-pricing) (verified 2026-09-02), [wavespeed comparison](https://wavespeed.ai/blog/posts/wan-2-7-vs-seedance-2-vs-sora-2-vs-veo-3-1-fast-image-to-video-comparison), [Kling API pricing](https://kling.ai/dev/pricing).

## 3. Rekomendasi Build: AI Clipping Sendiri (hemat, jalan di laptop + CF free tier)

Arsitektur (semua open-source/gratis kecuali ASR+LLM API):

```
[video panjang / URL YouTube]
   → yt-dlp / upload file
   → ffmpeg: ekstrak audio 16kHz mono wav
   → ASR: Groq Whisper-Large-V3-Turbo (word-level timestamps)   ~$0.036/jam
   → LLM: DeepSeek V4.1 Flash (atau GPT-5.6 Luna / Gemini Flash-Lite)
        input: transkrip ber-timestamp
        output JSON: [{start, end, title, hook, caption, hashtags, virality_score}]
        aturan: target durasi 20–59 dtk (hard max 180 dtk)
   → ffmpeg: cut + crop 9:16 1080×1920 30fps (crop ke speaker bila multi-cam)
   → burn caption dari word timestamps (ASS/styled subs; jaga safe zone TikTok)
   → optional: tambah hook text 3 detik pertama, zoom punch tiap ~4 dtk
   → output: N klip .mp4 siap upload ke Reels/TikTok/Shorts
```

Biaya per jam sumber: **~$0.04** (vs $1.25–6/jam pakai SaaS). Selisih 30–150×; trade-off = harus develop sendiri, kualitas caption/reframe secanggih Opus/Vizard harus dibangun.

Opsi hybrid yang masuk akal: develop pipeline sendiri untuk volume, pakai Opus Clip free tier (60 min/bulan) sebagai benchmark kualitas & untuk video penting.

Langkah lanjut yang bisa dikerjakan: scaffold `clipper.py` (CLI: input video/URL → output folder klip + SRT + metadata), dijalankan di laptop, dashboard sederhana di Cloudflare Pages. Opsional: auto-post via TikTok Content Posting API / YT Shorts API (perlu OAuth + review; IG Graph API butuh akun bisnis).
