import json, sys, time, urllib.parse, urllib.request
UA = "CabaiKMS-research/1.0 (thesis dataset prep; https://github.com/Rifqi-Setiawan/AgenticAI_CabaiKMS)"
API = "https://commons.wikimedia.org/w/api.php"


def api(**p):
    p["format"] = "json"
    url = API + "?" + urllib.parse.urlencode(p)
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.load(r)
        except Exception as e:
            time.sleep(1.5 * (i + 1))
    raise RuntimeError("api failed " + url[:120])


def subcats(cat):
    out, cont = [], {}
    while True:
        d = api(action="query", list="categorymembers", cmtitle=cat, cmtype="subcat", cmlimit=500, **cont)
        out += [m["title"] for m in d["query"]["categorymembers"]]
        if "continue" in d:
            cont = {"cmcontinue": d["continue"]["cmcontinue"]}
        else:
            return out


def files(cat, limit=500):
    out, cont = [], {}
    while len(out) < limit:
        d = api(action="query", list="categorymembers", cmtitle=cat, cmtype="file", cmlimit=500, **cont)
        out += [m["title"] for m in d["query"]["categorymembers"]]
        if "continue" in d:
            cont = {"cmcontinue": d["continue"]["cmcontinue"]}
        else:
            break
    return out


def info(cats):
    res = {}
    for i in range(0, len(cats), 40):
        chunk = cats[i:i + 40]
        d = api(action="query", prop="categoryinfo", titles="|".join(chunk))
        for pg in d["query"]["pages"].values():
            ci = pg.get("categoryinfo", {})
            res[pg["title"]] = (ci.get("files", 0), ci.get("subcats", 0))
    return res


if __name__ == "__main__":
    roots = sys.argv[1:]
    for root in roots:
        subs = subcats(root)
        inf = info(subs) if subs else {}
        print("==", root, "files:", info([root]).get(root), "subcats:", len(subs))
        for s in subs:
            print("   ", s, inf.get(s))
