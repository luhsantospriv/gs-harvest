# -*- coding: utf-8 -*-
import json
import gs_harvest as G
import gs_client as C

BOOK = "31001747475"
caps, _ = G.capitulos(BOOK)
pagos = [c for c in (caps or []) if (c.get("price") or 0) > 0]
cid = pagos[20]["id"]

H, host = G.conta()
print("conta nova, host", host)

def mostra(nome, rota, corpo):
    st, r = C.chamar(rota, corpo, extra=H, host=host)
    try:
        d = json.loads(r)
    except Exception:
        print(nome, "-> nao-json", r[:120])
        return None
    it = ((d.get("data") or {}).get("list") or [{}])[0]
    print("%-22s status=%s msg=%-28s cdn=%d" % (
        nome, d.get("status"), str(d.get("message"))[:28], len(it.get("cdnList") or [])))
    return d

mostra("load viewAd", "hwycclientreels/chapter/load",
       {"bookId": BOOK, "chapterIds": [cid], "viewAd": True})
mostra("ad/iaa", "hwycclientreels/ad/iaa", {"bookId": BOOK, "chapterId": cid})
mostra("load pos-iaa", "hwycclientreels/chapter/load",
       {"bookId": BOOK, "chapterIds": [cid], "viewAd": True})
mostra("load sem viewAd", "hwycclientreels/chapter/load",
       {"bookId": BOOK, "chapterIds": [cid]})
mostra("ad/iaa type1", "hwycclientreels/ad/iaa",
       {"bookId": BOOK, "chapterId": cid, "adType": 1, "rewardType": 1})
mostra("load denovo", "hwycclientreels/chapter/load",
       {"bookId": BOOK, "chapterIds": [cid], "viewAd": True})
