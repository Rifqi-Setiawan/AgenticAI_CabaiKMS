import csv, hashlib, html, json, random, re, sys, time, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import commons as C

OUT = Path(r"D:\college\Semester 6\Penulisan Proposal\project\data_evaluasi\gambar")
UP = OUT / "drive_upload"
UP.mkdir(parents=True, exist_ok=True)
random.seed(20261029)

KNOWN = {  # registry variety -> (categories, n)
    "Cabai Rawit": (["Category:Capsicum frutescens 'Rawit'", "Category:Capsicum frutescens in Indonesia", "Category:Bird's eye chili"], 16),
    "Jalapeno": (["Category:Jalapeño"], 16),
    "Habanero": (["Category:Habanero"], 16),
    "Cayenne": (["Category:Cayenne pepper"], 16),
    "Paprika": (["Category:Bell peppers"], 16),
    "Cabai Korea": (["Category:Korean chili", "Category:Cheongyang chili"], 16),
}
OTHER = {  # variety (NOT in registry) -> (categories, n)
    "Bhut Jolokia": (["Category:Capsicum chinense 'Bhut Jolokia'"], 6),
    "Carolina Reaper": (["Category:Capsicum chinense 'Carolina Reaper'"], 6),
    "Scotch Bonnet": (["Category:Scotch Bonnet"], 6),
    "Piri Piri": (["Category:Capsicum frutescens 'Piri Piri'"], 6),
    "Padron": (["Category:Pimientos de Padrón"], 6),
    "Trinidad Moruga Scorpion": (["Category:Trinidad Moruga Scorpion"], 6),
    "Poblano": (["Category:Poblano"], 6),
    "Shishito": (["Category:Shishito"], 6),
}
UNCERT = {  # reason -> (categories, n)
    "cabai kering": (["Category:Dried red chili pepper", "Category:Chillies drying"], 4),
    
    "cabai hijau generik": (["Category:Green chili peppers"], 4),
    "tak teridentifikasi": (["Category:Unidentified Capsicum"], 5),
    "bibit": (["Category:Capsicum (seedlings)"], 3),
}
BAD_TITLE = re.compile(r"\b(map|diagram|logo|illustration|drawing|painting|plate|herbarium|pdf|svg|icon|cartoon|distribution|chart|cross.?section|seed[s]? |recipe|sauce|soup|salsa|powder)\b", re.I)
PART_KW = [("BUNGA", r"flower|bloom|blossom|bunga"), ("DAUN", r"\bleaf\b|\bleaves\b|daun"), ("BATANG", r"\bstem\b|\bstalk\b|batang")]


FOOD_TITLE = re.compile(r"dried|drying|dry |markt|market|mercado|tomat|sauce|pizza|dish|cook|grill|roast|stuff|salad|restaurant|fried|stew|bowl|plate|jar|pickl|basket|stall|vendor|shop|store|supermarket|crate|bag|box|tray|cutting|sliced|chopped|cut |cut\.|half|halved|knife|hand|held|holding|people|man |woman|child|festival|exhibition|mix|variety of|assort|collection|various|different|group of", re.I)


REQUIRE = {
    "Cabai Rawit": r"rawit|bird|thai|labuyo|hi[eể]m|cabe|cabai",
    "Jalapeno": r"jalape",
    "Habanero": r"habanero",
    "Cayenne": r"cayenne",
    "Paprika": r"bell|paprika|capsicum|pepper",
    "Cabai Korea": r"korea|cheongyang|gochu|go choo|go-choo|yeongyang",
    "Bhut Jolokia": r"bhut|jolokia|ghost",
    "Carolina Reaper": r"reaper",
    "Scotch Bonnet": r"scotch|bonnet",
    "Piri Piri": r"piri|peri|capsicum|pepper|chili|chilli",
    "Padron": r"padr",
    "Trinidad Moruga Scorpion": r"moruga|scorpion|trinidad",
    "Poblano": r"poblano",
    "Shishito": r"shishito",
}
BAD_WORDS = re.compile(r"(?<![a-z])with(?![a-z])|pasta|ragu|bolognese|soup|pork|chicken|fish|rice|noodle|bread|cake|curry|burger|sandwich|breakfast|lunch|dinner|meal|food|menu|dsc|img_|sony|canon|nikon|^file:[0-9]{6,}|farm|tradition|nordkorea|north korea|von |roast beef|olives|cheese|biscuit|poppers|jelly|tarte|aperitif|paste|chocolat|filets|conserves|gemahlen|maquereaux|village|taco|queso|package|for sale|sale|sal maldon|boquerones|molho|twigim|subway|australian|mold|rhizoctonia|transparent|top view|salsa|jar|bottle|can |label|flakes|powder|ground|rotini|masala|cutout|isolated|jerusalem|roast beef|tikka", re.I)

EXCLUDE_TITLES = ("File:Habanero's + Jalapeño's.JPG", "File:Phơi ớt hiểm.jpg", "File:Itxassou Piment.JPG", "File:Pimientos de Padrón 1.JPG")
FORCE_UNCERTAIN = {"File:Habanero's + Jalapeño's.JPG": "campuran dua varietas"}


def strip(s):
    return html.unescape(re.sub(r"<.*?>", "", s or "")).strip()


def part_of(title):
    for p, kw in PART_KW:
        if re.search(kw, title, re.I):
            return p
    return "BUAH"


def cat_files(cats):
    seen, out = set(), []
    for c in cats:
        for t in C.files(c):
            if t not in seen:
                seen.add(t)
                out.append((t, c))
    return out


def meta(titles):
    res = {}
    for i in range(0, len(titles), 30):
        ch = titles[i:i + 30]
        d = C.api(action="query", prop="imageinfo", titles="|".join(ch), iiprop="url|size|mime|extmetadata|sha1", iiurlwidth=1024)
        for pg in d["query"]["pages"].values():
            ii = (pg.get("imageinfo") or [None])[0]
            if ii:
                res[pg["title"]] = ii
        time.sleep(0.3)
    return res


def pick(groups, label_kind):
    chosen = []
    for name, (cats, n) in groups.items():
        cand = sorted(cat_files(cats))
        cand = [x for x in cand if x[0] not in EXCLUDE_TITLES and not BAD_TITLE.search(x[0]) and re.search(r"[.](jpe?g)$", x[0], re.I)]
        if label_kind in ("KNOWN", "OTHER"):
            cand = [x for x in cand if not FOOD_TITLE.search(x[0]) and not BAD_WORDS.search(x[0]) and re.search(REQUIRE[name], x[0], re.I)]
        info = meta([t for t, _ in cand])
        ok = []
        for t, c in cand:
            ii = info.get(t)
            if not ii or ii.get("mime") not in ("image/jpeg", "image/png"):
                continue
            if ii.get("width", 0) < 600 or ii.get("height", 0) < 450:
                continue
            em = ii.get("extmetadata", {})
            lic = strip(em.get("LicenseShortName", {}).get("value", ""))
            if not lic:
                continue
            ok.append((t, c, ii, lic, strip(em.get("Artist", {}).get("value", "")), strip(em.get("Credit", {}).get("value", ""))))
        random.shuffle(ok)
        # keep at most 3 images per uploader to avoid near-duplicate burst shots
        per, sel = {}, []
        for row in ok:
            key = row[4][:40] or "?"
            if per.get(key, 0) >= 3:
                continue
            per[key] = per.get(key, 0) + 1
            sel.append(row)
            if len(sel) >= n:
                break
        print(f"{label_kind:9s} {name:16s} candidates={len(ok):3d} selected={len(sel)}/{n}")
        for t, c, ii, lic, art, cred in sel:
            chosen.append(dict(label_kind=label_kind, group=name, title=t, category=c, info=ii, license=lic, author=art, credit=cred))
    return chosen


items = pick(KNOWN, "KNOWN") + pick(OTHER, "OTHER") + pick(UNCERT, "UNCERTAIN")
for ft, reason in FORCE_UNCERTAIN.items():
    mi = meta([ft]).get(ft)
    if mi:
        em = mi.get("extmetadata", {})
        items.append(dict(label_kind="UNCERTAIN", group=reason, title=ft, category="(manual)", info=mi,
                          license=strip(em.get("LicenseShortName", {}).get("value", "")),
                          author=strip(em.get("Artist", {}).get("value", "")), credit=""))
print("TOTAL selected", len(items))
Path(r"C:\Users\Rifqi\AppData\Local\Temp\cabai_data\img_selected.json").write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
