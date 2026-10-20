# -*- coding: utf-8 -*-
import json
import gs_harvest as G

G.b2_pool(2)

def testa(book, inicio, quantos):
    caps, _ = G.capitulos(book)
    pagos = [c for c in (caps or []) if (c.get("price") or 0) > 0]
    alvo = pagos[inicio:inicio + quantos]
    G.troca_conta()
    H, host = G.conta()
    n = 0
    for c in alvo:
        urls = G.urls_do_capitulo(book, c)
        if not urls:
            break
        n += 1
    print("livro %s (pagos %d) -> %d de %d | host %s" % (book, len(pagos), n, len(alvo), host))
    return n

testa("31001747475", 20, 8)   # livro do probe que funcionou
testa("31001747542", 20, 8)   # livro dos runs que falharam
testa("31001747475", 30, 8)   # outro trecho do primeiro
