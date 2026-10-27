# -*- coding: utf-8 -*-
"""gs_unlock_runner.py - roda num runner do GitHub: desbloqueia capitulos.

Cada runner tem IP proprio (cota de viewAd independente). Cria contas
convidadas em loop e desbloqueia os capitulos do seu shard.

Resultado: unlock_result.jsonl (upload como artifact).
"""
import argparse
import json
import os
import random
import sys
import time
import uuid

B = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, B)
import gs_client as C

HOST = "https://api2.good-short.com"
FILA = os.path.join(B, "gs_fila.json")
SAIDA = os.path.join(B, "unlock_result.jsonl")
C._T = None


def afid():
    return "%d-%d" % (random.randint(1700000000000, 1800000000000),
                      random.randint(1000000000000000000, 9999999999999999999))


def conta():
    H = json.load(open(os.path.join(B, "gs_vip_headers.json"), encoding="utf-8"))
    H.update({"deviceid": str(uuid.uuid4()), "androidid": "%016x" % uuid.uuid4().int,
              "authorization": "", "afid": afid(),
              "model": "SM-G781B", "brand": "samsung"})
    for tent in range(5):
        try:
            st, r = C.chamar("hwycclientreels/app/bootstrap", {}, extra=H, host=HOST)
            d = json.loads(r)
            u = (d.get("data") or {}).get("user") or {}
            tok = u.get("token") or ""
            if tok:
                H["authorization"] = tok if tok.startswith("Bearer ") else "Bearer " + tok
                return H
        except Exception:
            time.sleep(2 * (tent + 1))
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--of", type=int, default=1)
    ap.add_argument("--max-contas", type=int, default=30)
    args = ap.parse_args()

    fila = json.load(open(FILA, encoding="utf-8"))
    meu = [f for i, f in enumerate(fila) if i % args.of == args.shard]
    print("shard %d/%d: %d capitulos" % (args.shard, args.of, len(meu)), flush=True)

    H = conta()
    if not H:
        print("sem conta inicial"); return
    usados = 0
    contas = 1
    ok = 0
    falhas_3015 = 0

    out = open(SAIDA, "a", encoding="utf-8")
    for i, item in enumerate(meu):
        book = item["book"]
        cid = item["chapterId"]
        try:
            st, r = C.chamar("hwycclientreels/chapter/load",
                             {"bookId": book, "chapterIds": [cid], "viewAd": True},
                             extra=H, host=HOST)
            d = json.loads(r)
            it = ((d.get("data") or {}).get("list") or [{}])[0]
            urls = [x.get("videoPath") for x in (it.get("cdnList") or [])
                    if x.get("videoPath")]
            if urls:
                out.write(json.dumps({"book": book, "chapterId": cid,
                                       "index": item.get("index"),
                                       "urls": urls, "via": "runner"},
                                      ensure_ascii=False) + "\n")
                out.flush()
                ok += 1
                usados += 1
                falhas_3015 = 0
            elif d.get("status") == 3015:
                falhas_3015 += 1
                if falhas_3015 >= 3:
                    # IP esgotado ou cota acabou: nova conta
                    time.sleep(5)
                    H = conta()
                    contas += 1
                    usados = 0
                    falhas_3015 = 0
                    if not H or contas > args.max_contas:
                        print("  contas esgotadas (%d)" % contas, flush=True)
                        break
                else:
                    time.sleep(2)
            else:
                time.sleep(0.5)
        except Exception as e:
            if "Waf" in type(e).__name__:
                print("  WAF! 60s", flush=True)
                time.sleep(60)
            else:
                time.sleep(2)
        if (i + 1) % 50 == 0:
            print("  %d/%d | ok=%d contas=%d" % (i + 1, len(meu), ok, contas), flush=True)
        time.sleep(0.3)

    out.close()
    print("FIM shard %d: %d unlocks | %d contas" % (args.shard, ok, contas), flush=True)


if __name__ == "__main__":
    main()
