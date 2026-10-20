# -*- coding: utf-8 -*-
import json, os, uuid, random
import gs_client as C

BASE = json.load(open("gs_vip_headers.json", encoding="utf-8"))
BOOK = "31001747475"
HOSTS = ["https://api2.good-short.com", "https://api.goodreels.com",
         "https://api.good-short.com", "https://api-akm.goodreels.com"]

def conta(host):
    H = dict(BASE)
    H.update({"deviceid": str(uuid.uuid4()), "androidid": "%016x" % uuid.uuid4().int,
              "authorization": "",
              "afid": "%d-%d" % (random.randint(1792000000000, 1792999999999),
                                 random.randint(2000000000000000000, 2999999999999999999))})
    try:
        st, r = C.chamar("hwycclientreels/app/bootstrap", {}, extra=H, host=host)
        d = json.loads(r)
        u = (d.get("data") or {}).get("user") or {}
        tok = u.get("token") or ""
        if tok and not tok.startswith("Bearer "):
            tok = "Bearer " + tok
        H["authorization"] = tok
        print("  bootstrap:", st, d.get("status"), d.get("message"), "uid", u.get("uid"))
    except Exception as e:
        print("  bootstrap ERRO", repr(e)[:70])
    return H

for host in HOSTS:
    print("==", host)
    H = conta(host)
    try:
        st, r = C.chamar("hwycclientreels/chapter/list", {"bookId": BOOK}, extra=H, host=host)
        print("  list:", st, r[:180])
    except Exception as e:
        print("  list ERRO", repr(e)[:90])
    try:
        st, r = C.chamar("hwycclientreels/chapter/load",
                         {"bookId": BOOK, "chapterIds": [67427573], "viewAd": True},
                         extra=H, host=host)
        d = json.loads(r)
        it = ((d.get("data") or {}).get("list") or [{}])[0]
        print("  load:", d.get("status"), str(d.get("message"))[:40],
              "cdn", len(it.get("cdnList") or []))
    except Exception as e:
        print("  load ERRO", repr(e)[:90])
