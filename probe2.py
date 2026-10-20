# -*- coding: utf-8 -*-
import json
from concurrent.futures import ThreadPoolExecutor
import gs_harvest as G

BOOK = "31001747475"
caps, err = G.capitulos(BOOK)
caps = caps or []
pagos = [c for c in caps if (c.get("price") or 0) > 0][:40]
print("pagos:", len(pagos))
G.b2_pool(8)

i = 0
for nw in (1, 2, 4, 8):
    lote = pagos[i:i + nw * 2]
    i += len(lote)
    if not lote:
        break
    with ThreadPoolExecutor(max_workers=nw) as ex:
        res = list(ex.map(lambda c: G.processar(BOOK, c), lote))
    bons = sum(1 for r, e in res if r)
    erros = [e for r, e in res if not r]
    print("workers=%d lote=%d ok=%d erros=%s" % (nw, len(lote), bons, erros[:2]))
