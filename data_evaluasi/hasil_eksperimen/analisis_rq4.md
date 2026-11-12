# RQ4: recall kelas OTHER (foto Commons, hasil UI)

Foto dinilai: 158; gold OTHER: 40. Gold: `gambar/manifest/gold_gambar_manifest_final.csv`.

| Varian | Recall OTHER | CI 95% (bootstrap) |
|---|---|---|
| V3 | 0.675 | 0.525 sampai 0.816 |
| V1 | 0.675 | 0.525 sampai 0.816 |
| V2 | 0.000 | 0.000 sampai 0.000 |

| Perbandingan | Selisih | CI 95% | p mentah | p Holm |
|---|---|---|---|---|
| V3 vs V1 (H4) | +0.000 | +0.000 sampai +0.000 | 1.0000 | 1.0000 |
| V3 vs V2 (eksploratori) | +0.675 | +0.525 sampai +0.816 | 0.0000 | 0.0000 |

Catatan: V3 dan V1 identik pada pemetaan yang dipakai, sehingga selisih V3 vs V1 nol menurut konstruksi; H4 tidak dapat didukung dengan data ini.

OTHER yang tidak terdeteksi V3: 13 dari 40; status prediksi: KNOWN.
