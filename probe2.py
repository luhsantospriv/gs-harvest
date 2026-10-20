# -*- coding: utf-8 -*-
import threading, time
from concurrent.futures import ThreadPoolExecutor
import gs_harvest as G

BOOK = "31001747475"
caps, _ = G.capitulos(BOOK)
pagos = [c for c in (caps or []) if (c.get("price") or 0) > 0][:40]
print("pagos:", len(pagos))
G.b2_pool(8)

# A) serializa o bootstrap
_L = threading.Lock()
_orig = G.nova_conta
def _serial():
    with _L:
        return _orig()
G.nova_conta = _serial

i = 0
for nw in (2, 4, 8):
    lote = pagos[i:i + nw]
    i += len(lote)
    with ThreadPoolExecutor(max_workers=nw) as ex:
        res = list(ex.map(lambda c: G.processar(BOOK, c), lote))
    bons = sum(1 for r, e in res if r)
    erros = [e for r, e in res if not r]
    print("A) bootstrap serial workers=%d lote=%d ok=%d erros=%s"
          % (nw, len(lote), bons, erros[:2]))

# B) sem serializar, mas espacando a criacao de threads
G.nova_conta = _orig
import itertools
_seq = itertools.count()

def _processa_espacado(c):
    n = next(_seq)
    time.sleep(0.7 * n)
    return G.processar(BOOK, c)

for nw in (4, 8):
    lote = pagos[i:i + nw]
    i += len(lote)
    with ThreadPoolExecutor(max_workers=nw) as ex:
        res = list(ex.map(_processa_espacado, lote))
    bons = sum(1 for r, e in res if r)
    erros = [e for r, e in res if not r]
    print("B) espacado workers=%d lote=%d ok=%d erros=%s"
          % (nw, len(lote), bons, erros[:2]))
