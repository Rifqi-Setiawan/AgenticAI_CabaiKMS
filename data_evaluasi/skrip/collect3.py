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

# --- round 3: drop the images rejected in the second visual review, then top up
idx = {int(r["n"]): r for r in csv.DictReader(open(HERE / "review" / "index.csv", encoding="utf-8-sig"))}
EXC = [1, 2, 4, 6, 7, 13, 14, 18, 19, 20, 27, 31, 42, 43, 44]
exclude_titles = {idx[i]["title"] for i in EXC}
prev = json.loads((HERE / "img_selected_round2.json").read_text(encoding="utf-8"))
final = []
for it in prev:
    if it["title"] in exclude_titles:
        continue
    it = dict(it)
    it["new"] = False
    final.append(it)
print("kept after review:", len(final))

# --- top-up targets
TARGET = {
    ("KNOWN", "Habanero"): 24, ("KNOWN", "Cayenne"): 12, ("KNOWN", "Jalapeno"): 16, ("KNOWN", "Hungarian Wax"): 9,
    ("KNOWN", "Serrano"): 6, ("KNOWN", "Cabai Rawit"): 14,
    ("OTHER", "Bhut Jolokia"): 10, ("OTHER", "Black Pearl"): 7, ("OTHER", "Banana Pepper"): 5,
    ("OTHER", "Carolina Reaper"): 6, ("OTHER", "Trinidad Moruga Scorpion"): 6,
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
used = {it["title"] for it in final} | exclude_titles | {x["title"] for x in prev} | {x["title"] for x in json.loads((HERE / "img_selected_round1.json").read_text(encoding="utf-8"))}
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
