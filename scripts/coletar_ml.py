"""Coleta de preços (e, se permitido, avaliações) na API oficial do Mercado Livre.

Executado manualmente, FORA do app. O app só lê os CSVs gerados aqui.

Credenciais: variáveis de ambiente ou arquivo .env na raiz do projeto
  ML_CLIENT_ID=...
  ML_CLIENT_SECRET=...

Endpoints usados (os de busca de anúncios /sites/MLB/search e /items/{id} de
terceiros retornam 403 para apps comuns e NÃO são usados):
  POST /oauth/token                              (grant_type=client_credentials)
  GET  /products/search?q=..&site_id=MLB&status=active
  GET  /products/{id}
  GET  /products/{id}/items                      (anúncios e preços)
  GET  /reviews/item/{item_id}?catalog_product_id={id}

Saídas:
  data/precos_ml.csv          modelo, preco_brl (mediana dos anúncios NOVOS), n_anuncios,
                              produtos_ml, data_coleta, status
  data/avaliacoes_ml.csv      modelo, nota_media, n_avaliacoes, data_coleta, status
  data/processed/reviews_ml.csv   texto, estrelas e data (SEM dados de usuários)
Depois rode: python scripts/gerar_catalogo.py

Uso:
  python scripts/coletar_ml.py --testar            # testa token e endpoints com 1 modelo
  python scripts/coletar_ml.py                     # coleta todo o catálogo
  python scripts/coletar_ml.py --modelos "Poco F5" "Redmi Note 12"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import sys
import time
from datetime import date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
from rapidfuzz import fuzz  # noqa: E402

from src.dados import (  # noqa: E402
    ARQ_CATALOGO, DATA, PROCESSED, RAIZ, normalizar_nome, tokens_numericos,
)

API = "https://api.mercadolibre.com"
CACHE = DATA / "cache"
PAUSA_S = 0.6            # pausa entre chamadas reais (não cacheadas)
MAX_TENTATIVAS = 5
MAX_PRODUTOS_POR_MODELO = 3
MAX_REVIEWS_POR_ITEM = 100
LIMIAR = 85

ARQ_PRECOS_ML = DATA / "precos_ml.csv"
ARQ_AVAL_ML = DATA / "avaliacoes_ml.csv"
ARQ_REVIEWS_ML = PROCESSED / "reviews_ml.csv"


class AcessoNegado(Exception):
    """401/403: o endpoint não está liberado para este app."""


def carregar_env() -> None:
    env = RAIZ / ".env"
    if env.exists():
        for linha in env.read_text(encoding="utf-8").splitlines():
            if "=" in linha and not linha.strip().startswith("#"):
                k, v = linha.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class ClienteML:
    def __init__(self, client_id: str, client_secret: str, usar_cache: bool = True):
        self.client_id = client_id
        self.client_secret = client_secret
        self.usar_cache = usar_cache
        self.token: str | None = None
        self.sessao = requests.Session()
        self.sessao.headers["Accept"] = "application/json"
        CACHE.mkdir(parents=True, exist_ok=True)

    def autenticar(self) -> None:
        r = self.sessao.post(f"{API}/oauth/token", data={
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }, timeout=30)
        if r.status_code != 200:
            raise SystemExit(f"Falha ao obter token ({r.status_code}): {r.text[:300]}")
        self.token = r.json()["access_token"]

    def get(self, caminho: str, params: dict | None = None) -> dict | None:
        """GET com cache em disco, pausa, backoff no 429 e renovação do token.

        Retorna None para 404. Levanta AcessoNegado para 401/403 persistentes.
        """
        params = params or {}
        chave = hashlib.sha1(json.dumps([caminho, sorted(params.items())]).encode()).hexdigest()
        arq = CACHE / f"{chave}.json"
        if self.usar_cache and arq.exists():
            return json.loads(arq.read_text(encoding="utf-8"))

        espera = 2.0
        renovou = False
        for _ in range(MAX_TENTATIVAS):
            time.sleep(PAUSA_S)
            r = self.sessao.get(f"{API}{caminho}", params=params, timeout=30,
                                headers={"Authorization": f"Bearer {self.token}"})
            if r.status_code == 200:
                dados = r.json()
                arq.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
                return dados
            if r.status_code == 404:
                return None
            if r.status_code == 401 and not renovou:   # token expirado
                self.autenticar()
                renovou = True
                continue
            if r.status_code in (401, 403):
                raise AcessoNegado(f"{r.status_code} em {caminho}: {r.text[:200]}")
            if r.status_code == 429 or r.status_code >= 500:
                ra = r.headers.get("Retry-After")
                time.sleep(float(ra) if ra and ra.isdigit() else espera)
                espera *= 2
                continue
            raise RuntimeError(f"{r.status_code} em {caminho}: {r.text[:200]}")
        raise RuntimeError(f"Tentativas esgotadas em {caminho}")


def escolher_produtos(resultados: list[dict], modelo: str, armazenamento_gb: float) -> list[dict]:
    """Filtra produtos de catálogo que correspondem ao modelo (mesma regra do matching)."""
    alvo = normalizar_nome(modelo)
    num_alvo = tokens_numericos(alvo)
    cands = []
    for p in resultados:
        nome = p.get("name", "")
        dominio = p.get("domain_id")
        if dominio and dominio != "MLB-CELLPHONES":
            continue
        if re.match(r"\s*(capa|capinha|pel[ií]cula|case|carregador|cabo|fone|suporte|kit)\b", nome, re.I):
            continue
        # Nomes do ML: "<modelo> 128 GB <cor> 4 GB RAM" -> usa só o trecho do modelo
        n = normalizar_nome(re.split(r"\s\d+\s*(?:GB|TB)\b", nome, flags=re.I)[0])
        if tokens_numericos(n) != num_alvo:
            continue
        score = fuzz.token_sort_ratio(alvo, n)
        if score < LIMIAR:
            continue
        mesma_mem = bool(pd.notna(armazenamento_gb)
                         and re.search(rf"\b{int(armazenamento_gb)}\s*gb\b", nome, re.I))
        mesmo_5g = ("5g" in modelo.lower()) == bool(re.search(r"\b5g\b", nome, re.I))
        cands.append(((mesma_mem, mesmo_5g, score), p))
    # prioriza: mesmo armazenamento da versão base, mesma geração (5G), maior score
    cands.sort(key=lambda t: t[0], reverse=True)
    return [p for _, p in cands[:MAX_PRODUTOS_POR_MODELO]]


def anuncios(cli: ClienteML, produto_id: str) -> list[dict]:
    itens, offset = [], 0
    while True:
        d = cli.get(f"/products/{produto_id}/items", {"offset": offset, "limit": 50})
        if not d:
            break
        itens += d.get("results", [])
        total = d.get("paging", {}).get("total", 0)
        offset += 50
        if offset >= min(total, 200):
            break
    return itens


def reviews(cli: ClienteML, item_id: str, produto_id: str) -> tuple[dict | None, list[dict]]:
    d = cli.get(f"/reviews/item/{item_id}", {"catalog_product_id": produto_id, "limit": MAX_REVIEWS_POR_ITEM})
    if not d:
        return None, []
    resumo = {"nota_media": d.get("rating_average"), "n_avaliacoes": d.get("paging", {}).get("total")}
    # somente conteúdo, estrelas e data — nenhum identificador de usuário
    lista = [{"titulo": r.get("title"), "texto": r.get("content"), "estrelas": r.get("rate"),
              "data": r.get("date_created")} for r in d.get("reviews", [])]
    return resumo, lista


def coletar(cli: ClienteML, catalogo: pd.DataFrame, testar_reviews: bool = True):
    hoje = date.today().isoformat()
    precos, avals, revs = [], [], []
    reviews_liberadas = testar_reviews
    for _, m in catalogo.iterrows():
        modelo = m["modelo"]
        print(f"- {modelo} ...", end=" ", flush=True)
        busca = cli.get("/products/search", {"q": modelo, "site_id": "MLB", "status": "active"}) or {}
        prods = escolher_produtos(busca.get("results", []), modelo, m.get("armazenamento_gb"))
        if not prods:
            print("não encontrado")
            precos.append({"modelo": modelo, "status": "nao_encontrado_no_ml", "data_coleta": hoje})
            avals.append({"modelo": modelo, "status": "nao_encontrado_no_ml", "data_coleta": hoje})
            continue

        valores, ids, item_ref = [], [], None
        for p in prods:
            ids.append(p["id"])
            for it in anuncios(cli, p["id"]):
                if it.get("condition") == "new" and it.get("currency_id", "BRL") == "BRL" and it.get("price"):
                    valores.append(float(it["price"]))
                    item_ref = item_ref or (it.get("item_id"), p["id"])
        precos.append({
            "modelo": modelo,
            "preco_brl": round(statistics.median(valores), 2) if valores else None,
            "n_anuncios": len(valores),
            "produtos_ml": "|".join(ids),
            "data_coleta": hoje,
            "status": "ok" if valores else "sem_anuncios_novos",
        })
        print(f"{len(valores)} anúncios novos", end="")

        if reviews_liberadas and item_ref:
            try:
                resumo, lista = reviews(cli, *item_ref)
                avals.append({"modelo": modelo, **(resumo or {}), "data_coleta": hoje,
                              "status": "ok" if resumo else "sem_avaliacoes"})
                revs += [{"modelo": modelo, "produto_ml": item_ref[1], **r} for r in lista]
                print(f", {len(lista)} reviews", end="")
            except AcessoNegado as e:
                reviews_liberadas = False
                print(f"\n  !! Reviews bloqueadas ({e}). Seguindo só com preços — use o plano B "
                      "(data/avaliacoes_manuais.csv + classificador treinado na Amazon).")
        print()
    return pd.DataFrame(precos), pd.DataFrame(avals), pd.DataFrame(revs)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--testar", action="store_true", help="testa token e endpoints com um modelo")
    ap.add_argument("--modelos", nargs="*", help="coleta só estes modelos do catálogo")
    ap.add_argument("--sem-cache", action="store_true", help="ignora o cache local")
    ap.add_argument("--sem-reviews", action="store_true", help="não tenta coletar avaliações")
    args = ap.parse_args()

    carregar_env()
    cid, csec = os.environ.get("ML_CLIENT_ID"), os.environ.get("ML_CLIENT_SECRET")
    if not cid or not csec:
        raise SystemExit("Defina ML_CLIENT_ID e ML_CLIENT_SECRET no ambiente ou em .env (veja .env.example).")

    cli = ClienteML(cid, csec, usar_cache=not args.sem_cache)
    cli.autenticar()
    print("Token obtido.")

    cat = pd.read_csv(ARQ_CATALOGO)
    if args.testar:
        cat = cat[cat["modelo"] == "Samsung Galaxy A15 5G"].head(1)
    elif args.modelos:
        cat = cat[cat["modelo"].isin(args.modelos)]

    precos, avals, revs = coletar(cli, cat, testar_reviews=not args.sem_reviews)
    if args.testar:
        print("\nTeste concluído (nada foi gravado):")
        print(precos.to_string(index=False))
        print(avals.to_string(index=False) if not avals.empty else "Avaliações: nenhuma")
        return

    def mesclar(novo: pd.DataFrame, arq: Path) -> None:
        if arq.exists() and not novo.empty:
            antigo = pd.read_csv(arq)
            novo = pd.concat([antigo[~antigo["modelo"].isin(novo["modelo"])], novo], ignore_index=True)
        novo.to_csv(arq, index=False, encoding="utf-8")

    mesclar(precos, ARQ_PRECOS_ML)
    if not avals.empty:
        mesclar(avals, ARQ_AVAL_ML)
    if not revs.empty:
        PROCESSED.mkdir(parents=True, exist_ok=True)
        mesclar(revs, ARQ_REVIEWS_ML)
    print(f"\nGravado: {ARQ_PRECOS_ML.name} ({precos['preco_brl'].notna().sum()} com preço), "
          f"{ARQ_AVAL_ML.name}, {ARQ_REVIEWS_ML.name} ({len(revs)} reviews).")
    print("Próximo passo: python scripts/gerar_catalogo.py")


if __name__ == "__main__":
    main()
