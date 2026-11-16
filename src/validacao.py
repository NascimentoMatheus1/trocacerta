"""Validação do modelo de decisão: análise de sensibilidade e pontos de virada.

- Pesos: cada peso é multiplicado por (1 ± 20%) e o vetor é renormalizado
  (Triantaphyllou & Sánchez, 1997).
- Depreciação: a taxa d de TODOS os modelos é deslocada em ±10 pontos percentuais.
- Ponto de virada: varre o parâmetro numa grade e localiza o valor mais próximo
  do atual em que o veredito muda.

"Margem" = proximidade TOPSIS da melhor troca comparável − proximidade de manter.
Margem > 0 -> o TOPSIS prefere trocar. Quando o veredito vem de uma regra
(suporte acabando ou 'não atende'), pesos e d não o alteram.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd

from src.decisao import (CRITERIOS, ROTULOS, AparelhoAtual, Compra, Parametros, Resultado, avaliar,
                         normalizar_pesos)


# ------------------------------------------------------------------ auxiliares
def margem(r: Resultado) -> float:
    t = r.tabela
    manter = t.loc[t["tipo"] == "manter", "proximidade"].iloc[0]
    return float(t.loc[t["tipo"] != "manter", "proximidade"].iloc[0] - manter)


def resumo(r: Resultado) -> dict:
    return {"veredito": r.veredito, "recomendado": r.recomendado, "primeiro": r.tabela.index[0],
            "margem": round(margem(r), 4), "saldo": r.indicadores["saldo_horizonte"],
            "regra": r.regra_aplicada}


def pesos_com_fator(pesos: dict, criterio: str, fator: float) -> dict:
    w = normalizar_pesos(pesos)
    w[criterio] *= fator
    return normalizar_pesos(w)


def pesos_com_parcela(pesos: dict, criterio: str, parcela: float) -> dict:
    """Define a parcela do critério (0-1) e redistribui o restante na proporção atual."""
    w = normalizar_pesos(pesos)
    resto = 1 - w[criterio]
    outros = [c for c in CRITERIOS if c != criterio]
    novo = {c: ((w[c] / resto) if resto > 0 else 1 / len(outros)) * (1 - parcela) for c in outros}
    novo[criterio] = parcela
    return novo


def cat_com_delta_d(cat: pd.DataFrame, delta: float) -> pd.DataFrame:
    c = cat.copy()
    c["taxa_depreciacao"] = (c["taxa_depreciacao"] + delta).clip(0, 0.95)
    return c


def _avaliar(atual, compra, pesos, h, cat, p, hoje):
    return avaliar(atual, compra, pesos, h, cat, p, hoje, ranking_completo=False)


# ------------------------------------------------------------------ sensibilidade
def sensibilidade(atual: AparelhoAtual, compra: Compra, pesos: dict, h: int, cat: pd.DataFrame,
                  p: Parametros, hoje: date, delta_peso: float = 0.20, delta_d: float = 0.10) -> dict:
    base = resumo(_avaliar(atual, compra, pesos, h, cat, p, hoje))
    w = normalizar_pesos(pesos)

    linhas = []
    for c in CRITERIOS:
        if w[c] == 0:
            linhas.append({"parametro": ROTULOS[c], "variacao": "peso 0 (sem efeito)", "peso_novo": 0.0,
                           **{k: base[k] for k in ("veredito", "primeiro", "margem", "saldo")},
                           "mantem_veredito": True, "mantem_primeiro": True})
            continue
        for sinal in (-1, 1):
            w2 = pesos_com_fator(w, c, 1 + sinal * delta_peso)
            r = resumo(_avaliar(atual, compra, w2, h, cat, p, hoje))
            linhas.append({"parametro": ROTULOS[c], "variacao": f"{sinal * delta_peso:+.0%}",
                           "peso_novo": round(w2[c], 4), **{k: r[k] for k in ("veredito", "primeiro", "margem", "saldo")},
                           "mantem_veredito": r["veredito"] == base["veredito"],
                           "mantem_primeiro": r["primeiro"] == base["primeiro"]})
    tab_pesos = pd.DataFrame(linhas)

    linhas = []
    for sinal in (-1, 1):
        delta = sinal * delta_d
        r = resumo(_avaliar(atual, compra, w, h, cat_com_delta_d(cat, delta), p, hoje))
        linhas.append({"parametro": "Taxa de depreciação d (todos os modelos)",
                       "variacao": f"{delta * 100:+.0f} p.p.",
                       **{k: r[k] for k in ("veredito", "primeiro", "margem", "saldo")},
                       "mantem_veredito": r["veredito"] == base["veredito"],
                       "mantem_primeiro": r["primeiro"] == base["primeiro"]})
    tab_d = pd.DataFrame(linhas)

    estavel = bool(tab_pesos["mantem_veredito"].all() and tab_d["mantem_veredito"].all())
    return {"base": base, "pesos": tab_pesos, "depreciacao": tab_d, "veredito_estavel": estavel,
            "pct_cenarios_mesmo_veredito": round(float(pd.concat([tab_pesos, tab_d])["mantem_veredito"].mean()), 4),
            "pct_cenarios_mesmo_primeiro": round(float(pd.concat([tab_pesos, tab_d])["mantem_primeiro"].mean()), 4)}


# ------------------------------------------------------------------ curvas e pontos de virada
def curva(atual: AparelhoAtual, compra: Compra, pesos: dict, h: int, cat: pd.DataFrame, p: Parametros,
          hoje: date, parametro: str, passos: int = 41) -> pd.DataFrame:
    """Varre um parâmetro e devolve veredito e margem em cada ponto.

    parametro: nome de critério (varre a parcela do peso de 0 a 95%),
               'd' (desloca d de −30 a +50 p.p.) ou 'preco' (30% a 200% do preço informado).
    """
    w = normalizar_pesos(pesos)
    linhas = []
    if parametro in CRITERIOS:
        for s in np.linspace(0, 0.95, passos):
            r = _avaliar(atual, compra, pesos_com_parcela(w, parametro, s), h, cat, p, hoje)
            linhas.append({"valor": round(float(s), 4), **resumo(r)})
    elif parametro == "d":
        for dlt in np.linspace(-0.30, 0.50, passos):
            r = _avaliar(atual, compra, w, h, cat_com_delta_d(cat, dlt), p, hoje)
            linhas.append({"valor": round(float(dlt), 4), **resumo(r)})
    elif parametro == "preco":
        for f in np.linspace(0.3, 2.0, passos):
            c2 = replace(compra, preco=compra.preco * f,
                         valor_parcela=compra.valor_parcela * f if compra.parcelado else compra.valor_parcela)
            r = _avaliar(atual, c2, w, h, cat, p, hoje)
            linhas.append({"valor": round(float(compra.preco * f), 2), **resumo(r)})
    else:
        raise ValueError(f"Parâmetro desconhecido: {parametro}")
    return pd.DataFrame(linhas)


def ponto_virada(cv: pd.DataFrame, valor_atual: float, veredito_base: str) -> dict | None:
    """Fronteira mais próxima do valor atual em que o veredito deixa de ser o base.

    Retorna o ponto médio entre o último valor com o veredito base e o primeiro
    com outro veredito (precisão = metade do passo da grade)."""
    v = cv["valor"].to_numpy()
    mesmo = (cv["veredito"] == veredito_base).to_numpy()
    candidatos = []
    for i in range(len(v) - 1):
        if mesmo[i] != mesmo[i + 1]:
            fronteira = (v[i] + v[i + 1]) / 2
            novo = cv["veredito"].iloc[i + 1] if mesmo[i] else cv["veredito"].iloc[i]
            candidatos.append((abs(fronteira - valor_atual), fronteira, novo))
    if not candidatos:
        return None
    _, fronteira, novo = min(candidatos)
    return {"valor_virada": float(fronteira), "novo_veredito": novo,
            "direcao": "aumentar" if fronteira > valor_atual else "reduzir"}


def pontos_virada(atual: AparelhoAtual, compra: Compra, pesos: dict, h: int, cat: pd.DataFrame,
                  p: Parametros, hoje: date, passos: int = 41) -> pd.DataFrame:
    w = normalizar_pesos(pesos)
    base = resumo(_avaliar(atual, compra, w, h, cat, p, hoje))
    linhas = []
    alvos = [(c, ROTULOS[c] + " (parcela do peso)", w[c]) for c in CRITERIOS] + \
            [("d", "Taxa de depreciação d (deslocamento)", 0.0), ("preco", "Preço do pretendido (R$)", compra.preco)]
    for chave, nome, atual_v in alvos:
        pv = None if base["regra"] else ponto_virada(curva(atual, compra, w, h, cat, p, hoje, chave, passos),
                                                     atual_v, base["veredito"])
        linhas.append({"parametro": nome, "chave": chave, "valor_atual": atual_v,
                       "valor_virada": None if pv is None else pv["valor_virada"],
                       "direcao": None if pv is None else pv["direcao"],
                       "novo_veredito": None if pv is None else pv["novo_veredito"],
                       "observacao": ("veredito definido por regra" if base["regra"] else
                                      "" if pv else "não vira na faixa testada")})
    return pd.DataFrame(linhas)
