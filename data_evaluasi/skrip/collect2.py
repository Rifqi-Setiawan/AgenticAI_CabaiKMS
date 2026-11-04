"""Round 2 curation: apply the visual-review decisions, then top up groups from unreviewed candidates (hash order)."""
import csv, hashlib, json, re, sys, time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
src = (HERE / "collect_images.py").read_text(encoding="utf-8")
cut = src.index("items = pick(KNOWN")
ns = {"__name__": "collect_defs", "__file__": str(HERE / "collect_images.py")}
exec(compile(src[:cut], "collect_defs", "exec"), ns)
meta, cat_files, strip = ns["meta"], ns["cat_files"], ns["strip"]
BAD_TITLE, FOOD_TITLE, BAD_WORDS, EXCLUDE_TITLES = ns["BAD_TITLE"], ns["FOOD_TITLE"], ns["BAD_WORDS"], ns["EXCLUDE_TITLES"]
REQUIRE = dict(ns["REQUIRE"])

# --- review decisions (indices refer to review/index.csv of round 1)
idx = {int(r["n"]): r for r in csv.DictReader(open(HERE / "review" / "index.csv", encoding="utf-8-sig"))}
EXC = [25, 29, 30, 31, 32, 33, 37, 42, 56, 64, 66, 69, 70, 72, 73, 76, 77, 79, 80, 82, 83, 85, 86, 90,
       103, 104, 106, 107, 109, 110, 111, 112, 113, 114, 116, 118, 119, 127, 129, 130, 136, 137, 145]
TO_UNC = {91: "bibit/daun saja", 98: "bibit/daun saja", 99: "bibit/daun saja"}
TO_JAL = [151]
exclude_titles = {idx[i]["title"] for i in EXC}
to_unc = {idx[i]["title"]: v for i, v in TO_UNC.items()}
to_jal = {idx[i]["title"] for i in TO_JAL}

prev = json.loads((HERE / "img_selected.json").read_text(encoding="utf-8"))
final = []
for it in prev:
    t = it["title"]
    if t in exclude_titles:
        continue
    it = dict(it)
    it["new"] = False
    if t in to_unc:
        it["label_kind"], it["group"] = "UNCERTAIN", to_unc[t]
    if t in to_jal:
        it["label_kind"], it["group"] = "KNOWN", "Jalapeno"
    final.append(it)
print("kept after review:", len(final))

# --- top-up targets
TARGET = {
    ("KNOWN", "Cabai Rawit"): 14, ("KNOWN", "Cayenne"): 14, ("KNOWN", "Habanero"): 16, ("KNOWN", "Jalapeno"): 16,
    ("KNOWN", "Paprika"): 15, ("KNOWN", "Cabai Korea"): 15,
    ("OTHER", "Bhut Jolokia"): 8, ("OTHER", "Carolina Reaper"): 6, ("OTHER", "Scotch Bonnet"): 6,
    ("OTHER", "Trinidad Moruga Scorpion"): 6, ("OTHER", "Padron"): 2, ("OTHER", "Poblano"): 2, ("OTHER", "Shishito"): 2,
    ("KNOWN", "Serrano"): 6, ("KNOWN", "Hungarian Wax"): 9, ("OTHER", "Banana Pepper"): 5, ("OTHER", "Black Pearl"): 5,
}
CATS = {
    "Cabai Rawit": ["Category:Capsicum frutescens 'Rawit'", "Category:Capsicum frutescens in Indonesia", "Category:Bird's eye chili"],
    "Cayenne": ["Category:Cayenne pepper"], "Habanero": ["Category:Habanero"], "Jalapeno": ["Category:Jalapeño"],
    "Paprika": ["Category:Bell peppers"], "Cabai Korea": ["Category:Korean chili", "Category:Cheongyang chili"],
    "Bhut Jolokia": ["Category:Capsicum chinense 'Bhut Jolokia'"], "Carolina Reaper": ["Category:Capsicum chinense 'Carolina Reaper'"],
    "Scotch Bonnet": ["Category:Scotch Bonnet"], "Trinidad Moruga Scorpion": ["Category:Trinidad Moruga Scorpion"],
    "Padron": ["Category:Pimientos de Padrón"], "Poblano": ["Category:Poblano"], "Shishito": ["Category:Shishito"],
    "Serrano": ["Category:Serrano pepper"], "Hungarian Wax": ["Category:Hungarian wax pepper"],
    "Banana Pepper": ["Category:Banana peppers"], "Black Pearl": ["Category:Capsicum annuum 'Black Pearl'"],
}
REQUIRE.update({"Serrano": r"serrano", "Hungarian Wax": r"wax|hungarian", "Banana Pepper": r"banana", "Black Pearl": r"black pearl|pearl"})
PAPRIKA_NOT = re.compile(r"plant|seedling|mix|assort|display|rainbow|miniature|small|cut|slice", re.I)
used = {it["title"] for it in final} | exclude_titles | {x["title"] for x in prev}
h = lambda t: hashlib.md5(t.encode("utf-8")).hexdigest()

for (kind, grp), want in TARGET.items():
    have = sum(1 for it in final if it["label_kind"] == kind and it["group"] == grp)
    need = want - have
    if need <= 0:
        continue
    cand = sorted(cat_files(CATS[grp]), key=lambda x: h(x[0]))
    cand = [x for x in cand if x[0] not in used and x[0] not in EXCLUDE_TITLES and not BAD_TITLE.search(x[0])
            and re.search(r"[.](jpe?g)$", x[0], re.I) and not FOOD_TITLE.search(x[0]) and not BAD_WORDS.search(x[0])
            and re.search(REQUIRE.get(grp, r"."), x[0], re.I)]
    if grp == "Paprika":
        cand = [x for x in cand if not PAPRIKA_NOT.search(x[0])]
    info = meta([t for t, _ in cand[:80]])
    got = 0
    for t, c in cand:
        ii = info.get(t)
        if not ii or ii.get("mime") != "image/jpeg" or ii.get("width", 0) < 600 or ii.get("height", 0) < 450:
            continue
        em = ii.get("extmetadata", {})
        lic = strip(em.get("LicenseShortName", {}).get("value", ""))
        if not lic:
            continue
        final.append(dict(label_kind=kind, group=grp, title=t, category=c, info=ii, license=lic,
                          author=strip(em.get("Artist", {}).get("value", "")), credit="", new=True))
        used.add(t)
        got += 1
        if got >= need:
            break
    print(f"top-up {kind:6s} {grp:26s} have={have:2d} want={want:2d} added={got}")

from collections import Counter
print("TOTAL", len(final), dict(Counter(i["label_kind"] for i in final)))
(HERE / "img_selected.json").write_text(json.dumps(final, ensure_ascii=False, indent=1), encoding="utf-8")
