import csv, json, sys
from collections import Counter, OrderedDict
from pathlib import Path
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

sys.path.insert(0, str(Path(__file__).parent))
import annotations as A

OUT = Path(r"D:\college\Semester 6\Penulisan Proposal\project\data_evaluasi")
GOLD = OUT / "gold"
GOLD.mkdir(parents=True, exist_ok=True)
PILOT = Path(r"D:\college\Semester 6\Penulisan Proposal\project\eval\campaigns\schema-mapping-pilot-v1\master\master_evaluation.xlsx")

ANNOTATOR = ""
SOURCE = "usulan_awal_v1"
COLS = [
    "annotation_version", "annotation_source", "mapping_item_id", "mapping_identity_kind", "mapping_identity_value",
    "mapping_identity_issue", "dataset_id", "source_file_name", "source_file_sha256", "source_sheet", "source_format",
    "source_attribute_display", "source_attribute", "source_context", "contoh_nilai_sumber",
    "gold_status", "gold_canonical_keys", "ambiguous_candidate_canonical_keys", "annotator_id", "annotation_round",
    "notes", "confidence_usulan", "perlu_adjudikasi",
]
DATASET_ID = {
    "data_input.xlsx": "R01", "input_cabai_kms.xlsx": "R02",
    "D01_transposed_indonesia_mixed.xlsx": "S01", "D02_row_flat_english_semantic.xlsx": "S02",
    "D03_row_multilevel_indonesia.xlsx": "S03", "D04_varietas_kosong_invalid.xlsx": "S04",
    "E07_kementan_deskripsi_ext.xlsx": "N07", "E08_zenodo_capsicum_en.xlsx": "N08",
    "dataset_cabai_deskripsi_varietas.xlsx": "N09",
}
data = json.load(open(Path(__file__).parent / "attrs.json", encoding="utf-8"))

# canonical keys (validate every key used)
ref = openpyxl.load_workbook(PILOT, data_only=True)["Canonical Reference"]
ref_rows = [list(r) for r in ref.iter_rows(values_only=True)]
valid_keys = {r[0] for r in ref_rows[1:] if r[0]}

all_rows = []
for ds in data:
    rows = []
    for it in ds["items"]:
        status, keys, amb, note, conf = A.annotate(ds["file"], it["display"])
        for k in (keys + "|" + amb).split("|"):
            if k and k not in valid_keys:
                raise SystemExit(f"unknown canonical key {k} for {it['display']}")
        if status == "ONE_TO_ONE":
            assert keys and "|" not in keys and not amb
        if status == "COMPOSITE":
            assert keys.count("|") >= 1
        if status == "AMBIGUOUS":
            assert amb.count("|") >= 1 and not keys
        if status in ("NO_MATCH", "EXCLUDE"):
            assert not keys and not amb
        rows.append(OrderedDict(
            annotation_version="schema-mapping-gold-v1", annotation_source=SOURCE,
            mapping_item_id=it["item_id"], mapping_identity_kind=it["id_kind"], mapping_identity_value=it["id_value"],
            mapping_identity_issue=it["id_issue"] or "", dataset_id=DATASET_ID[ds["file"]],
            source_file_name=ds["file"], source_file_sha256=ds["sha"], source_sheet=ds["sheet"],
            source_format=ds["format"], source_attribute_display=it["display"], source_attribute=it["name"],
            source_context=it["context"] or "", contoh_nilai_sumber=" || ".join(it["samples"]),
            gold_status=status, gold_canonical_keys=keys, ambiguous_candidate_canonical_keys=amb,
            annotator_id=ANNOTATOR, annotation_round=1, notes=note, confidence_usulan=conf,
            perlu_adjudikasi="Y" if conf != "H" else "N",
        ))
    ids = [r["mapping_item_id"] for r in rows]
    assert len(ids) == len(set(ids)), "duplicate item ids in " + ds["file"]
    all_rows.append((ds, rows))

FILL_HDR = PatternFill("solid", fgColor="1F4E78")
FILL_HUM = PatternFill("solid", fgColor="FFF2CC")
FILL_Y = PatternFill("solid", fgColor="FCE4D6")


def write_sheet(ws, rows):
    ws.append(COLS)
    for r in rows:
        ws.append([r[c] for c in COLS])
    for i, c in enumerate(COLS, 1):
        cell = ws.cell(row=1, column=i)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = FILL_HDR
        width = 14
        if c in ("source_attribute_display", "notes", "contoh_nilai_sumber", "mapping_identity_value"):
            width = 46
        if c in ("gold_canonical_keys", "ambiguous_candidate_canonical_keys", "source_file_name"):
            width = 30
        if c == "mapping_item_id":
            width = 18
        ws.column_dimensions[get_column_letter(i)].width = width
        if c in ("gold_status", "gold_canonical_keys", "ambiguous_candidate_canonical_keys", "annotator_id", "annotation_round", "notes"):
            for rr in range(2, ws.max_row + 1):
                ws.cell(row=rr, column=i).fill = FILL_HUM
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    flag_col = COLS.index("perlu_adjudikasi") + 1
    for rr in range(2, ws.max_row + 1):
        if ws.cell(row=rr, column=flag_col).value == "Y":
            ws.cell(row=rr, column=flag_col).fill = FILL_Y


def add_reference(wb):
    ws = wb.create_sheet("Canonical Reference")
    for r in ref_rows:
        ws.append(r)
    for i in range(1, 6):
        ws.column_dimensions[get_column_letter(i)].width = [26, 30, 12, 60, 26][i - 1]
    ws.cell(row=1, column=1).font = Font(bold=True)


def readme_sheet(wb, text_lines):
    ws = wb.create_sheet("README", 0)
    for line in text_lines:
        ws.append([line])
    ws.column_dimensions["A"].width = 130
    for r in range(1, ws.max_row + 1):
        ws.cell(row=r, column=1).alignment = Alignment(wrap_text=True, vertical="top")
    ws.cell(row=1, column=1).font = Font(bold=True, size=13)


README = [
    "GOLD ANOTASI PEMETAAN ATRIBUT - USULAN AWAL (SEBELUM VERIFIKASI)",
    "Dibuat pada 29 Okt 2026 dari atribut hasil parser proyek (src/agents/schema_matching/source_parsing.py) dan ID dari src/schema/gold_mapping.py.",
    "Kanonik: cabai-kms-canonical-v1 (59 baris, sheet 'Canonical Reference'). Pedoman: docs/annotation_guidelines_v1.md (lima status: ONE_TO_ONE, NO_MATCH, AMBIGUOUS, COMPOSITE, EXCLUDE).",
    "annotation_source 'usulan_awal_v1'. Gold yang dipakai untuk skor adalah gold/final/gold_semua_dataset_final.csv (terverifikasi_v1).",
    "Kolom perlu_adjudikasi = Y menandai butir yang keyakinannya Sedang/Rendah (mis. kepala putik vs tangkai putik, benang sari, tahap buah tidak disebut). Selesaikan butir Y terlebih dahulu.",
    "Kolom kuning = kolom manusia (status/kunci/catatan). Jangan mengubah mapping_item_id dan kolom identitas lain.",
    "Pembagian peran dataset: R = riset nyata (data_input, input_cabai_kms), S = sintetis/dummy (D01-D04), N = data baru dari sumber publik (E07 Kementan, E08 Zenodo, E09 label 80 dokumen).",
]


def sheet_per_dataset():
    for ds, rows in all_rows:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Annotations"
        write_sheet(ws, rows)
        add_reference(wb)
        readme_sheet(wb, README + [f"Dataset: {ds['file']} | sheet {ds['sheet']} | format {ds['format']} | {len(rows)} butir"])
        stem = Path(ds["file"]).stem
        wb.save(GOLD / f"gold_{DATASET_ID[ds['file']]}_{stem}.xlsx")


sheet_per_dataset()

# combined workbook
flat = [r for _, rows in all_rows for r in rows]
wb = openpyxl.Workbook()
ws = wb.active
ws.title = "Annotations"
write_sheet(ws, flat)
add_reference(wb)

summ = wb.create_sheet("Ringkasan")
statuses = ["ONE_TO_ONE", "NO_MATCH", "AMBIGUOUS", "COMPOSITE", "EXCLUDE"]
summ.append(["dataset_id", "file", "jumlah_butir", *statuses, "perlu_adjudikasi_Y"])
for ds, rows in all_rows:
    c = Counter(r["gold_status"] for r in rows)
    summ.append([DATASET_ID[ds["file"]], ds["file"], len(rows), *[c.get(s, 0) for s in statuses],
                 sum(1 for r in rows if r["perlu_adjudikasi"] == "Y")])
c = Counter(r["gold_status"] for r in flat)
summ.append(["TOTAL", "", len(flat), *[c.get(s, 0) for s in statuses], sum(1 for r in flat if r["perlu_adjudikasi"] == "Y")])
for i, w in enumerate([12, 44, 14, 14, 12, 12, 12, 10, 20], 1):
    summ.column_dimensions[get_column_letter(i)].width = w
for cell in summ[1]:
    cell.font = Font(bold=True)

# canonical coverage sheet
cov = wb.create_sheet("Cakupan Kanonik")
cov.append(["canonical_key", "label", "jumlah_butir_gold (ONE_TO_ONE+COMPOSITE)", "dataset"])
use = {}
for r in flat:
    if r["gold_status"] in ("ONE_TO_ONE", "COMPOSITE"):
        for k in r["gold_canonical_keys"].split("|"):
            use.setdefault(k, []).append(r["dataset_id"])
for rr in ref_rows[1:]:
    if rr[0]:
        ds_list = sorted(set(use.get(rr[0], [])))
        cov.append([rr[0], rr[1], len(use.get(rr[0], [])), ", ".join(ds_list)])
for i, w in enumerate([36, 36, 22, 40], 1):
    cov.column_dimensions[get_column_letter(i)].width = w
for cell in cov[1]:
    cell.font = Font(bold=True)

readme_sheet(wb, README + [f"Total: {len(flat)} butir dari {len(all_rows)} dataset."])
wb.save(GOLD / "gold_semua_dataset.xlsx")

with open(GOLD / "gold_semua_dataset.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=COLS)
    w.writeheader()
    w.writerows(flat)

print("TOTAL", len(flat))
for ds, rows in all_rows:
    c = Counter(r["gold_status"] for r in rows)
    print(DATASET_ID[ds["file"]], ds["file"], len(rows), dict(c), "Y=", sum(1 for r in rows if r["perlu_adjudikasi"] == "Y"))
print("overall", dict(c))
print("overall total", dict(Counter(r["gold_status"] for r in flat)), "Y=", sum(1 for r in flat if r["perlu_adjudikasi"] == "Y"))
unused = [k for k in valid_keys if k not in use]
print("canonical keys never used as gold target:", len(unused), sorted(unused))
