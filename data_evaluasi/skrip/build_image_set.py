import csv, hashlib, json, random, re, time, urllib.request
from pathlib import Path
import openpyxl

OUT = Path(r"D:\college\Semester 6\Penulisan Proposal\project\data_evaluasi\gambar")
UP = OUT / "drive_upload"
UP.mkdir(parents=True, exist_ok=True)
MAN = OUT / "manifest"
MAN.mkdir(parents=True, exist_ok=True)
UA = "CabaiKMS-research/1.0 (thesis dataset prep; https://github.com/Rifqi-Setiawan/AgenticAI_CabaiKMS)"
random.seed(20261029)

items = json.loads(Path(r"C:\Users\Rifqi\AppData\Local\Temp\cabai_data\img_selected.json").read_text(encoding="utf-8"))
REGISTRY = ["Cabai Rawit", "Jalapeno", "Habanero", "Cayenne", "Paprika", "Cabai Korea", "Serrano", "Hungarian Wax"]
slug = lambda s: re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
PART_KW = [("BUNGA", r"flower|bloom|blossom|bunga|blüte|blute|(?<![a-z])hoa(?![a-z])|kwiat"), ("DAUN", r"(?<![a-z])leaf(?![a-z])|leaves|daun|seedling|sprout|days old|days plant|young .*plant|[0-9]+ days"), ("BATANG", r"\bstem\b|\bstalk\b|batang")]


def part_of(title):
    for p, kw in PART_KW:
        if re.search(kw, title, re.I):
            return p
    return "BUAH"


# global neutral numbering (shuffled so numbering leaks nothing)
order = list(range(len(items)))
random.shuffle(order)
for num, i in enumerate(order, 1):
    items[i]["num"] = num

# filename condition: 40% NETRAL / 40% INFORMATIF / 20% MENYESATKAN, stratified by label_kind
for kind in ("KNOWN", "OTHER", "UNCERTAIN"):
    idx = [i for i, it in enumerate(items) if it["label_kind"] == kind]
    random.shuffle(idx)
    n = len(idx)
    n_neu, n_mis = round(n * 0.4), round(n * 0.2)
    for k, i in enumerate(idx):
        items[i]["cond"] = "NETRAL" if k < n_neu else ("MENYESATKAN" if k < n_neu + n_mis else "INFORMATIF")

# split val/test 30/70 stratified by group
groups = {}
for i, it in enumerate(items):
    groups.setdefault((it["label_kind"], it["group"]), []).append(i)
for g, idx in groups.items():
    random.shuffle(idx)
    n_val = max(1, round(len(idx) * 0.3))
    for k, i in enumerate(idx):
        items[i]["split"] = "val" if k < n_val else "test"

rows = []
for it in items:
    ii = it["info"]
    mime = ii["mime"]
    ext = ".jpg" if mime == "image/jpeg" else ".png"
    kind, grp = it["label_kind"], it["group"]
    part = part_of(it["title"])
    n = it["num"]
    if kind == "KNOWN":
        true_var = grp
    elif kind == "OTHER":
        true_var = grp
    else:
        true_var = ""
    cond = it["cond"]
    if cond == "NETRAL":
        fname = f"IMG_{n:04d}{ext}"
        fhint = ""
    elif cond == "INFORMATIF":
        base = slug(grp) if kind in ("KNOWN", "OTHER") else {"cabai kering": "cabai-kering", "serpihan cabai": "serpihan-cabai", "cabai hijau generik": "cabai-hijau", "bibit/daun saja": "bibit-cabai", "campuran dua varietas": "cabai-campuran", "tak teridentifikasi": "cabai", "bibit": "bibit-cabai"}[grp]
        fname = f"{base}_{part.lower()}_{n:03d}{ext}"
        fhint = grp if kind in ("KNOWN", "OTHER") else ""
    else:  # MENYESATKAN: named after a different registry variety
        wrong = random.choice([v for v in REGISTRY if v != true_var])
        fname = f"{slug(wrong)}_{part.lower()}_{n:03d}{ext}"
        fhint = wrong
    rows.append(dict(
        filename=fname, label_kind=kind, true_variety=true_var, in_registry="Y" if true_var in REGISTRY else "N",
        true_part=part, filename_condition=cond, filename_hint_variety=fhint,
        expected_fusion={"KNOWN": "AUTO_LINK" if cond != "MENYESATKAN" else "REVIEW_MISMATCH",
                         "OTHER": "CANDIDATE" if cond != "MENYESATKAN" else "REVIEW_MISMATCH",
                         "UNCERTAIN": "REVIEW_UNCERTAIN"}[kind],
        split=it["split"], uncertain_reason=grp if kind == "UNCERTAIN" else "",
        commons_title=it["title"], source_category=it["category"], license=it["license"], author=it["author"],
        source_url="https://commons.wikimedia.org/wiki/" + it["title"].replace(" ", "_"),
        download_url=ii.get("thumburl") or ii.get("url"), _mime=mime,
    ))

# download
ok = 0
for r in rows:
    path = UP / r["filename"]
    if path.exists() and path.stat().st_size > 5000:
        ok += 1
    else:
        for attempt in range(4):
            try:
                req = urllib.request.Request(r["download_url"], headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = resp.read()
                if len(data) < 5000 or not (data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n"):
                    raise RuntimeError("not an image")
                path.write_bytes(data)
                ok += 1
                break
            except Exception as e:
                time.sleep(2 * (attempt + 1))
        else:
            r["_failed"] = True
        time.sleep(0.4)
    if path.exists():
        data = path.read_bytes()
        r["file_sha256"] = hashlib.sha256(data).hexdigest()
        r["file_size_kb"] = round(len(data) / 1024)
print("downloaded/present:", ok, "of", len(rows), "failed:", sum(1 for r in rows if r.get("_failed")))

rows = [r for r in rows if not r.get("_failed")]
for r in rows:
    r.pop("_mime", None)
    r.pop("_failed", None)
rows.sort(key=lambda r: (r["split"], r["label_kind"], r["true_variety"], r["filename"]))

cols = ["filename", "label_kind", "true_variety", "in_registry", "true_part", "filename_condition", "filename_hint_variety",
        "expected_fusion", "split", "uncertain_reason", "file_sha256", "file_size_kb", "commons_title", "source_category",
        "license", "author", "source_url", "download_url"]
with open(MAN / "gold_gambar_manifest.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    w.writerows(rows)

wb = openpyxl.Workbook()
ws = wb.active
ws.title = "Manifest"
ws.append(cols)
for r in rows:
    ws.append([r.get(c) for c in cols])
ws.freeze_panes = "A2"
ws.auto_filter.ref = ws.dimensions
for i, c in enumerate(cols, 1):
    ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = {"filename": 34, "commons_title": 50, "source_url": 50, "download_url": 30, "author": 30}.get(c, 16)
wb.save(MAN / "gold_gambar_manifest.xlsx")

# registry spreadsheet (what the run-scope variety extraction reads)
reg = openpyxl.Workbook()
w2 = reg.active
w2.title = "Data Varietas"
w2.append(["Varietas Cabai"])
for v in REGISTRY:
    w2.append([v])
reg.save(OUT / "spreadsheet_varietas_terdaftar.xlsx")

# attribution file
with open(MAN / "ATRIBUSI_LISENSI.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["filename", "commons_title", "author", "license", "source_url"])
    for r in rows:
        w.writerow([r["filename"], r["commons_title"], r["author"], r["license"], r["source_url"]])

from collections import Counter
print("kind", dict(Counter(r["label_kind"] for r in rows)))
print("cond", dict(Counter(r["filename_condition"] for r in rows)))
print("split", dict(Counter(r["split"] for r in rows)))
print("part", dict(Counter(r["true_part"] for r in rows)))
print("license", dict(Counter(r["license"] for r in rows)))
print("size MB", round(sum(r["file_size_kb"] for r in rows) / 1024, 1))
