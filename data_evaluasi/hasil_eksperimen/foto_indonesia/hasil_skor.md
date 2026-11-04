# Foto Indonesia (S01-S03) dan gabungan dengan 160 foto Commons

Metrik sama dengan foto Commons (hitung_metrik.img_metrics): status KNOWN/OTHER/UNCERTAIN, Top-1 pada foto KNOWN, presisi AUTO_LINK. Foto Indonesia: 12 foto unik yang sama di tiga run (spreadsheet berbeda), jadi 36 keputusan tidak independen. Gold Indonesia = isian peneliti 4 Nov 2026 (3 varietas tebakan AI atas persetujuan peneliti) dan tidak memuat UNCERTAIN, sehingga untuk foto Indonesia yang adil adalah macro-F1 atas kelas yang ada di gold (KNOWN, OTHER).

| Himpunan | Keputusan | Status benar | Macro-F1 3 kelas | Macro-F1 kelas di gold | Top-1 KNOWN | AUTO_LINK benar |
|---|---|---|---|---|---|---|
| Indonesia S01 | 12 | 8/12 | 0.519 | 0.778 | 0.750 | 5/8 = 0.625 |
| Indonesia S02 | 12 | 8/12 | 0.536 | 0.804 | 0.750 | 6/8 = 0.750 |
| Indonesia S03 | 12 | 7/12 | 0.370 | 0.556 | 0.833 | 4/8 = 0.500 |
| Indonesia, 3 run | 36 | 23/36 | 0.470 | 0.706 | 0.773 | 15/24 = 0.625 |
| Commons 160 (UI 1 Nov, terkoreksi D18) | 160 | 108/160 | 0.640 | 0.640 | 0.727 | 64/87 = 0.736 |
| Gabungan Commons + Indonesia | 196 | 131/196 | 0.632 | 0.632 | 0.736 | 79/111 = 0.712 |

## Per foto (Indonesia)

| Run | Foto | Gold | Sistem | Confidence | Tindakan | Benar |
|---|---|---|---|---|---|---|
| S01 | C. annuum - bentuk buah_ warna bh_ posisi buah menggantung.j | OTHER  | KNOWN Cabai tanjung | 0.85 | AUTO_LINK | tidak |
| S01 | cabai domba.jpg | OTHER  | OTHER  | 0.95 | CANDIDATE | ya |
| S01 | cabai katokon - bentuk daun.jpg | KNOWN Katokkon | KNOWN Katokkon | 0.95 | AUTO_LINK | ya |
| S01 | cabai katokon - posisi bunga tegak_ jumlah bunga 1 per ruas_ | KNOWN Katokkon | KNOWN Katokkon | 0.95 | AUTO_LINK | ya |
| S01 | cabai katokon - posisi bunga tegak_ jumlah bunga 2 per ruas. | KNOWN Katokkon | KNOWN Katokkon | 0.93 | AUTO_LINK | ya |
| S01 | cabai katokon - warna tangkai daun.jpg | KNOWN Katokkon | KNOWN Katokkon | 0.95 | AUTO_LINK | ya |
| S01 | cabai kopay.webp | KNOWN Kopay | KNOWN Kopay | 0.92 | AUTO_LINK | ya |
| S01 | daun cabai domba.webp | OTHER  | OTHER  | 0.85 | CANDIDATE | ya |
| S01 | daun cabai gendot | KNOWN Gendot | KNOWN Katokkon | 0.88 | REVIEW | tidak |
| S01 | daun cabai kopay.jpg | KNOWN Kopay | KNOWN Kopay | 0.83 | REVIEW | ya |
| S01 | p9vb80t0ldt5cms.webp | KNOWN Gendot | KNOWN Katokkon | 0.92 | AUTO_LINK | tidak |
| S01 | warna tangkai daun C. chinense dan C. annuum permukaan bawah | OTHER  | KNOWN Katokkon | 0.85 | AUTO_LINK | tidak |
| S02 | C. annuum - bentuk buah_ warna bh_ posisi buah menggantung.j | OTHER  | KNOWN Kopay | 0.95 | AUTO_LINK | tidak |
| S02 | cabai domba.jpg | OTHER  | OTHER  | 0.95 | CANDIDATE | ya |
| S02 | cabai katokon - bentuk daun.jpg | KNOWN Katokkon | KNOWN Katokkon | 0.93 | AUTO_LINK | ya |
| S02 | cabai katokon - posisi bunga tegak_ jumlah bunga 1 per ruas_ | KNOWN Katokkon | KNOWN Katokkon | 0.93 | AUTO_LINK | ya |
| S02 | cabai katokon - posisi bunga tegak_ jumlah bunga 2 per ruas. | KNOWN Katokkon | KNOWN Katokkon | 0.95 | AUTO_LINK | ya |
| S02 | cabai katokon - warna tangkai daun.jpg | KNOWN Katokkon | KNOWN Katokkon | 0.95 | AUTO_LINK | ya |
| S02 | cabai kopay.webp | KNOWN Kopay | KNOWN Kopay | 0.95 | AUTO_LINK | ya |
| S02 | daun cabai domba.webp | OTHER  | OTHER  | 0.85 | CANDIDATE | ya |
| S02 | daun cabai gendot | KNOWN Gendot | KNOWN Katokkon | 0.85 | REVIEW | tidak |
| S02 | daun cabai kopay.jpg | KNOWN Kopay | KNOWN Kopay | 0.87 | AUTO_LINK | ya |
| S02 | p9vb80t0ldt5cms.webp | KNOWN Gendot | KNOWN Katokkon | 0.92 | AUTO_LINK | tidak |
| S02 | warna tangkai daun C. chinense dan C. annuum permukaan bawah | OTHER  | UNCERTAIN  | 0.5 | REVIEW | tidak |
| S03 | C. annuum - bentuk buah_ warna bh_ posisi buah menggantung.j | OTHER  | KNOWN Cabai tanjung | 0.95 | AUTO_LINK | tidak |
| S03 | cabai domba.jpg | KNOWN Domba | OTHER  | 0.88 | REVIEW | tidak |
| S03 | cabai katokon - bentuk daun.jpg | KNOWN Katokkon | KNOWN Katokkon | 0.93 | AUTO_LINK | ya |
| S03 | cabai katokon - posisi bunga tegak_ jumlah bunga 1 per ruas_ | KNOWN Katokkon | KNOWN Katokkon | 0.89 | AUTO_LINK | ya |
| S03 | cabai katokon - posisi bunga tegak_ jumlah bunga 2 per ruas. | KNOWN Katokkon | KNOWN Katokkon | 0.94 | AUTO_LINK | ya |
| S03 | cabai katokon - warna tangkai daun.jpg | KNOWN Katokkon | KNOWN Katokkon | 0.96 | AUTO_LINK | ya |
| S03 | cabai kopay.webp | OTHER  | OTHER  | 0.95 | CANDIDATE | ya |
| S03 | daun cabai domba.webp | KNOWN Domba | KNOWN Domba | 0.85 | REVIEW | ya |
| S03 | daun cabai gendot | OTHER  | KNOWN Katokkon | 0.91 | AUTO_LINK | tidak |
| S03 | daun cabai kopay.jpg | OTHER  | OTHER  | 0.9 | CANDIDATE | ya |
| S03 | p9vb80t0ldt5cms.webp | OTHER  | KNOWN Katokkon | 0.95 | AUTO_LINK | tidak |
| S03 | warna tangkai daun C. chinense dan C. annuum permukaan bawah | OTHER  | KNOWN Katokkon | 0.9 | AUTO_LINK | tidak |
