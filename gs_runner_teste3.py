# -*- coding: utf-8 -*-
"""gs_runner_teste3.py - no runner: 2 fluxos SIMULTANEOS (2 contas) e 1 sequencial.

Descobre se a concorrencia no mesmo IP quebra o unlock.
"""
import json
import os
import random
import sys
import threading
import time
import uuid

B = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, B)
import gs_client as C

HOST = "https://api2.good-short.com"
C._T = None
BOOK = "31001837621"
AU, AG, CONF = "876f264e7bffc5be", 1, 305


def log(t):
    print(t, flush=True)


def conta():
    H = json.load(open(os.path.join(B, "gs_vip_headers.json"), encoding="utf-8"))
    H.update({"deviceid": str(uuid.uuid4()), "androidid": "%016x" % uuid.uuid4().int,
              "authorization": "", "afid": "%d-%d" % (
                  random.randint(1700000000000, 1800000000000),
                  random.randint(1000000000000000000, 9999999999999999999)),
              "model": "SM-G781B", "brand": "samsung"})
    st, r = C.chamar("hwycclientreels/app/bootstrap", {}, extra=H, host=HOST)
    d = json.loads(r)
    u = (d.get("data") or {}).get("user") or {}
    tok = u.get("token") or ""
    H["authorization"] = tok if tok.startswith("Bearer ") else "Bearer " + tok
    return H, u.get("uid")


def fluxo(H, cid, tag):
    t0 = time.time()
    try:
        st, r = C.chamar("hwycclientreels/ad/show/report",
                         {"bookId": BOOK, "chapterId": cid, "agentCode": AG,
                          "adUnitId": AU, "position": 0, "showType": 1,
                          "confId": CONF}, extra=H, host=HOST)
        d1 = json.loads(r).get("status")
    except Exception as e:
        d1 = "EXC"
    time.sleep(31)
    try:
        st, r = C.chamar("hwycclientreels/ad/iaa",
                         {"afid": H["afid"], "agentCode": AG, "adUnitId": AU,
                          "ecpm": 12.5, "prices": [12.5], "chapterId": cid,
                          "bookId": BOOK, "confId": CONF, "duration": 31,
                          "viewedAdNum": 1}, extra=H, host=HOST)
        d2 = json.loads(r).get("status")
    except Exception as e:
        d2 = "EXC"
    time.sleep(1)
    try:
        st, r = C.chamar("hwycclientreels/chapter/load",
                         {"bookId": BOOK, "chapterIds": [cid], "viewAd": True},
                         extra=H, host=HOST)
        d = json.loads(r)
        it = ((d.get("data") or {}).get("list") or [{}])[0]
        urls = [x.get("videoPath") for x in (it.get("cdnList") or [])
                if x.get("videoPath")]
        log("%s: [%.0fs] show=%s iaa=%s load=%s cdn=%d %s"
            % (tag, time.time() - t0, d1, d2, d.get("status"), len(urls),
               str(d.get("message"))[:20]))
        return len(urls)
    except Exception as e:
        log("%s: load EXC %r" % (tag, e))
        return 0


# capitulos pagos
st, r = C.chamar("hwycclientreels/chapter/list", {"bookId": BOOK},
                 extra=json.load(open(os.path.join(B, "gs_vip_headers.json"),
                                      encoding="utf-8")), host=HOST)
caps = (json.loads(r).get("data") or {}).get("list") or []
pagos = [c for c in sorted(caps, key=lambda x: x.get("index", 0))
         if (c.get("price") or 0) > 0]
cids = [c["id"] for c in pagos if c.get("index") > 30]
if len(cids) < 3:
    cids = [c["id"] for c in pagos[-3:]]
log("alvos: %s" % cids[:3])

log("== teste A: 2 contas SIMULTANEAS ==")
H1, u1 = conta()
H2, u2 = conta()
log("contas: %s / %s" % (u1, u2))
res = {}
t1 = threading.Thread(target=lambda: res.update(a=fluxo(H1, cids[0], "sim-A")))
t2 = threading.Thread(target=lambda: res.update(b=fluxo(H2, cids[1], "sim-B")))
t1.start()
time.sleep(1.5)
t2.start()
t1.join()
t2.join()
log("resultado simultaneo: %s" % res)

log("== teste B: 1 conta SEQUENCIAL ==")
H3, u3 = conta()
n = fluxo(H3, cids[2], "seq")
log("resultado sequencial: %d" % n)
