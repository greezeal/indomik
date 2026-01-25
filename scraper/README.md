# Universal Comic Scraper

Scraper Python untuk mengambil data komik dari website sumber.

## Instalasi

```bash
cd scraper
pip install -r requirements.txt
```

## Penggunaan

### Scrape Satu Komik

```bash
# Scrape satu komik berdasarkan slug
python main_scraper.py --comic one-piece

# Atau menggunakan URL lengkap
python main_scraper.py --comic https://[REDACTED]/komik/one-piece/

# Dengan chapter dan gambar
python main_scraper.py --comic one-piece --chapters --images
```

### Scrape Semua Komik

```bash
# Scrape semua halaman (272 halaman, ~8000+ komik)
python main_scraper.py

# Scrape halaman tertentu saja
python main_scraper.py --start-page 1 --end-page 5

# Dengan chapter detail
python main_scraper.py --start-page 1 --end-page 2 --chapters

# Dengan gambar chapter (HATI-HATI: akan memakan banyak waktu dan bandwidth)
python main_scraper.py --start-page 1 --end-page 1 --chapters --images
```

### Integrity Checker (Pengecekan Gambar Rusak/Terpotong)

Gunakan script ini untuk mengecek apakah chapter yang sudah di-scrape memiliki jumlah gambar yang sama dengan website live (berguna jika ada update perbaikan gambar di website sumber).

```bash
# Pindah ke folder scraper
cd scraper

# Cek satu komik spesifik
python integrity_checker.py --comic slug-komik

# Cek semua komik yang ada di data
python integrity_checker.py --all
```

### Opsi Lengkap

| Opsi           | Deskripsi                        | Default |
| -------------- | -------------------------------- | ------- |
| `--data-dir`   | Direktori untuk menyimpan data   | `data`  |
| `--delay`      | Jeda antar request (detik)       | `1.0`   |
| `--start-page` | Halaman awal                     | `1`     |
| `--end-page`   | Halaman akhir                    | Semua   |
| `--chapters`   | Scrape detail chapter            | False   |
| `--images`     | Scrape URL gambar chapter        | False   |
| `--comic`      | Scrape komik spesifik (slug/URL) | -       |

## Struktur Output

Data disimpan di folder `data/` pada root project (bukan di dalam folder `scraper/`):

```
KomikAniZinn/
├── scraper/
│   ├── main_scraper.py
│   ├── requirements.txt
│   └── README.md
├── data/                         # Data tersimpan di root project
│   ├── index.json                # Daftar semua komik
│   └── comics/
│       └── {comic-slug}/
│           ├── metadata.json     # Info komik lengkap
│           └── chapters/
│               ├── chapter-1.json
│               └── ...
└── planning.txt
```

### Contoh metadata.json

```json
{
  "slug": "one-piece",
  "title": "One Piece",
  "alternative_titles": "ワンピース",
  "status": "Berjalan",
  "author": "Oda Eiichiro",
  "type": "Manga",
  "genres": ["Action", "Adventure", "Comedy"],
  "synopsis": "...",
  "rating": 9.5,
  "chapters": [...],
  "total_chapters": 1120
}
```

### Contoh chapter-1.json

```json
{
  "chapter": "1",
  "title": "Komik One Piece Chapter 1",
  "url": "https://[REDACTED]/one-piece-chapter-1/",
  "date": "5 tahun yang lalu",
  "images": [
    "https://imageserver.../page-01.jpg",
    "https://imageserver.../page-02.jpg"
  ],
  "total_images": 52
}
```

## Fitur Keamanan (Privacy)

URL yang menuju ke domain sumber akan otomatis di-encode menggunakan **Base64** sebelum disimpan ke file JSON. Ini dilakukan untuk mencegah deteksi domain jika data ini di-upload ke repository public seperti GitHub.

- Contoh URL ter-encode: `"url": "b64:aHR0cHM...=="`
- Script memiliki fungsi `decode_url()` jika Anda ingin mengembalikan formatnya di script lain.

## Tips

1. **Rate Limiting**: Gunakan `--delay 2` atau lebih tinggi untuk menghindari IP di-block.
2. **Incremental Scraping**: Jalankan dengan `--start-page` dan `--end-page` untuk scraping bertahap.
3. **Bandwidth**: Scraping gambar akan memakan waktu sangat lama, pertimbangkan untuk hanya menyimpan URL dan download saat diperlukan.
4. **Data Location**: Secara default data akan disimpan di folder `data/` pada root project, berapapun kedalaman script ini dijalankan.
