# Panduan Penggunaan Cookie di GitHub Codespaces / VPS

Jika Anda menjalankan bot ini di **GitHub Codespaces** atau **VPS (Server)**, bot tidak bisa mengambil cookie langsung dari browser Anda. Anda harus menyediakan file `cookies.txt` secara manual.

## Mengapa butuh Cookie?
TikTok menggunakan sistem anti-bot yang ketat. Tanpa cookie dari akun yang sudah login, TikTok akan sering melaporkan bahwa user "tidak sedang live" padahal sebenarnya sedang live.

## Cara Mendapatkan `cookies.txt`

1.  **Install Ekstensi Browser:**
    *   Chrome: [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/ccmclabnhaocemoghpkilaakpjbcikki)
    *   Firefox: [export-cookies-txt](https://addons.mozilla.org/en-US/firefox/addon/export-cookies-txt/)
2.  **Buka TikTok:**
    *   Buka [tiktok.com](https://www.tiktok.com) dan pastikan Anda sudah **Login**.
3.  **Ekspor Cookie:**
    *   Klik ikon ekstensi yang baru diinstall.
    *   Pilih opsi untuk mengekspor cookie untuk `tiktok.com`.
    *   Simpan file tersebut dengan nama `cookies.txt`.
4.  **Upload ke Codespaces:**
    *   Buka GitHub Codespaces Anda.
    *   Klik kanan di folder project bot ini.
    *   Pilih **Upload...** dan pilih file `cookies.txt` yang tadi diunduh.
    *   Pastikan file tersebut berada di folder yang sama dengan `bot.py`.

## Catatan Penting
*   **Keamanan:** Jangan bagikan file `cookies.txt` Anda kepada siapapun. File ini berisi data login Anda.
*   **Kadaluwarsa:** Jika bot mulai gagal lagi, kemungkinan cookie Anda sudah kadaluwarsa. Silakan ulangi langkah di atas untuk memperbarui `cookies.txt`.
*   **Otomatisasi:** Bot akan secara otomatis mendeteksi jika ada file `cookies.txt` di foldernya dan menggunakannya sebagai prioritas utama.
