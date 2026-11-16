"""Fase 2 — executa as 4 funções analíticas e atualiza o catálogo.

Ordem do pipeline completo:
  1. python scripts/gerar_catalogo.py   (specs + dados manuais/ML)
  2. python scripts/gerar_analitica.py  (notas, clusters, depreciação, satisfação)

Saídas:
  data/catalogo_br.csv                  (colunas analíticas preenchidas)
  data/processed/metricas.json          (métricas das 4 funções)
  data/processed/satisfacao_marca.csv
  data/processed/estatisticas_marca.csv, estatisticas_segmento.csv
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from src import analitica as an  # noqa: E402
from src.dados import (  # noqa: E402
    ARQ_AMAZON, ARQ_CATALOGO, ARQ_USADOS, PROCESSED, normalizar_marca,
)


def main(pular_classificador: bool = False) -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    cat = pd.read_csv(ARQ_CATALOGO)
    metricas = {"gerado_em": datetime.now().isoformat(timespec="seconds")}

    t = time.time()
    cat, metricas["sumarizacao"] = an.sumarizar(cat)
    cat, metricas["agrupamento"] = an.agrupar(cat)
    print(f"[1-2] sumarização + agrupamento: k={metricas['agrupamento']['k_escolhido']} ({time.time()-t:.1f}s)")

    t = time.time()
    cat, metricas["regressao"] = an.depreciacao(pd.read_csv(ARQ_USADOS), cat)
    print(f"[3] regressão: {metricas['regressao']['modelo_escolhido']} ({time.time()-t:.1f}s)")

    # 4. Classificação -> satisfação por marca; prioridade: avaliação por modelo > marca
    arq_sat = PROCESSED / "satisfacao_marca.csv"
    if pular_classificador and arq_sat.exists():
        sat = pd.read_csv(arq_sat)
        antigo = json.loads((PROCESSED / "metricas.json").read_text(encoding="utf-8"))
        metricas["classificacao"] = antigo.get("classificacao")
    else:
        t = time.time()
        az = pd.read_csv(ARQ_AMAZON, usecols=["Brand Name", "Rating", "Reviews"])
        az["marca_norm"] = az["Brand Name"].map(normalizar_marca)
        sat, metricas["classificacao"] = an.satisfacao(az)
        sat.to_csv(arq_sat, index=False)
        print(f"[4] classificação: acc={metricas['classificacao']['acuracia']} ({time.time()-t:.1f}s)")

    sat_marca = sat.set_index("marca_norm")["satisfacao"]
    cat["satisfacao"] = pd.NA
    cat["fonte_satisfacao"] = pd.NA
    por_marca = cat["marca"].str.lower().map(sat_marca)
    cat.loc[por_marca.notna(), "satisfacao"] = por_marca
    cat.loc[por_marca.notna(), "fonte_satisfacao"] = "classificador (reviews Amazon, por marca)"
    aval = pd.to_numeric(cat["avaliacao_media"], errors="coerce")
    cat.loc[aval.notna(), "satisfacao"] = (aval * 2).round(2)          # 0-5 -> 0-10
    cat.loc[aval.notna(), "fonte_satisfacao"] = "avaliação média do modelo (" + \
        cat.loc[aval.notna(), "fonte_avaliacao"].fillna("manual").astype(str) + ")"
    metricas["satisfacao_catalogo"] = {
        "modelos_por_fonte": cat["fonte_satisfacao"].fillna("PENDENTE").value_counts().to_dict(),
        "marcas_sem_dado": sorted(cat.loc[cat["satisfacao"].isna(), "marca"].unique().tolist()),
    }

    cat.to_csv(ARQ_CATALOGO, index=False, encoding="utf-8")
    pd.DataFrame(metricas["sumarizacao"]["por_marca"]).to_csv(PROCESSED / "estatisticas_marca.csv", index=False)
    pd.DataFrame(metricas["agrupamento"]["por_cluster"]).to_csv(PROCESSED / "estatisticas_segmento.csv", index=False)
    with open(PROCESSED / "metricas.json", "w", encoding="utf-8") as f:
        json.dump(metricas, f, ensure_ascii=False, indent=2, default=str)
    print("Catálogo e métricas atualizados.")


if __name__ == "__main__":
    main(pular_classificador="--pular-classificador" in sys.argv)
