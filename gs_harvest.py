# -*- coding: utf-8 -*-
"""gs_harvest.py - harvest GoodShort: URLs VIP -> mp4 -> B2.

Uso:
  python gs_harvest.py --ids gs_pt_ids.json --workers 4 [--limit N] [--book ID]

Layout no B2 (bucket dramio-videos):
  _videos/goodshort/<bookId>/<NNN>_<chapterId>.mp4
  _dados/goodshort/<bookId>.json
  _dados/goodshort/_progresso.jsonl
"""
import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor

import gs_client as C

B = os.path.dirname(os.path.abspath(__file__))
TMP = os.path.join(B, "gs_tmp")
os.makedirs(TMP, exist_ok=True)

URLRE = re.compile(r"https://[^\s\"\\]+\.m3u8[^\s\"\\]*")
BASE = json.loads(os.environ["VIP_HEADERS"]) if os.environ.get("VIP_HEADERS") \
    else json.load(open(os.path.join(B, "gs_vip_headers.json"), encoding="utf-8"))

# ---------------- contas convidadas (sem VIP) ----------------
# Cada conta nova desbloqueia 8 capitulos pagos; trocar o afid evita o bloqueio
# por instalacao. Os hosts de backup nao estao atras do Akamai que barra
# datacenter, entao os runners do GitHub conseguem falar com a API.
HOSTES = [x for x in os.environ.get(
    "GS_HOSTS",
    "https://api2.good-short.com,https://api.goodreels.com,https://api.good-short.com"
).split(",") if x.strip()]
COTA = int(os.environ.get("GS_COTA", "8"))
ESPERA3015 = float(os.environ.get("GS_ESPERA_3015", "600"))
_rc = {"contas": 0, "host": 0, "lock": threading.Lock()}
_rcl = threading.local()
# freio global: quando o IP entra em 3015, todos os workers pausam juntos
_pausa = {"ate": 0.0, "vezes": 0}


def pausado():
    """Dorme enquanto o freio global estiver ativo."""
    while True:
        with _rc["lock"]:
            falta = _pausa["ate"] - time.time()
        if falta <= 0:
            return
        time.sleep(min(falta, 30))


def freiou():
    with _rc["lock"]:
        if _pausa["ate"] <= time.time():
            _pausa["vezes"] += 1
        _pausa["ate"] = time.time() + ESPERA3015


def _afid_novo():
    import random
    return "%d-%d" % (random.randint(1792000000000, 1792999999999),
                      random.randint(2000000000000000000, 2999999999999999999))


def nova_conta():
    """Cria conta convidada com fingerprint novo e escolhe um host."""
    with _rc["lock"]:
        host = HOSTES[_rc["host"] % len(HOSTES)]
        _rc["host"] += 1
    H = dict(BASE)
    H.update({"deviceid": str(uuid.uuid4()), "androidid": "%016x" % uuid.uuid4().int,
              "authorization": "", "afid": _afid_novo()})
    for tent in range(4):
        try:
            st, r = C.chamar("hwycclientreels/app/bootstrap", {}, extra=H, host=host)
            u = (json.loads(r).get("data") or {}).get("user") or {}
            tok = u.get("token") or ""
            if tok:
                if not tok.startswith("Bearer "):
                    tok = "Bearer " + tok
                H["authorization"] = tok
                with _rc["lock"]:
                    _rc["contas"] += 1
                _rcl.usados = 0
                return H, host
        except Exception:
            time.sleep(1.5 * (tent + 1))
    return None, host


def conta():
    """Headers+host da conta do thread, renovando a cada COTA desbloqueios."""
    if getattr(_rcl, "H", None) is None or getattr(_rcl, "usados", 0) >= COTA:
        H, host = nova_conta()
        if H is None:
            return None, None
        _rcl.H, _rcl.host = H, host
    return _rcl.H, _rcl.host


def queimou():
    _rcl.usados = getattr(_rcl, "usados", 0) + 1


def troca_conta():
    _rcl.usados = COTA


# ---------------- B2 ----------------
KID = os.environ.get("B2_KID", "0058801f4ba47340000000001")
AK = os.environ.get("B2_AK", "K005v5qF3JSb5Gn29Vl7udyDxsGNqrA")
BUCKET = os.environ.get("B2_BUCKET", "dramio-videos")

import queue

_lock = threading.Lock()
_b2 = {"api": None, "tok": None, "bid": None}
_pool = queue.Queue()


def b2_auth():
    basic = base64.b64encode(f"{KID}:{AK}".encode()).decode()
    req = urllib.request.Request(
        "https://api.backblazeb2.com/b2api/v2/b2_authorize_account",
        headers={"Authorization": "Basic " + basic})
    with urllib.request.urlopen(req, timeout=60) as r:
        a = json.loads(r.read())
    api, tok, conta = a["apiUrl"], a["authorizationToken"], a["accountId"]
    req = urllib.request.Request(
        api + "/b2api/v2/b2_list_buckets",
        data=json.dumps({"accountId": conta, "bucketName": BUCKET}).encode(),
        headers={"Authorization": tok, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read())
    _b2.update(api=api, tok=tok, bid=d["buckets"][0]["bucketId"])


def b2_nova_url():
    with _lock:
        if _b2["api"] is None:
            b2_auth()
        api, tok, bid = _b2["api"], _b2["tok"], _b2["bid"]
    req = urllib.request.Request(
        api + "/b2api/v2/b2_get_upload_url",
        data=json.dumps({"bucketId": bid}).encode(),
        headers={"Authorization": tok, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def b2_pool(n):
    for _ in range(n):
        _pool.put(b2_nova_url())


def b2_listar(prefixo):
    """Lista todos os nomes de arquivo sob um prefixo do bucket."""
    with _lock:
        if _b2["api"] is None:
            b2_auth()
        api, tok, bid = _b2["api"], _b2["tok"], _b2["bid"]
    nomes = []
    inicio = None
    while True:
        corpo = {"bucketId": bid, "prefix": prefixo, "maxFileCount": 1000}
        if inicio:
            corpo["startFileName"] = inicio
        req = urllib.request.Request(
            api + "/b2api/v2/b2_list_file_names",
            data=json.dumps(corpo).encode(),
            headers={"Authorization": tok, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read())
        for f in d.get("files", []):
            nomes.append(f["fileName"])
        inicio = d.get("nextFileName")
        if not inicio:
            break
    return nomes


def b2_upload(caminho, key):
    dados = open(caminho, "rb").read()
    sha1 = hashlib.sha1(dados).hexdigest()
    for tent in range(5):
        try:
            u = _pool.get(timeout=300)
        except queue.Empty:
            raise RuntimeError("sem upload url livre")
        soltar = True
        try:
            h = {
                "Authorization": u["authorizationToken"],
                "X-Bz-File-Name": urllib.parse.quote(key),
                "Content-Type": "video/mp4" if key.endswith(".mp4") else "application/json",
                "Content-Length": str(len(dados)),
                "X-Bz-Content-Sha1": sha1,
            }
            req = urllib.request.Request(u["uploadUrl"], data=dados, headers=h)
            with urllib.request.urlopen(req, timeout=600) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            corpo = e.read().decode("utf-8", "replace")
            if e.code == 401 or "expired_auth_token" in corpo or "auth_token_limit" in corpo:
                soltar = False
                _pool.put(b2_nova_url())
                time.sleep(0.5)
                continue
            raise RuntimeError("B2 %s: %s" % (e.code, corpo[:120]))
        except Exception:
            time.sleep(1 + tent)
        finally:
            if soltar:
                _pool.put(u)
    raise RuntimeError("upload falhou: " + key)


# ---------------- download ----------------
def melhor_url(urls):
    for u in urls:
        if "720p" in u and "v3-akm" in u:
            return u
    for u in urls:
        if "720p" in u:
            return u
    for u in urls:
        if "v3-akm" in u:
            return u
    return urls[0] if urls else None


def baixar(url, saida):
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-protocol_whitelist", "file,http,https,tcp,tls,crypto",
           "-user_agent", "okhttp/4.10.0",
           "-i", url, "-c", "copy", "-bsf:a", "aac_adtstoasc", saida]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0 or not os.path.exists(saida) or os.path.getsize(saida) < 10000:
        # fallback: remux sem o bsf
        cmd2 = ["ffmpeg", "-y", "-loglevel", "error",
                "-protocol_whitelist", "file,http,https,tcp,tls,crypto",
                "-user_agent", "okhttp/4.10.0",
                "-i", url, "-c", "copy", saida]
        subprocess.run(cmd2, capture_output=True, text=True)
    if not os.path.exists(saida):
        raise RuntimeError("ffmpeg falhou: " + (p.stderr or "")[:200])
    return os.path.getsize(saida)


# ---------------- capitulos ----------------
def capitulos(book):
    Hc, host = conta()
    st, r = C.chamar("hwycclientreels/chapter/list", {"bookId": book},
                     extra=Hc or BASE, host=host)
    try:
        d = json.loads(r)
    except Exception:
        return None, r
    if d.get("status") != 0:
        return None, d.get("message")
    return (d.get("data") or {}).get("list") or [], None


def urls_do_capitulo(book, cap):
    # viewAd:true -> o servidor entrega a URL assinada de capitulo pago
    # (funciona ate em conta convidada, sem VIP e sem anuncio)
    for tent in range(10):
        pausado()
        Hc, host = conta()
        if Hc is None:
            return []
        try:
            st, r = C.chamar("hwycclientreels/chapter/load",
                             {"bookId": book, "chapterIds": [cap["id"]], "viewAd": True},
                             extra=Hc, host=host)
        except Exception:
            time.sleep(1.5 * (tent + 1))
            continue
        try:
            d = json.loads(r)
        except Exception:
            return []
        if d.get("status") == 3015:
            # throttle por IP: nao adianta trocar de conta; trava o job inteiro
            freiou()
            print("3015: pausa global de %.0fs (cap %s)" % (ESPERA3015, cap["id"]), flush=True)
            continue
        if d.get("status") != 0:
            troca_conta()
            continue
        it = ((d.get("data") or {}).get("list") or [{}])[0]
        urls = [x.get("videoPath") for x in (it.get("cdnList") or []) if x.get("videoPath")]
        if urls:
            queimou()
            return urls
        troca_conta()          # conta sem cota: pega outra e tenta de novo
    return []


def meta_e_capa(book, caps):
    """Metadados completos (book/quick/open) + capa -> B2."""
    Hc, host = conta()
    try:
        st, r = C.chamar("hwycclientreels/book/quick/open", {"bookId": book},
                         extra=Hc or BASE, host=host)
        d = json.loads(r)
        livro = (d.get("data") or {}).get("book") or {}
    except Exception:
        livro = {}
    meta = {"bookId": book, "book": livro, "chapters": caps}
    mp = os.path.join(TMP, "meta_%s.json" % book)
    json.dump(meta, open(mp, "w", encoding="utf-8"), ensure_ascii=False)
    b2_upload(mp, "_dados/goodshort/%s.json" % book)
    os.remove(mp)

    capa = (livro.get("bookDetailCover") or livro.get("cover")
            or livro.get("image") or "")
    if capa:
        try:
            req = urllib.request.Request(capa, headers={"User-Agent": "okhttp/4.10.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                dados = resp.read()
            cp = os.path.join(TMP, "capa_%s.jpg" % book)
            open(cp, "wb").write(dados)
            b2_upload(cp, "_capas/goodshort/%s.jpg" % book)
            os.remove(cp)
        except Exception:
            pass
    return livro.get("bookName") or livro.get("name") or ""


def processar(book, cap):
    urls = urls_do_capitulo(book, cap)
    if not urls:
        return None, "sem URL"
    url = melhor_url(urls)
    idx = cap.get("index")
    cid = cap.get("id")
    nome = "%03d_%s.mp4" % (idx, cid)
    local = os.path.join(TMP, nome)
    tam = baixar(url, local)
    key = "_videos/goodshort/%s/%s" % (book, nome)
    b2_upload(local, key)
    try:
        os.remove(local)
    except Exception:
        pass
    return {"book": book, "index": idx, "chapterId": cid, "key": key,
            "size": tam, "price": cap.get("price"), "playTime": cap.get("playTime"),
            "name": cap.get("chapterName")}, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default=os.path.join(B, "gs_pt_ids.json"))
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--book", default="")
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--of", type=int, default=1)
    args = ap.parse_args()

    prog = os.path.join(B, "gs_progresso.jsonl")
    done = set()
    if os.path.exists(prog):
        for ln in open(prog, encoding="utf-8"):
            try:
                done.add(json.loads(ln)["book"] + ":" + str(json.loads(ln)["chapterId"]))
            except Exception:
                pass
    print("já feitos (progresso local):", len(done), flush=True)

    # pula o que ja esta no B2 (permite rodar varios runners com sobreposicao)
    if not os.environ.get("GS_IGNORA_B2"):
        try:
            chaves = b2_listar("_videos/goodshort/")
            for k in chaves:
                p = k.split("/")
                if len(p) >= 4:
                    cid = p[3].rsplit("_", 1)[-1]
                    if cid.endswith(".mp4"):
                        cid = cid[:-4]
                    done.add(p[2] + ":" + cid)
            print("no B2:", len(chaves), "-> pular:", len(done), flush=True)
        except Exception as e:
            print("aviso: nao listei o B2:", repr(e)[:80], flush=True)

    ids = ([args.book] if args.book else json.load(open(args.ids, encoding="utf-8")))
    # aceita lista de ids ou lista de objetos (gs_prioridade.json)
    ids = [(x.get("gs_bookId") or x.get("book")) if isinstance(x, dict) else x for x in ids]
    ids = [str(x) for x in ids if x]
    if args.of > 1:
        ids = [x for i, x in enumerate(ids) if i % args.of == args.shard]
    if args.limit:
        ids = ids[:args.limit]
    print("livros:", len(ids), " workers:", args.workers, flush=True)

    t0 = time.time()
    total = 0
    bytes_total = 0
    falhas = 0

    b2_pool(args.workers + 2)
    print("B2 pronto (%d upload urls)" % (args.workers + 2), flush=True)

    for bi, book in enumerate(ids, 1):
        try:
            caps, err = capitulos(book)
        except Exception as e:
            print("[%d/%d] %s ERRO: %r" % (bi, len(ids), book, e), flush=True)
            continue
        if caps is None:
            print("[%d/%d] %s SEM CAPITULOS: %s" % (bi, len(ids), book, err), flush=True)
            continue
        caps = sorted(caps, key=lambda c: c.get("index", 0))
        try:
            nome_livro = meta_e_capa(book, caps)
        except Exception as e:
            nome_livro = ""
            print("   meta falhou: %r" % e, flush=True)

        pend = [c for c in caps if book + ":" + str(c.get("id")) not in done]
        print("[%d/%d] livro %s: %d caps (%d pendentes)" % (
            bi, len(ids), book, len(caps), len(pend)), flush=True)
        if not pend:
            continue

        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(processar, book, c): c for c in pend}
            for f in futs:
                try:
                    res, erro = f.result()
                except Exception as e:
                    res, erro = None, repr(e)[:120]
                if res:
                    total += 1
                    bytes_total += res["size"]
                    with open(prog, "a", encoding="utf-8") as fh:
                        fh.write(json.dumps(res, ensure_ascii=False) + "\n")
                    if total % 10 == 0:
                        print("   +%d eps  %.1f MB  %.0fs" % (
                            total, bytes_total / 1048576.0, time.time() - t0), flush=True)
                else:
                    falhas += 1
                    print("   falha cap %s: %s" % (futs[f].get("index"), erro), flush=True)

    print("\nFIM: %d episodios, %.1f MB, %d falhas, %.0f min" % (
        total, bytes_total / 1048576.0, falhas, (time.time() - t0) / 60), flush=True)


if __name__ == "__main__":
    main()
