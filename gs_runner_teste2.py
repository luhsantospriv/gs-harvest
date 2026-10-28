# -*- coding: utf-8 -*-
"""gs_runner_teste2.py - no runner: testa B2 (auth, pool, upload, leitura)."""
import json
import os
import sys

B = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, B)

print("== imports ==", flush=True)
import gs_harvest as GH
print("gs_harvest ok | BUCKET=%s | KID=%s" % (GH.BUCKET, GH.KID[:12]), flush=True)

arq = os.path.join(B, "hb_teste.jsonl")
with open(arq, "w", encoding="utf-8") as fh:
    fh.write(json.dumps({"book": "0", "chapterId": 0, "urls": ["x"],
                         "via": "hb"}) + "\n")

print("== auth ==", flush=True)
try:
    GH.b2_auth()
    print("auth ok", flush=True)
except Exception as e:
    print("auth ERRO: %r" % (e,), flush=True)
    sys.exit(1)

print("== pool ==", flush=True)
try:
    GH.b2_pool(2)
    print("pool ok", flush=True)
except Exception as e:
    print("pool ERRO: %r" % (e,), flush=True)

print("== upload ==", flush=True)
try:
    r = GH.b2_upload(arq, "_unlock/teste_runner.jsonl")
    print("upload ok: %s" % json.dumps(r)[:120], flush=True)
except Exception as e:
    print("upload ERRO: %r" % (e,), flush=True)
