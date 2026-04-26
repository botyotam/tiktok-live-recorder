# TikTok Live Recorder Telegram Bot

Bot Telegram untuk merekam siaran langsung (live) TikTok secara otomatis menggunakan `yt-dlp` dan `ffmpeg`. Dirancang untuk dijalankan di GitHub Codespaces atau server cloud lainnya.

## Fitur Utama

- **Autentikasi**: Hanya user ID yang terdaftar yang dapat mengakses bot.
- **Perekaman Tanpa Re-encode**: Menggunakan codec copy untuk menjaga kualitas asli dan menghemat CPU.
- **Manajemen File**: Unggah hasil rekaman ke Telegram dan hapus file lokal secara otomatis.
- **Status Real-time**: Cek durasi dan ukuran file rekaman yang sedang berjalan.

## Arsitektur

- **Bahasa**: Python 3.11
- **Library**: `python-telegram-bot`, `yt-dlp`
- **Tools**: `ffmpeg`
- **Cloud**: GitHub Codespaces

## Cara Penggunaan

1. **Clone Repositori**:
   ```bash
   git clone <url-repositori-anda>
   cd tiktok-live-recorder
   ```

2. **Konfigurasi**:
   Edit file `config.py` dan masukkan:
   - `TELEGRAM_BOT_TOKEN`: Token dari @BotFather.
   - `AUTHORIZED_USER_ID`: ID Telegram Anda (bisa didapat dari @userinfobot).

3. **Jalankan di Codespaces**:
   - Buka repositori di GitHub.
   - Klik tombol **Code** -> **Codespaces** -> **Create codespace on main**.
   - Tunggu setup selesai (otomatis menginstal dependensi).
   - Jalankan bot: `python bot.py`.

## Perintah Bot

- Kirim username TikTok (contoh: `@username`) atau URL live untuk mulai merekam.
- `/status`: Melihat status perekaman yang sedang berjalan.
- `/stop`: Menghentikan perekaman.
- `/save`: Mengunggah file rekaman ke Telegram dan menghapusnya dari server.

## Struktur Proyek

- `bot.py`: Handler utama bot Telegram.
- `recorder.py`: Logika perekaman menggunakan yt-dlp dan ffmpeg.
- `config.py`: Pengaturan token dan user ID.
- `requirements.txt`: Daftar dependensi Python.
- `.devcontainer/`: Konfigurasi untuk GitHub Codespaces.
