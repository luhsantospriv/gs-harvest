# -*- coding: utf-8 -*-
import json, os
import gs_harvest as G
import gs_client as C

BOOK = "31001747475"
Hc, host = G.conta()
print("conta auth:", str((Hc or {}).get("authorization", ""))[:18], "host:", host)

caps, err = G.capitulos(BOOK)
caps = caps or []
print("caps:", len(caps), "err:", err)
pagos = [c for c in caps if (c.get("price") or 0) > 0][:3]
print("pagos:", [c["id"] for c in pagos])

for c in pagos:
    urls = G.urls_do_capitulo(BOOK, c)
    print("  urls_do_capitulo cap", c["id"], "->", len(urls))

print("--- chamada crua com a MESMA conta ---")
Hc, host = G.conta()
st, r = C.chamar("hwycclientreels/chapter/load",
                 {"bookId": BOOK, "chapterIds": [pagos[0]["id"]], "viewAd": True},
                 extra=Hc, host=host)
d = json.loads(r)
it = ((d.get("data") or {}).get("list") or [{}])[0]
print("status:", d.get("status"), "msg:", str(d.get("message"))[:40],
      "cdn:", len(it.get("cdnList") or []))
print("raw:", r[:200])
