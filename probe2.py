# -*- coding: utf-8 -*-
import json
import gs_harvest as G

BOOK = "31001747542"      # livro que os runners estavam pegando
caps, _ = G.capitulos(BOOK)
pagos = [c for c in (caps or []) if (c.get("price") or 0) > 0]
print("pagos:", len(pagos))
G.b2_pool(2)

# capítulos do meio do livro, nunca usados nos testes
alvo = pagos[20:60]
pos = 0
for rodada in range(1, 5):
    H, host = G.conta()
    n = 0
    for c in alvo[pos:pos + 10]:
        urls = G.urls_do_capitulo(BOOK, c)
        if not urls:
            break
        n += 1
    pos += n
    print("conta %d (uid novo) -> %d capitulos | host %s" % (rodada, n, host))
    G.troca_conta()
    if n == 0:
        break
