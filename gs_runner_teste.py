# -*- coding: utf-8 -*-
"""gs_runner_teste.py - teste rapido no runner: imprime cada passo e termina."""
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
C._T = None
BOOK = "31001837621"


def log(t):
    print(t, flush=True)


H = json.load(open(os.path.join(B, "gs_vip_headers.json"), encoding="utf-8"))
H.update({"deviceid": str(uuid.uuid4()), "androidid": "%016x" % uuid.uuid4().int,
          "authorization": "", "afid": "%d-%d" % (
              random.randint(1700000000000, 1800000000000),
              random.randint(1000000000000000000, 9999999999999999999)),
          "model": "SM-G781B", "brand": "samsung"})

log("== 1) bootstrap ==")
try:
    st, r = C.chamar("hwycclientreels/app/bootstrap", {}, extra=H, host=HOST)
    d = json.loads(r)
    u = (d.get("data") or {}).get("user") or {}
    tok = u.get("token") or ""
    log("bootstrap: status=%s uid=%s tok=%s ip=%s" % (d.get("status"), u.get("uid"),
                                                      bool(tok), d.get("ip")))
    H["authorization"] = tok if tok.startswith("Bearer ") else "Bearer " + tok
except Exception as e:
    log("bootstrap ERRO: %r" % (e,))
    sys.exit(1)

log("== 2) chapter/list ==")
try:
    st, r = C.chamar("hwycclientreels/chapter/list", {"bookId": BOOK},
                     extra=H, host=HOST)
    d = json.loads(r)
    log("list: status=%s msg=%s" % (d.get("status"), str(d.get("message"))[:30]))
    caps = (d.get("data") or {}).get("list") or []
except Exception as e:
    log("list ERRO: %r" % (e,))
    sys.exit(1)

pagos = [c for c in sorted(caps, key=lambda x: x.get("index", 0))
         if (c.get("price") or 0) > 0]
log("pagos: %d" % len(pagos))
if not pagos:
    sys.exit(0)

CID = pagos[0]["id"]
log("== 3) adconfig ==")
try:
    st, r = C.chamar("hwycclientreels/chapter/load", {"bookId": BOOK,
                                                      "chapterIds": [CID]},
                     extra=H, host=HOST)
    d = json.loads(r)
    oi = (d.get("data") or {}).get("orderInfo") or {}
    ac = oi.get("adConfResponse") or {}
    adus = (ac.get("adIdNewConfVo") or {}).get("agentAdUnitIdList") or []
    AU = adus[0]["adUnitId"] if adus else "876f264e7bffc5be"
    AG = adus[0]["agentCode"] if adus else 1
    CONF = ac.get("id") or 441
    log("adconfig: adUnlock=%s adUnit=%s agent=%s conf=%s"
        % (oi.get("adUnlock"), AU, AG, CONF))
except Exception as e:
    log("adconfig ERRO: %r" % (e,))
    sys.exit(1)

log("== 4) ad/show/report ==")
try:
    st, r = C.chamar("hwycclientreels/ad/show/report",
                     {"bookId": BOOK, "chapterId": CID, "agentCode": AG,
                      "adUnitId": AU, "position": 0, "showType": 1,
                      "confId": CONF}, extra=H, host=HOST)
    d = json.loads(r)
    log("show/report: status=%s msg=%s" % (d.get("status"),
                                           str(d.get("message"))[:30]))
except Exception as e:
    log("show/report ERRO: %r" % (e,))

log("== 5) espera 31s ==")
time.sleep(31)

log("== 6) ad/iaa ==")
try:
    st, r = C.chamar("hwycclientreels/ad/iaa",
                     {"afid": H["afid"], "agentCode": AG, "adUnitId": AU,
                      "ecpm": 12.5, "prices": [12.5], "chapterId": CID,
                      "bookId": BOOK, "confId": CONF, "duration": 31,
                      "viewedAdNum": 1}, extra=H, host=HOST)
    d = json.loads(r)
    log("iaa: status=%s msg=%s" % (d.get("status"), str(d.get("message"))[:30]))
except Exception as e:
    log("iaa ERRO: %r" % (e,))

log("== 7) chapter/load viewAd ==")
try:
    st, r = C.chamar("hwycclientreels/chapter/load",
                     {"bookId": BOOK, "chapterIds": [CID], "viewAd": True},
                     extra=H, host=HOST)
    d = json.loads(r)
    it = ((d.get("data") or {}).get("list") or [{}])[0]
    urls = [x.get("videoPath") for x in (it.get("cdnList") or [])
            if x.get("videoPath")]
    log("load: status=%s cdn=%d msg=%s" % (d.get("status"), len(urls),
                                           str(d.get("message"))[:30]))
    if urls:
        log("URL: " + urls[0][:100])
        log(">>> SUCESSO NO RUNNER <<<")
    else:
        log(">>> FALHOU NO RUNNER <<<")
except Exception as e:
    log("load ERRO: %r" % (e,))
