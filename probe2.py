# -*- coding: utf-8 -*-
import time
import gs_harvest as G

BOOK = "31001747475"
caps, _ = G.capitulos(BOOK)
pagos = [c for c in (caps or []) if (c.get("price") or 0) > 0]
print("pagos:", len(pagos), flush=True)

t0 = time.time()
for rodada in range(1, 13):          # ate 60 min, de 5 em 5
    G.troca_conta()
    ok = 0
    for c in pagos[20:23]:
        if G.urls_do_capitulo(BOOK, c):
            ok += 1
    dt = (time.time() - t0) / 60.0
    print("SONDA t=%.0f min -> %d/3 capitulos" % (dt, ok), flush=True)
    if ok >= 2:
        print("SONDA LIBEROU em %.0f min" % dt, flush=True)
        break
    time.sleep(300)
