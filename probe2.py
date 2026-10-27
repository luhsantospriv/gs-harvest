# -*- coding: utf-8 -*-
import json, random, sys, time, uuid
import gs_client as C

HOST = "https://api2.good-short.com"
BOOK = "31001250229"
C._T = None

H = json.load(open("gs_vip_headers.json", encoding="utf-8"))
H.update({"deviceid": str(uuid.uuid4()), "androidid": "%016x" % uuid.uuid4().int,
          "authorization": "", "afid": "%d-%d" % (
              random.randint(1700000000000, 1800000000000),
              random.randint(1000000000000000000, 9999999999999999999)),
          "model": "SM-G781B", "brand": "samsung"})

st, r = C.chamar("hwycclientreels/app/bootstrap", {}, extra=H, host=HOST)
d = json.loads(r)
u = (d.get("data") or {}).get("user") or {}
tok = u.get("token") or ""
print("conta:", u.get("uid"))
if not tok:
    print("sem token"); sys.exit(1)
H["authorization"] = tok if tok.startswith("Bearer ") else "Bearer " + tok

st, r = C.chamar("hwycclientreels/chapter/list", {"bookId": BOOK}, extra=H, host=HOST)
caps = (json.loads(r).get("data") or {}).get("list") or []
pagos = [c for c in sorted(caps, key=lambda x: x.get("index", 0))
         if (c.get("price") or 0) > 0]
print("pagos:", len(pagos))

ok = 0
for c in pagos[:10]:
    st, r = C.chamar("hwycclientreels/chapter/load",
                     {"bookId": BOOK, "chapterIds": [c["id"]], "viewAd": True},
                     extra=H, host=HOST)
    d = json.loads(r)
    it = ((d.get("data") or {}).get("list") or [{}])[0]
    n = len(it.get("cdnList") or [])
    print("  cap %s -> status=%s cdn=%d %s" % (c["id"], d.get("status"), n,
                                               str(d.get("message"))[:20]))
    if n:
        ok += 1
    else:
        break
    time.sleep(0.5)
print("RESULTADO: %d unlocks" % ok)
