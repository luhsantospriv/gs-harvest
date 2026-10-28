# -*- coding: utf-8 -*-
"""gs_unlock_runner2.py - runner: fluxo completo de anuncio, contas em loop.

Cada runner tem IP proprio (sem WAF). Cria conta -> ad/show/report ->
30s -> ad/iaa -> chapter/load. 8 unlocks por conta, depois nova conta.

uso: python gs_unlock_runner2.py --shard N --of M --workers 3
"""
import argparse
import json
import os
import random
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

B = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, B)
import gs_client as C

HOST = "https://api2.good-short.com"
SAIDA = os.path.join(B, "unlock_result.jsonl")
FILA = os.path.join(B, "gs_fila.json")
C._T = None

_lock = threading.Lock()
cont = {"novos": 0, "contas": 0, "publicado": 0}
SHARD = [0]

H0 = json.load(open(os.path.join(B, "gs_vip_headers.json"), encoding="utf-8"))

try:
    import gs_harvest as GH
    _tem_b2 = True
except Exception:
    GH = None
    _tem_b2 = False


def publica_b2():
    """sobe o resultado parcial para o B2 (visivel em tempo real)."""
    if not _tem_b2:
        return
    try:
        if GH._b2["tok"] is None:
            GH.b2_auth()
        GH.b2_upload(SAIDA, "_unlock/fluxo-%d.jsonl" % SHARD[0])
        cont["publicado"] += 1
        log("publicado no B2 (lote %d)" % cont["publicado"])
    except Exception as e:
        log("b2 erro: %s" % repr(e)[:60])


def log(t):
    print("%s %s" % (time.strftime("%H:%M:%S"), t), flush=True)


def nova_conta():
    H = dict(H0)
    H.update({"deviceid": str(uuid.uuid4()), "androidid": "%016x" % uuid.uuid4().int,
              "authorization": "", "afid": "%d-%d" % (
                  random.randint(1700000000000, 1800000000000),
                  random.randint(1000000000000000000, 9999999999999999999)),
              "model": "SM-G781B", "brand": "samsung"})
    for tent in range(4):
        try:
            st, r = C.chamar("hwycclientreels/app/bootstrap", {}, extra=H, host=HOST)
            d = json.loads(r)
            u = (d.get("data") or {}).get("user") or {}
            tok = u.get("token") or ""
            if tok:
                H["authorization"] = tok if tok.startswith("Bearer ") else "Bearer " + tok
                with _lock:
                    cont["contas"] += 1
                return H
        except Exception:
            time.sleep(3 * (tent + 1))
    return None


def adconfig(H, book, cid):
    try:
        st, r = C.chamar("hwycclientreels/chapter/load",
                         {"bookId": book, "chapterIds": [cid]}, extra=H, host=HOST)
        oi = (json.loads(r).get("data") or {}).get("orderInfo") or {}
        ac = oi.get("adConfResponse") or {}
        adus = (ac.get("adIdNewConfVo") or {}).get("agentAdUnitIdList") or []
        if adus:
            return adus[0]["adUnitId"], adus[0]["agentCode"], ac.get("id") or 441
    except Exception:
        pass
    return "876f264e7bffc5be", 1, 441


def desbloqueia(H, book, cid, au, ag, conf):
    try:
        C.chamar("hwycclientreels/ad/show/report",
                 {"bookId": book, "chapterId": cid, "agentCode": ag,
                  "adUnitId": au, "position": 0, "showType": 1, "confId": conf},
                 extra=H, host=HOST)
    except Exception:
        pass
    time.sleep(31)
    try:
        C.chamar("hwycclientreels/ad/iaa",
                 {"afid": H.get("afid", "0-0"), "agentCode": ag, "adUnitId": au,
                  "ecpm": 12.5, "prices": [12.5], "chapterId": cid,
                  "bookId": book, "confId": conf, "duration": 31,
                  "viewedAdNum": 1}, extra=H, host=HOST)
    except Exception:
        pass
    time.sleep(1)
    try:
        st, r = C.chamar("hwycclientreels/chapter/load",
                         {"bookId": book, "chapterIds": [cid], "viewAd": True},
                         extra=H, host=HOST)
        d = json.loads(r)
        it = ((d.get("data") or {}).get("list") or [{}])[0]
        urls = [x.get("videoPath") for x in (it.get("cdnList") or [])
                if x.get("videoPath")]
        return urls, d.get("status")
    except Exception:
        return [], -1


def worker(idw, fila, idx, cache):
    while True:
        with _lock:
            if idx[0] >= len(fila):
                return
            i = idx[0]
            idx[0] += 1
        item = fila[i]
        H = nova_conta()
        if not H:
            time.sleep(10)
            continue
        bk = item["book"]
        if bk not in cache:
            cache[bk] = adconfig(H, bk, item["chapterId"])
        au, ag, conf = cache[bk]

        usados = 0
        # primeiro item
        urls, stt = desbloqueia(H, bk, item["chapterId"], au, ag, conf)
        if urls:
            usados += 1
            with _lock:
                with open(SAIDA, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"book": bk, "chapterId": item["chapterId"],
                                         "index": item.get("index"), "urls": urls,
                                         "via": "adfluxo"}, ensure_ascii=False) + "\n")
                cont["novos"] += 1
        else:
            log("w%d: cap %s status=%s" % (idw, item["chapterId"], stt))

        # restante da cota
        while usados < 8:
            with _lock:
                if idx[0] >= len(fila):
                    break
                j = idx[0]
                idx[0] += 1
            it2 = fila[j]
            b2 = it2["book"]
            if b2 not in cache:
                cache[b2] = adconfig(H, b2, it2["chapterId"])
            au2, ag2, conf2 = cache[b2]
            urls, stt = desbloqueia(H, b2, it2["chapterId"], au2, ag2, conf2)
            if not urls:
                break
            usados += 1
            with _lock:
                with open(SAIDA, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"book": b2, "chapterId": it2["chapterId"],
                                         "index": it2.get("index"), "urls": urls,
                                         "via": "adfluxo"}, ensure_ascii=False) + "\n")
                cont["novos"] += 1
        log("w%d: conta feita, %d unlocks (total %d)" % (idw, usados, cont["novos"]))
        if cont["novos"] > 0 and cont["novos"] % 40 == 0:
            publica_b2()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--of", type=int, default=1)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--max-ciclos", type=int, default=40)
    args = ap.parse_args()

    fila = json.load(open(FILA, encoding="utf-8"))
    SHARD[0] = args.shard
    # shard por indice
    meu = [f for i, f in enumerate(fila) if i % args.of == args.shard]
    log("shard %d/%d: %d capitulos | %d workers" % (args.shard, args.of,
                                                     len(meu), args.workers))

    idx = [0]
    cache = {}
    ts = []
    for i in range(args.workers):
        t = threading.Thread(target=worker, args=(i, meu, idx, cache), daemon=True)
        t.start()
        ts.append(t)
        time.sleep(2)
    for t in ts:
        t.join()
    log("FIM: %d novos | %d contas" % (cont["novos"], cont["contas"]))


if __name__ == "__main__":
    main()
