"""Fase 0 — matching Smartprix × Amazon e contagem de reviews por modelo casado.

Saídas:
  data/processed/matching_amazon.csv    (nome Amazon -> modelo Smartprix, score)
  data/processed/reviews_por_modelo.csv (reviews por modelo Smartprix casado)
Uso: python scripts/fase0_matching.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from src.dados import (  # noqa: E402
    PROCESSED, carregar_amazon, carregar_smartprix, casar_modelos,
    normalizar_marca, normalizar_nome,
)

MARCAS_BR = {"samsung", "motorola", "xiaomi", "apple", "realme"}

PROCESSED.mkdir(parents=True, exist_ok=True)

sp = carregar_smartprix()
alvo = sp[["name", "marca_norm", "nome_norm"]].drop_duplicates("name").rename(columns={"name": "nome"})

az = carregar_amazon(["Product Name", "Brand Name", "Rating"])
prod = (az.groupby(["Product Name", "Brand Name"], dropna=False).size()
          .rename("n_reviews").reset_index())
prod["nome"] = prod["Product Name"]
prod["marca_norm"] = prod["Brand Name"].map(normalizar_marca)
prod["nome_norm"] = prod["nome"].map(normalizar_nome)

m = casar_modelos(prod, alvo)
m = m.merge(prod[["nome", "n_reviews"]].drop_duplicates("nome"), left_on="nome_origem", right_on="nome", how="left").drop(columns="nome")
m.to_csv(PROCESSED / "matching_amazon.csv", index=False)

por_modelo = (m.groupby(["nome_alvo", "marca"])
                .agg(produtos_amazon=("nome_origem", "nunique"), n_reviews=("n_reviews", "sum"),
                     score_min=("score", "min"))
                .reset_index().sort_values("n_reviews", ascending=False))
por_modelo.to_csv(PROCESSED / "reviews_por_modelo.csv", index=False)

print(f"Produtos Amazon distintos: {len(prod)} | com marca: {prod['marca_norm'].ne('').sum()}")
print(f"Modelos Smartprix distintos: {len(alvo)}")
print(f"Produtos Amazon casados (score>=85): {len(m)} | reviews cobertas: {m['n_reviews'].sum()}")
print(f"Modelos Smartprix casados: {len(por_modelo)} | marcas BR: {por_modelo['marca'].isin(MARCAS_BR).sum()}")
print(f"Modelos casados com >=20 reviews: {(por_modelo['n_reviews'] >= 20).sum()} "
      f"| marcas BR: {((por_modelo['n_reviews'] >= 20) & por_modelo['marca'].isin(MARCAS_BR)).sum()}")
print("\nReviews por modelo casado:")
print(por_modelo.to_string(index=False))
duv = m[(m.score >= 85) & (m.score <= 92)].sort_values("n_reviews", ascending=False)
print(f"\nMatches duvidosos (85-92): {len(duv)}")
print(duv[["nome_origem", "nome_origem_norm", "nome_alvo", "score", "n_reviews"]].head(25).to_string(index=False))

# Contexto: o que a Amazon tem de marcas BR (para dimensionar o plano B por marca)
az["marca_norm"] = az["Brand Name"].map(normalizar_marca)
rot = az[az["Rating"] != 3]
print("\nReviews rotuláveis (nota != 3) por marca BR:")
print(rot[rot.marca_norm.isin(MARCAS_BR)].groupby("marca_norm").agg(
    reviews=("Rating", "size"), pct_positivas=("Rating", lambda s: round((s >= 4).mean() * 100, 1))).to_string())
