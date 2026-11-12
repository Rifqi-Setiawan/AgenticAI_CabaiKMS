# Foto Indonesia (S01-S03) dan gabungan dengan 160 foto Commons

Metrik sama dengan foto Commons (hitung_metrik.img_metrics): status KNOWN/OTHER/UNCERTAIN, Top-1 pada foto KNOWN, presisi AUTO_LINK. Foto Indonesia: 10 foto unik yang sama di tiga run (spreadsheet berbeda), jadi 30 keputusan tidak independen.

| Himpunan | Keputusan | Status benar | Macro-F1 | Top-1 KNOWN | AUTO_LINK benar |
|---|---|---|---|---|---|
| Indonesia S01 | 10 | 7/10 | 0.619 | 0.833 | 5/7 = 0.714 |
| Indonesia S02 | 10 | 8/10 | 0.863 | 0.833 | 5/6 = 0.833 |
| Indonesia S03 | 10 | 6/10 | 0.405 | 0.833 | 4/7 = 0.571 |
| Indonesia, 3 run | 30 | 21/30 | 0.649 | 0.833 | 14/20 = 0.700 |
| Commons 160 (UI 1 Nov, terkoreksi D18) | 160 | 108/160 | 0.640 | 0.727 | 64/87 = 0.736 |
| Gabungan Commons + Indonesia | 190 | 129/190 | 0.634 | 0.744 | 78/107 = 0.729 |

## Per foto (Indonesia)

| Run | Foto | Gold | Sistem | Confidence | Tindakan | Benar |
|---|---|---|---|---|---|---|
| S01 | C. annuum - bentuk buah_ warna bh_ posisi buah menggantung.j | UNCERTAIN  | KNOWN Cabai tanjung | 0.85 | AUTO_LINK | tidak |
| S01 | cabai domba.jpg | OTHER  | OTHER  | 0.95 | CANDIDATE | ya |
| S01 | cabai katokon - bentuk daun.jpg | KNOWN Katokkon | KNOWN Katokkon | 0.95 | AUTO_LINK | ya |
| S01 | cabai katokon - posisi bunga tegak_ jumlah bunga 1 per ruas_ | KNOWN Katokkon | KNOWN Katokkon | 0.95 | AUTO_LINK | ya |
| S01 | cabai katokon - posisi bunga tegak_ jumlah bunga 2 per ruas. | KNOWN Katokkon | KNOWN Katokkon | 0.93 | AUTO_LINK | ya |
| S01 | cabai katokon - warna tangkai daun.jpg | KNOWN Katokkon | KNOWN Katokkon | 0.95 | AUTO_LINK | ya |
| S01 | cabai kopay.webp | KNOWN Kopay | KNOWN Kopay | 0.92 | AUTO_LINK | ya |
| S01 | daun cabai domba.webp | OTHER  | OTHER  | 0.85 | CANDIDATE | ya |
| S01 | daun cabai gendot | KNOWN Gendot | KNOWN Katokkon | 0.88 | REVIEW | tidak |
| S01 | warna tangkai daun C. chinense dan C. annuum permukaan bawah | UNCERTAIN  | KNOWN Katokkon | 0.85 | AUTO_LINK | tidak |
| S02 | C. annuum - bentuk buah_ warna bh_ posisi buah menggantung.j | UNCERTAIN  | KNOWN Kopay | 0.95 | AUTO_LINK | tidak |
| S02 | cabai domba.jpg | OTHER  | OTHER  | 0.95 | CANDIDATE | ya |
| S02 | cabai katokon - bentuk daun.jpg | KNOWN Katokkon | KNOWN Katokkon | 0.93 | AUTO_LINK | ya |
| S02 | cabai katokon - posisi bunga tegak_ jumlah bunga 1 per ruas_ | KNOWN Katokkon | KNOWN Katokkon | 0.93 | AUTO_LINK | ya |
| S02 | cabai katokon - posisi bunga tegak_ jumlah bunga 2 per ruas. | KNOWN Katokkon | KNOWN Katokkon | 0.95 | AUTO_LINK | ya |
| S02 | cabai katokon - warna tangkai daun.jpg | KNOWN Katokkon | KNOWN Katokkon | 0.95 | AUTO_LINK | ya |
| S02 | cabai kopay.webp | KNOWN Kopay | KNOWN Kopay | 0.95 | AUTO_LINK | ya |
| S02 | daun cabai domba.webp | OTHER  | OTHER  | 0.85 | CANDIDATE | ya |
| S02 | daun cabai gendot | KNOWN Gendot | KNOWN Katokkon | 0.85 | REVIEW | tidak |
| S02 | warna tangkai daun C. chinense dan C. annuum permukaan bawah | UNCERTAIN  | UNCERTAIN  | 0.5 | REVIEW | ya |
| S03 | C. annuum - bentuk buah_ warna bh_ posisi buah menggantung.j | UNCERTAIN  | KNOWN Cabai tanjung | 0.95 | AUTO_LINK | tidak |
| S03 | cabai domba.jpg | KNOWN Domba | OTHER  | 0.88 | REVIEW | tidak |
| S03 | cabai katokon - bentuk daun.jpg | KNOWN Katokkon | KNOWN Katokkon | 0.93 | AUTO_LINK | ya |
| S03 | cabai katokon - posisi bunga tegak_ jumlah bunga 1 per ruas_ | KNOWN Katokkon | KNOWN Katokkon | 0.89 | AUTO_LINK | ya |
| S03 | cabai katokon - posisi bunga tegak_ jumlah bunga 2 per ruas. | KNOWN Katokkon | KNOWN Katokkon | 0.94 | AUTO_LINK | ya |
| S03 | cabai katokon - warna tangkai daun.jpg | KNOWN Katokkon | KNOWN Katokkon | 0.96 | AUTO_LINK | ya |
| S03 | cabai kopay.webp | OTHER  | OTHER  | 0.95 | CANDIDATE | ya |
| S03 | daun cabai domba.webp | KNOWN Domba | KNOWN Domba | 0.85 | REVIEW | ya |
| S03 | daun cabai gendot | OTHER  | KNOWN Katokkon | 0.91 | AUTO_LINK | tidak |
| S03 | warna tangkai daun C. chinense dan C. annuum permukaan bawah | UNCERTAIN  | KNOWN Katokkon | 0.9 | AUTO_LINK | tidak |
