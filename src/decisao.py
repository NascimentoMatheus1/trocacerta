"""Modelo de decisão do TrocaCerta: modelo financeiro + regras + TOPSIS.

Referências (detalhes em docs/referencias.md):
- Análise de substituição "defensor × desafiante" (manter × trocar): Blank & Tarquin,
  Engineering Economy; Bellman (1955).
- Depreciação geométrica R_t = R_0(1-d)^t: Hulten & Wykoff (1981); Fraumeni (1997).
- Queda imediata de valor na revenda (fator a): Akerlof (1970), assimetria de
  informação no mercado de usados.
- TOPSIS com normalização vetorial: Hwang & Yoon (1981); Behzadian et al. (2012).

Convenções:
- Notas de critérios de benefício em 0-10; pesos sempre normalizados para somar 1.
- Valores em R$. Saldo > 0 significa que TROCAR sai mais barato que manter.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from itertools import combinations

import numpy as np
import pandas as pd

BENEFICIO = ["camera", "processamento", "bateria", "seguranca", "armazenamento", "satisfacao"]
CUSTO = ["custo"]
CRITERIOS = BENEFICIO + CUSTO
ROTULOS = {"camera": "Câmera", "processamento": "Processamento", "bateria": "Bateria",
           "seguranca": "Segurança (suporte)", "armazenamento": "Armazenamento",
           "satisfacao": "Satisfação", "custo": "Custo líquido"}
COL_NOTA = {"camera": "nota_camera", "processamento": "nota_processamento",
            "bateria": "nota_bateria", "armazenamento": "nota_armazenamento",
            "satisfacao": "satisfacao"}

CONDICOES = ["otima", "boa", "regular", "ruim"]
ATENDE = ["nao", "parcialmente", "sim", "totalmente"]

TROCA_NECESSARIA = "Troca necessária"
VALE_TROCAR = "Vale a pena trocar"
MANTER = "Manter o atual"


# ------------------------------------------------------------------ parâmetros
@dataclass
class Parametros:
    limite_suporte_meses: int = 6
    taxa_depreciacao_fallback: float = 0.30
    fator_revenda_fallback: float = 1.0
    fatores_condicao: dict = field(default_factory=lambda: {"otima": 1.0, "boa": 0.9, "regular": 0.75, "ruim": 0.5})
    reducao_atende_parcialmente: float = 0.15
    faixa_preco: float = 0.30
    max_alternativas: int = 6

    @classmethod
    def de_dict(cls, d: dict) -> "Parametros":
        campos = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**campos)


# ------------------------------------------------------------------ pesos
def normalizar_pesos(pesos: dict) -> dict:
    """Normaliza para somar 1 (aceita escala 0-100 ou qualquer escala).

    Critérios ausentes valem 0. Se todos forem 0, usa pesos iguais.
    """
    p = {c: max(float(pesos.get(c, 0) or 0), 0.0) for c in CRITERIOS}
    total = sum(p.values())
    if total <= 0:
        return {c: 1 / len(CRITERIOS) for c in CRITERIOS}
    return {c: v / total for c, v in p.items()}


# ------------------------------------------------------------------ financeiro
def total_pago(preco: float, parcelado: bool = False, n_parcelas: int = 1, valor_parcela: float = 0.0) -> float:
    """T = preço à vista, ou n × parcela."""
    return float(n_parcelas * valor_parcela) if parcelado else float(preco)


def revenda(r0: float, d: float, h: float) -> float:
    """Depreciação geométrica: R_H = R_0 × (1 − d)^H."""
    return float(r0 * (1 - d) ** h)


def custo_manter(g: float, h: float, r_atual0: float, d_atual: float, g_anual: bool = True) -> float:
    """C_manter = G_ano × H − R_atual,H   (ou G − R_atual,H se G for gasto único)."""
    gastos = g * h if g_anual else g
    return float(gastos - revenda(r_atual0, d_atual, h))


def custo_trocar(t: float, r_atual0: float, r_novo0: float, d_novo: float, h: float) -> float:
    """C_trocar = T − R_atual,0 − R_novo,H, com R_novo,H = R_novo,0 × (1 − d)^H.

    R_novo,0 = preço à vista × a (a = fator de revenda logo após a compra,
    estimado pela regressão). Com a = 1 recupera-se a fórmula original da proposta.
    """
    return float(t - r_atual0 - revenda(r_novo0, d_novo, h))


def saldo(c_manter: float, c_trocar: float) -> float:
    """Saldo(H) = C_manter − C_trocar (positivo = trocar sai mais barato)."""
    return float(c_manter - c_trocar)


def saldo_ano_a_ano(g, r_atual0, d_atual, t, r_novo0, d_novo, anos=range(1, 6), g_anual=True) -> pd.DataFrame:
    linhas = []
    for h in anos:
        cm = custo_manter(g, h, r_atual0, d_atual, g_anual)
        ct = custo_trocar(t, r_atual0, r_novo0, d_novo, h)
        linhas.append({"ano": h, "custo_manter": round(cm, 2), "custo_trocar": round(ct, 2),
                       "revenda_atual": round(revenda(r_atual0, d_atual, h), 2),
                       "revenda_novo": round(revenda(r_novo0, d_novo, h), 2),
                       "saldo": round(saldo(cm, ct), 2)})
    return pd.DataFrame(linhas)


# ------------------------------------------------------------------ suporte
def meses_restantes(fim_suporte: str | float, hoje: date) -> float:
    """Meses entre hoje e o fim do suporte (AAAA-MM). NaN se desconhecido."""
    if not isinstance(fim_suporte, str) or len(fim_suporte) < 7:
        return float("nan")
    a, m = int(fim_suporte[:4]), int(fim_suporte[5:7])
    return float((a * 12 + m) - (hoje.year * 12 + hoje.month))


def nota_seguranca(meses: float, h: float) -> float:
    """Proporção do horizonte coberta por suporte, em 0-10:
    min(meses restantes, 12H) / (12H) × 10."""
    if np.isnan(meses):
        return float("nan")
    return float(max(min(meses, 12 * h), 0) / (12 * h) * 10)


# ------------------------------------------------------------------ TOPSIS
def topsis_passos(matriz: pd.DataFrame, pesos: dict, beneficio: list[str], custo: list[str]) -> dict:
    """TOPSIS (Hwang & Yoon, 1981) com todas as matrizes intermediárias.

    1. normalização vetorial r_ij = x_ij / sqrt(Σ_i x_ij²)
    2. ponderação v_ij = w_j × r_ij
    3. ideal positivo A+ (máx. benefício, mín. custo) e negativo A−
    4. distâncias euclidianas D+ e D−; proximidade C = D− / (D+ + D−)

    Critérios de custo com valores ≤ 0 (ex.: revenda maior que o gasto) são
    transladados para o positivo (x − mín + 1) antes da normalização, pois a
    normalização vetorial pressupõe valores positivos; a ordem é preservada.
    Colunas constantes nulas e alternativas idênticas não quebram o método
    (C = 0,5 quando D+ = D− = 0).
    """
    cols = beneficio + custo
    X = matriz[cols].astype(float).copy()
    for c in custo:
        if (X[c] <= 0).any():
            X[c] = X[c] - X[c].min() + 1.0
    norma = np.sqrt((X ** 2).sum(axis=0)).replace(0, 1.0)
    R = X / norma
    w = pd.Series({c: pesos.get(c, 0.0) for c in cols})
    V = R * w
    ideal_pos = pd.Series({c: V[c].max() if c in beneficio else V[c].min() for c in cols})
    ideal_neg = pd.Series({c: V[c].min() if c in beneficio else V[c].max() for c in cols})
    d_pos = np.sqrt(((V - ideal_pos) ** 2).sum(axis=1))
    d_neg = np.sqrt(((V - ideal_neg) ** 2).sum(axis=1))
    soma = d_pos + d_neg
    c_rel = pd.Series(np.where(soma > 0, d_neg / soma.replace(0, 1), 0.5), index=matriz.index)
    return {"X": X, "norma": norma, "R": R, "w": w, "V": V, "ideal_pos": ideal_pos, "ideal_neg": ideal_neg,
            "d_pos": d_pos, "d_neg": d_neg, "proximidade": c_rel}


def topsis(matriz: pd.DataFrame, pesos: dict, beneficio: list[str], custo: list[str]) -> pd.DataFrame:
    """Ranking TOPSIS: D+, D−, proximidade e posição (detalhes em topsis_passos)."""
    t = topsis_passos(matriz, pesos, beneficio, custo)
    out = pd.DataFrame({"d_pos": t["d_pos"], "d_neg": t["d_neg"], "proximidade": t["proximidade"]},
                       index=matriz.index)
    out["posicao"] = out["proximidade"].rank(ascending=False, method="min").astype(int)
    return out


# ------------------------------------------------------------------ entradas
@dataclass
class AparelhoAtual:
    modelo: str
    revenda_atual: float            # R_atual,0
    gasto_anual: float = 0.0        # G_ano
    condicao: str = "boa"
    saude_bateria: float = 100.0    # %
    atende: str = "sim"
    valor_pago: float | None = None
    anos_uso: float | None = None


@dataclass
class Compra:
    modelo: str
    preco: float                     # à vista
    parcelado: bool = False
    n_parcelas: int = 1
    valor_parcela: float = 0.0

    @property
    def total(self) -> float:
        return total_pago(self.preco, self.parcelado, self.n_parcelas, self.valor_parcela)


def _linha(cat: pd.DataFrame, modelo: str) -> pd.Series:
    sel = cat.loc[cat["modelo"] == modelo]
    if sel.empty:
        raise ValueError(f"Modelo não encontrado no catálogo: {modelo}")
    return sel.iloc[0]


def _taxas(linha: pd.Series, p: Parametros) -> tuple[float, float, str]:
    """(a, d, origem) do modelo; usa o fallback configurável se faltar."""
    d = linha.get("taxa_depreciacao")
    a = linha.get("fator_revenda_inicial")
    if pd.isna(d) or pd.isna(a):
        return p.fator_revenda_fallback, p.taxa_depreciacao_fallback, "taxa fixa de fallback (parâmetro do admin)"
    return float(a), float(d), "regressão (random forest, mediana do segmento)"


def notas_alternativa(linha: pd.Series, h: float, hoje: date) -> dict:
    notas = {c: float(linha[COL_NOTA[c]]) for c in COL_NOTA}
    meses = meses_restantes(linha.get("fim_suporte"), hoje)
    notas["seguranca"] = nota_seguranca(meses, h)
    notas["meses_suporte"] = meses
    return notas


def notas_atual(linha: pd.Series, atual: AparelhoAtual, h: float, hoje: date, p: Parametros) -> dict:
    """Aplica os ajustes do aparelho em uso:
    - bateria × saúde%/100
    - fator de condição sobre câmera, processamento e bateria
    - 'atende parcialmente' reduz todas as notas de benefício (e logo a adequação) em 15%
    """
    n = notas_alternativa(linha, h, hoje)
    f = p.fatores_condicao[atual.condicao]
    n["camera"] *= f
    n["processamento"] *= f
    n["bateria"] *= f * (atual.saude_bateria / 100)
    if atual.atende == "parcialmente":
        for c in BENEFICIO:
            n[c] *= 1 - p.reducao_atende_parcialmente
    return n


def adequacao(notas: dict, pesos: dict) -> float:
    """Nota de adequação 0-10: soma ponderada dos critérios de benefício
    (pesos de benefício renormalizados para somar 1)."""
    wb = {c: pesos[c] for c in BENEFICIO}
    tot = sum(wb.values()) or 1.0
    return float(sum(notas[c] * w for c, w in wb.items()) / tot)


def _n3(v: float) -> str:
    return f"{v:.3f}".replace(".", ",")


# ------------------------------------------------------------------ avaliação (consumidor)
@dataclass
class Resultado:
    veredito: str
    motivo: str
    regra_aplicada: str | None
    tabela: pd.DataFrame            # alternativas com notas, custos, TOPSIS
    recomendado: str
    saldo_anos: pd.DataFrame        # saldo ano a ano do modelo pretendido
    indicadores: dict
    origens: dict
    pesos: dict
    ranking_completo: pd.DataFrame | None = None   # manter + catálogo inteiro (só informativo)


def selecionar_alternativas(cat: pd.DataFrame, modelo_novo: str, preco_ref: float, modelo_atual: str,
                            p: Parametros) -> list[str]:
    """Pretendido + modelos do mesmo cluster e preço ±faixa (mais próximos no preço),
    até max_alternativas no total (contando 'manter')."""
    alvo = _linha(cat, modelo_novo)
    cand = cat[(cat["cluster"] == alvo["cluster"]) & (~cat["modelo"].isin([modelo_novo, modelo_atual]))
               & cat["preco_brl"].between(preco_ref * (1 - p.faixa_preco), preco_ref * (1 + p.faixa_preco))]
    cand = cand.assign(_d=(cand["preco_brl"] - preco_ref).abs()).sort_values("_d")
    return [modelo_novo] + cand["modelo"].head(p.max_alternativas - 2).tolist()


def avaliar(atual: AparelhoAtual, compra: Compra, pesos: dict, h: int, cat: pd.DataFrame,
            p: Parametros | None = None, hoje: date | None = None,
            alternativas: list[str] | None = None, ranking_completo: bool = True) -> Resultado:
    """Avalia manter × trocar.

    Decisão: TOPSIS com 'manter' + alternativas COMPARÁVEIS (pretendido + mesmo
    segmento k-means com preço ±faixa, até max_alternativas), ou a lista
    `alternativas` no modo frota. É este ranking que gera o veredito.

    Informativo: um segundo TOPSIS, independente, com 'manter' + catálogo inteiro
    (`ranking_completo`), exibido apenas no relatório completo. Como o TOPSIS
    depende do conjunto de alternativas (rank reversal), as posições dos dois
    rankings não são comparáveis entre si.
    """
    p = p or Parametros()
    hoje = hoje or date.today()
    w = normalizar_pesos(pesos)
    la = _linha(cat, atual.modelo)
    a_at, d_at, origem_d_at = _taxas(la, p)

    if alternativas:
        nomes, comparaveis = list(alternativas), set(alternativas)
    else:
        lista_comp = selecionar_alternativas(cat, compra.modelo, compra.preco, atual.modelo, p)
        comparaveis = set(lista_comp)
        if ranking_completo:
            nomes = cat.loc[(cat["modelo"] != atual.modelo) & cat["preco_brl"].notna(), "modelo"].tolist()
            if compra.modelo not in nomes:
                nomes.append(compra.modelo)
        else:
            nomes = lista_comp
    c_manter = custo_manter(atual.gasto_anual, h, atual.revenda_atual, d_at)

    linhas = []
    na = notas_atual(la, atual, h, hoje, p)
    linhas.append({"alternativa": f"Manter: {atual.modelo}", "modelo": atual.modelo, "tipo": "manter",
                   **na, "custo": c_manter, "total_pago": 0.0, "saldo": 0.0, "d": d_at, "a": np.nan})
    for m in nomes:
        lm = _linha(cat, m)
        a_n, d_n, _ = _taxas(lm, p)
        preco = compra.preco if m == compra.modelo else float(lm["preco_brl"])
        t = compra.total if m == compra.modelo else preco
        ct = custo_trocar(t, atual.revenda_atual, preco * a_n, d_n, h)
        linhas.append({"alternativa": m, "modelo": m, "tipo": "pretendido" if m == compra.modelo else "alternativa",
                       **notas_alternativa(lm, h, hoje), "custo": ct, "total_pago": t,
                       "preco": preco, "saldo": saldo(c_manter, ct), "d": d_n, "a": a_n})
    todas = pd.DataFrame(linhas).set_index("alternativa")
    todas["comparavel"] = (todas["tipo"] == "manter") | todas["modelo"].isin(comparaveis)
    idx_manter = f"Manter: {atual.modelo}"

    def ranquear(t: pd.DataFrame) -> pd.DataFrame:
        t = t.copy()
        # critérios sem dado (ex.: suporte desconhecido) recebem a mediana das alternativas
        for c in BENEFICIO:
            if t[c].isna().any():
                t[c] = t[c].fillna(t[c].median() if t[c].notna().any() else 0.0)
        t = t.join(topsis(t, w, BENEFICIO, CUSTO))
        t["adequacao"] = [adequacao(r, w) for r in t[BENEFICIO].to_dict("records")]
        t["ganho_adequacao"] = t["adequacao"] - t.loc[idx_manter, "adequacao"]
        ganho_pos = t["ganho_adequacao"].where(t["ganho_adequacao"] > 0)
        t["custo_por_ponto"] = t["saldo"].abs() / ganho_pos
        return t.sort_values("proximidade", ascending=False)

    tab = ranquear(todas[todas["comparavel"]])                      # decide o veredito
    completo = tab if (todas["comparavel"].all() or not ranking_completo) else ranquear(todas)  # informativo

    manter_c = tab.loc[idx_manter, "proximidade"]
    trocas = tab[tab["tipo"] != "manter"]
    melhor_troca = trocas.index[0]

    meses_at = na["meses_suporte"]
    regra, veredito = None, None
    if not np.isnan(meses_at) and meses_at < p.limite_suporte_meses:
        regra, veredito = "suporte", TROCA_NECESSARIA
        motivo = (f"O suporte de software do {atual.modelo} termina em {max(meses_at, 0):.0f} meses, "
                  f"abaixo do limite de {p.limite_suporte_meses} meses: o aparelho deixará de receber "
                  f"atualizações de segurança. Recomendado: {melhor_troca}.")
    elif atual.atende == "nao":
        regra, veredito = "nao_atende", TROCA_NECESSARIA
        motivo = f"Você informou que o aparelho atual não atende às suas necessidades. Recomendado: {melhor_troca}."
    elif trocas.iloc[0]["proximidade"] > manter_c:
        veredito = VALE_TROCAR
        motivo = (f"{melhor_troca} ficou em 1º no TOPSIS entre as alternativas comparáveis (mesmo segmento e "
                  f"faixa de preço), com proximidade {_n3(trocas.iloc[0]['proximidade'])}, acima de manter "
                  f"o atual ({_n3(manter_c)}).")
    else:
        veredito = MANTER
        motivo = (f"Manter o {atual.modelo} ficou acima de todas as alternativas comparáveis (mesmo segmento e "
                  f"faixa de preço) no TOPSIS (proximidade {_n3(manter_c)} contra "
                  f"{_n3(trocas.iloc[0]['proximidade'])} de {melhor_troca}).")

    recomendado = f"Manter: {atual.modelo}" if veredito == MANTER else melhor_troca
    lp = tab.loc[compra.modelo]
    a_p, d_p = lp["a"], lp["d"]
    saldo_anos = saldo_ano_a_ano(atual.gasto_anual, atual.revenda_atual, d_at, compra.total,
                                 compra.preco * a_p, d_p)
    ref = tab.loc[recomendado if veredito != MANTER else compra.modelo]
    ind = {
        "adequacao_atual": round(float(tab.loc[f"Manter: {atual.modelo}", "adequacao"]), 2),
        "adequacao_recomendado": round(float(tab.loc[recomendado, "adequacao"]), 2),
        "ganho_adequacao": round(float(ref["ganho_adequacao"]), 2),
        "saldo_horizonte": round(float(ref["saldo"]), 2),
        "custo_por_ponto": None if pd.isna(ref["custo_por_ponto"]) else round(float(ref["custo_por_ponto"]), 2),
        "saldo_pretendido": round(float(lp["saldo"]), 2),
        "meses_suporte_atual": None if np.isnan(meses_at) else int(meses_at),
        "proximidade_recomendado": round(float(tab.loc[recomendado, "proximidade"]), 4),
        "posicao_recomendado": int(tab.loc[recomendado, "posicao"]),
        "posicao_manter": int(tab.loc[f"Manter: {atual.modelo}", "posicao"]),
        "posicao_pretendido": int(lp["posicao"]),
        "referencia_indicadores": recomendado if veredito != MANTER else compra.modelo,
        "n_ranking": int(len(tab)),
        "n_catalogo": int(len(completo)),
        "melhor_catalogo": completo[completo["tipo"] != "manter"].index[0],
        "posicao_catalogo_recomendado": int(completo.loc[recomendado, "posicao"]),
        "depreciacao_ja_sofrida": (None if not atual.valor_pago else
                                   round(1 - atual.revenda_atual / atual.valor_pago, 4)),
        "horizonte": h,
    }
    origens = {
        "d_atual": origem_d_at,
        "d_novo": _taxas(_linha(cat, compra.modelo), p)[2],
        "notas": "sumarização por percentil no catálogo (Smartprix)",
        "seguranca": f"fim do suporte: {la.get('fonte_fim_suporte', 'pendente')}",
        "satisfacao": str(la.get("fonte_satisfacao", "pendente")),
        "preco_alternativas": "catálogo (preco_brl): " + str(_linha(cat, compra.modelo).get("fonte_preco", "")),
    }
    return Resultado(veredito, motivo, regra, tab, recomendado, saldo_anos, ind, origens, w, completo)


# ------------------------------------------------------------------ modo frota
@dataclass
class PerfilFrota:
    nome: str
    quantidade: int
    modelo_atual: str
    revenda_atual: float            # por aparelho
    gasto_anual: float = 0.0        # por aparelho
    condicao: str = "boa"
    saude_bateria: float = 85.0
    atende: str = "sim"
    pesos: dict = field(default_factory=dict)


def plano_frota(perfis: list[PerfilFrota], orcamento: float, h: int, cat: pd.DataFrame,
                p: Parametros | None = None, hoje: date | None = None,
                suporte_minimo_meses: int = 36, max_modelos: int = 2) -> dict:
    """Plano de renovação da frota.

    1. Elegíveis: modelos com suporte restante >= suporte mínimo e preço conhecido.
    2. Para cada perfil, TOPSIS com 'manter' + todos os elegíveis (pesos do perfil).
    3. Restrição de no máximo `max_modelos` modelos: testa todos os conjuntos de
       até max_modelos elegíveis e escolhe o que maximiza Σ quantidade × proximidade
       da opção escolhida por perfil (perfis com troca obrigatória precisam trocar).
    4. Orçamento (desembolso imediato = preço − revenda do atual, por aparelho):
       se não couber, prioriza troca obrigatória, depois maior ganho de adequação
       por real gasto e, no empate, suporte mais próximo do fim; atende parcialmente
       o último perfil financiado (aparelhos inteiros).
    """
    p = p or Parametros()
    hoje = hoje or date.today()
    meses = cat["fim_suporte"].map(lambda f: meses_restantes(f, hoje))
    eleg = cat[(meses >= suporte_minimo_meses) & cat["preco_brl"].notna()]["modelo"].tolist()
    if not eleg:
        raise ValueError("Nenhum modelo do catálogo atende ao suporte mínimo exigido.")

    res_perfil = {}
    for pf in perfis:
        atual = AparelhoAtual(pf.modelo_atual, pf.revenda_atual, pf.gasto_anual, pf.condicao,
                              pf.saude_bateria, pf.atende)
        alts = [m for m in eleg if m != pf.modelo_atual]
        compra = Compra(alts[0], float(_linha(cat, alts[0])["preco_brl"]))
        res_perfil[pf.nome] = avaliar(atual, compra, pf.pesos, h, cat, p, hoje, alternativas=alts)

    # escolha do conjunto de modelos (≤ max_modelos)
    melhor, melhor_score = None, -np.inf
    for k in range(1, max_modelos + 1):
        for conj in combinations(eleg, k):
            score = 0.0
            for pf in perfis:
                r = res_perfil[pf.nome]
                tab = r.tabela
                opc = tab[tab["modelo"].isin(conj) & (tab["tipo"] != "manter")]["proximidade"]
                if opc.empty:
                    score = -np.inf
                    break
                c_trocar = opc.max()
                c_manter = tab.loc[tab["tipo"] == "manter", "proximidade"].iloc[0]
                c = c_trocar if r.regra_aplicada else max(c_trocar, c_manter)
                score += pf.quantidade * c
            if score > melhor_score:
                melhor, melhor_score = conj, score

    linhas = []
    for pf in perfis:
        r = res_perfil[pf.nome]
        tab = r.tabela
        lm = tab[tab["tipo"] == "manter"].iloc[0]
        opc = tab[tab["modelo"].isin(melhor) & (tab["tipo"] != "manter")]
        best = opc.iloc[0]                 # tabela já ordenada por proximidade
        obrig = r.regra_aplicada is not None
        trocar = obrig or best["proximidade"] > lm["proximidade"]
        desembolso = float(best["preco"] - pf.revenda_atual)
        linhas.append({
            "perfil": pf.nome, "quantidade": pf.quantidade, "modelo_atual": pf.modelo_atual,
            "decisao": (TROCA_NECESSARIA if obrig else VALE_TROCAR) if trocar else MANTER,
            "motivo": r.motivo if obrig else "",
            "modelo_recomendado": best.name if trocar else pf.modelo_atual,
            "proximidade_manter": round(float(lm["proximidade"]), 4),
            "proximidade_troca": round(float(best["proximidade"]), 4),
            "ganho_adequacao": round(float(best["ganho_adequacao"]), 2) if trocar else 0.0,
            "preco_unit": round(float(best["preco"]), 2) if trocar else 0.0,
            "desembolso_unit": round(desembolso, 2) if trocar else 0.0,
            "saldo_unit": round(float(best["saldo"]), 2) if trocar else 0.0,
            "meses_suporte_atual": lm["meses_suporte"],
        })
    plano = pd.DataFrame(linhas)
    plano["desembolso_total"] = plano["desembolso_unit"] * plano["quantidade"]
    plano["saldo_total"] = plano["saldo_unit"] * plano["quantidade"]
    plano["ganho_por_real"] = np.where(plano["desembolso_unit"] > 0,
                                       plano["ganho_adequacao"] / plano["desembolso_unit"].where(plano["desembolso_unit"] > 0),
                                       np.inf)

    # orçamento
    plano["obrigatoria"] = plano["decisao"] == TROCA_NECESSARIA
    ordem = plano[plano["decisao"] != MANTER].sort_values(
        ["obrigatoria", "ganho_por_real", "meses_suporte_atual"], ascending=[False, False, True])
    restante = float(orcamento)
    plano["aparelhos_financiados"] = 0
    plano["prioridade"] = pd.NA
    for prio, (i, l) in enumerate(ordem.iterrows(), start=1):
        plano.loc[i, "prioridade"] = prio
        unit = max(l["desembolso_unit"], 0.0)
        n = l["quantidade"] if unit == 0 else int(min(l["quantidade"], restante // unit))
        plano.loc[i, "aparelhos_financiados"] = n
        restante -= n * unit
    plano["aparelhos_adiados"] = np.where(plano["decisao"] != MANTER,
                                          plano["quantidade"] - plano["aparelhos_financiados"], 0)
    custo_total = float(plano["desembolso_total"].sum())
    financiado = float((plano["aparelhos_financiados"] * plano["desembolso_unit"]).sum())
    return {
        "plano": plano.drop(columns=["obrigatoria"]),
        "modelos_escolhidos": list(melhor),
        "elegiveis": eleg,
        "orcamento": float(orcamento),
        "custo_total_trocas": round(custo_total, 2),
        "custo_financiado": round(financiado, 2),
        "saldo_orcamento": round(float(orcamento) - financiado, 2),
        "cabe_no_orcamento": custo_total <= orcamento,
        "resultados_perfil": res_perfil,
    }
