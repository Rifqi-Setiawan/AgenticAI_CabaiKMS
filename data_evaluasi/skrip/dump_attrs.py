import json, sys
from pathlib import Path
sys.path.insert(0, r"D:\college\Semester 6\Penulisan Proposal\project")
from src.agents.schema_matching.source_parsing import load_row_oriented_columns, load_transposed_rows
from src.schema.gold_mapping import build_mapping_item_identities
from src.schema.provenance import source_file_sha256

INP = Path(r"D:\college\Semester 6\Penulisan Proposal\project\data_evaluasi\inputs")
SPECS = [
    ("data_input.xlsx", "Resume Data", "row-oriented", None),
    ("input_cabai_kms.xlsx", "Data Varietas", "row-oriented", 1),
    ("D01_transposed_indonesia_mixed.xlsx", "Data_Transposed", "transposed", None),
    ("D02_row_flat_english_semantic.xlsx", "English_Flat_Data", "row-oriented", 1),
    ("D03_row_multilevel_indonesia.xlsx", "Data_Bertingkat", "row-oriented", 2),
    ("D04_varietas_kosong_invalid.xlsx", "Data_Invalid", "row-oriented", 1),
    ("E07_kementan_deskripsi_ext.xlsx", "Deskripsi Varietas", "row-oriented", 1),
    ("E08_zenodo_capsicum_en.xlsx", "Observed85_readable", "row-oriented", 1),
    ("dataset_cabai_deskripsi_varietas.xlsx", "transposed", "transposed", None),
]
out = []
for fname, sheet, fmt, hr in SPECS:
    p = INP / fname
    try:
        if fmt == "transposed":
            attrs, _ = load_transposed_rows(p, sheet)
        else:
            attrs = load_row_oriented_columns(p, sheet, header_rows=hr)
    except Exception as e:  # report and continue
        print("FAIL", fname, repr(e)[:200])
        continue
    sha = source_file_sha256(p)
    idents = build_mapping_item_identities(
        source_file_sha256=sha, source_sheet=sheet, source_format=fmt,
        source_items=[(None, a.display_name) for a in attrs],
    )
    items = []
    for a, i in zip(attrs, idents):
        items.append({
            "display": a.display_name, "name": a.attribute_name, "context": a.structural_context,
            "samples": [str(v)[:60] for v in a.sample_values[:3]],
            "n_values": len(a.sample_values),
            "item_id": i.mapping_item_id, "id_kind": getattr(i.identity_kind, "value", str(i.identity_kind)),
            "id_value": i.identity_value, "id_issue": i.issue_code,
        })
    out.append({"file": fname, "sheet": sheet, "format": fmt, "header_rows": hr, "sha": sha, "items": items})
    print(fname, len(items), "items", "ID issues:", sum(1 for x in items if x["id_issue"]))
Path(r"C:\Users\Rifqi\AppData\Local\Temp\cabai_data\attrs.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
