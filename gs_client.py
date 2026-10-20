# -*- coding: utf-8 -*-
"""gs_client.py - cliente da API do GoodShort com assinatura RSA propria.

Usa o conjunto COMPLETO de cabecalhos capturado do app (41 headers) e assina
com chave_sign.pem.  Descoberta: o servidor exige todos esses cabecalhos.
"""
import base64
import gzip
import hashlib
import io
import json
import os
import re
import time
import urllib.error
import urllib.request
import zipfile

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

B = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(B, "gs_cap.log")
KEY = os.path.join(B, "chave_sign.pem")
APK = os.path.join(B, "gs.apk")
PREFS = os.path.join(B, "gsnow.xml")
HDRS = os.path.join(B, "gs_vip_headers.json")

BASE = os.environ.get("GS_API", "https://api-akm.goodreels.com")
RPS = float(os.environ.get("GS_RPS", "6"))


class WafBlock(Exception):
    """Akamai recusou a requisicao (WAF)."""
     # requisicoes por segundo (global)
_RATE_LOCK = None
_ULTIMO = [0.0]
PKG = "com.newreading.goodreels"
CM_FIXO = "919326DD9A742D064502468E1BF11144"


# ---------- cabecalhos modelo, vindos de uma requisicao real ----------
def template_headers():
    env = os.environ.get("VIP_HEADERS")
    if env:
        return json.loads(env)
    if not os.path.exists(LOG):
        return json.load(open(HDRS, encoding="utf-8"))
    linhas = open(LOG, encoding="utf-8", errors="replace").read().splitlines()
    h = {}
    dentro = False
    for ln in linhas:
        if re.match(r"^\d\d:\d\d:\d\d REQ POST https://api-akm", ln):
            dentro = True
            continue
        if dentro:
            m = re.match(r"^   H ([^:]+): (.*)$", ln)
            if m:
                h[m.group(1).strip()] = m.group(2)
                continue
            if ln.startswith("============") or re.match(r"^\d\d:\d\d:\d\d ", ln):
                break
    return h or json.load(open(HDRS, encoding="utf-8"))


def cert_md5():
    if not os.path.exists(APK):
        return CM_FIXO
    from cryptography.hazmat.primitives.serialization import pkcs7, Encoding
    z = zipfile.ZipFile(APK)
    for n in z.namelist():
        if n.upper().startswith("META-INF/") and n.upper().endswith(".RSA"):
            certs = pkcs7.load_der_pkcs7_certificates(z.read(n))
            der = certs[0].public_bytes(Encoding.DER)
            return hashlib.md5(der).hexdigest().upper()
    return CM_FIXO


def chave():
    env = os.environ.get("SIGN_KEY")
    if env:
        return serialization.load_pem_private_key(env.encode(), password=None)
    return serialization.load_pem_private_key(open(KEY, "rb").read(), password=None)


_T = None
_CM = None
_K = None


def chamar(rota, corpo=None, extra=None, debug=False, host=None):
    global _T, _CM, _K
    if _T is None:
        _T = template_headers()
        _CM = cert_md5()
        _K = chave()
    h = dict(_T)
    if extra:
        h.update(extra)

    corpo_txt = json.dumps(corpo, separators=(",", ":")) if corpo is not None else ""
    ts = str(int(time.time() * 1000))
    src = ("timestamp=" + ts + corpo_txt + h.get("deviceid", "") +
           h.get("androidid", "") + h.get("authorization", "") + _CM + PKG)
    sig = base64.b64encode(_K.sign(src.encode("utf-8"), padding.PKCS1v15(),
                                   hashes.SHA256())).decode()
    h["timestamp"] = ts
    h["sign"] = sig
    h["Content-Type"] = "application/json; charset=utf-8"
    h.pop("content-length", None)
    h.pop("Content-Length", None)
    h.pop("accept-encoding", None)
    h.pop("Accept-Encoding", None)
    if extra:
        h.update(extra)

    # ------- limitador global de taxa (evita o WAF) -------
    global _RATE_LOCK
    if _RATE_LOCK is None:
        import threading
        _RATE_LOCK = threading.Lock()
    with _RATE_LOCK:
        intervalo = 1.0 / max(RPS, 0.1)
        espera = _ULTIMO[0] + intervalo - time.time()
        if espera > 0:
            time.sleep(espera)
        _ULTIMO[0] = time.time()

    url = (host or BASE) + "/" + rota.lstrip("/") + "?timestamp=" + ts
    dados = corpo_txt.encode() if corpo_txt else None
    st, raw, enc = 0, b"", ""
    for tent in range(4):
        req = urllib.request.Request(url, data=dados, headers=h, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                st, raw, enc = r.status, r.read(), r.headers.get("Content-Encoding", "")
            break
        except urllib.error.HTTPError as e:
            st, raw, enc = e.code, e.read(), e.headers.get("Content-Encoding", "")
            break
        except Exception:
            time.sleep(1.5 * (tent + 1))
            if tent == 3:
                raise
    if enc == "gzip" or raw[:2] == b"\x1f\x8b":
        try:
            raw = gzip.decompress(raw)
        except Exception:
            pass
    txt = raw.decode("utf-8", "replace")
    if "Access Denied" in txt:
        raise WafBlock("Access Denied")
    if debug:
        print("%s -> %s (%d bytes)" % (rota, st, len(raw)))
        print(txt[:400])
    return st, txt


if __name__ == "__main__":
    import sys
    rota = sys.argv[1] if len(sys.argv) > 1 else "hwycclientreels/app/health"
    corpo = json.loads(sys.argv[2]) if len(sys.argv) > 2 else None
    st, txt = chamar(rota, corpo, debug=True)
    try:
        d = json.loads(txt)
        print("\nstatus:", d.get("status"), "success:", d.get("success"),
              "message:", d.get("message"))
    except Exception:
        pass
