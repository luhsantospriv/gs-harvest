# -*- coding: utf-8 -*-
import json
import gs_harvest as G

BOOK = "31001747475"
caps, _ = G.capitulos(BOOK)
pagos = [c for c in (caps or []) if (c.get("price") or 0) > 0][:24]
print("pagos:", len(pagos))
G.b2_pool(2)

# sequencial: quantos capitulos saem antes de parar?
ok = 0
for c in pagos:
    urls = G.urls_do_capitulo(BOOK, c)
    if urls:
        ok += 1
    else:
        print("parou no capitulo %d apos %d ok" % (c["id"], ok))
        break
print("SEQUENCIAL ok=%d de %d (contas criadas=%d)" % (ok, len(pagos), G._rc["contas"]))
