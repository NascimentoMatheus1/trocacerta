"""Fase 5 — documenta passo a passo um caso concreto (o do teste de referência) com o catálogo real.

Gera docs/caso_concreto.md usando exatamente as funções do app (src/decisao.py e
src/validacao.py), para que os números do relatório acadêmico sejam reprodutíveis.

Caso: R_atual,0 = R$ 1.650; T = R$ 5.400 (à vista); G = R$ 450 por ano; H = 3 anos.
Aparelho atual: Samsung Galaxy A54 5G (boa condição, bateria 85%, atende).
Pretendido: Samsung Galaxy S24 5G. Pesos padrão do app.
Uso: python scripts/caso_concreto.py
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from src.dados import RAIZ, carregar_catalogo, carregar_parametros  # noqa: E402
from src.decisao import (BENEFICIO, CRITERIOS, CUSTO, ROTULOS, AparelhoAtual, Compra, Parametros,  # noqa: E402
                         avaliar, custo_manter, custo_trocar, normalizar_pesos, saldo, topsis_passos)
from src.relatorio import brl  # noqa: E402
from src.validacao import pontos_virada, sensibilidade  # noqa: E402

ATUAL = AparelhoAtual("Samsung Galaxy A54 5G", revenda_atual=1650, gasto_anual=450, condicao="boa",
                      saude_bateria=85, atende="sim", valor_pago=2300, anos_uso=2)
COMPRA = Compra("Samsung Galaxy S24 5G", preco=5400)
PESOS = {"camera": 15, "processamento": 15, "bateria": 15, "seguranca": 15,
         "armazenamento": 10, "satisfacao": 10, "custo": 20}
H = 3
SAIDA = RAIZ / "docs" / "caso_concreto.md"


def n(v, casas=2) -> str:
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def tabela_md(df: pd.DataFrame, casas: int = 3) -> str:
    def fmt(v):
        if isinstance(v, (float, int)) and not isinstance(v, bool):
            return n(v, casas)
        return str(v)
    cab = "| " + " | ".join([df.index.name or ""] + [str(c) for c in df.columns]) + " |"
    sep = "|" + "---|" * (len(df.columns) + 1)
    linhas = ["| " + " | ".join([str(i)] + [fmt(v) for v in r]) + " |" for i, r in zip(df.index, df.to_numpy())]
    return "\n".join([cab, sep, *linhas])


def main() -> None:
    hoje = date.today()
    cat = carregar_catalogo(hoje=hoje)
    p = Parametros.de_dict(carregar_parametros())
    w = normalizar_pesos(PESOS)
    r = avaliar(ATUAL, COMPRA, PESOS, H, cat, p, hoje)
    ind = r.indicadores
    la = cat.set_index("modelo").loc[ATUAL.modelo]
    ln = cat.set_index("modelo").loc[COMPRA.modelo]
    t = r.tabela
    tm = t[t["tipo"] == "manter"].iloc[0]
    tp = t.loc[COMPRA.modelo]
    L = []
    A = L.append

    A("# Caso concreto: passo a passo\n")
    A(f"Gerado por `scripts/caso_concreto.py` em {hoje:%d/%m/%Y}, com o catálogo e os parâmetros atuais. "
      "Os números saem das mesmas funções usadas pelo app.\n")
    sims = sorted({c for m in [ATUAL.modelo] + list(t["modelo"])
                   for c in str(cat.set_index("modelo").loc[m, "campos_simulados"]).split(";") if c})
    if sims:
        A(f"> ⚠️ **Valores simulados neste caso** (modo demonstração): {', '.join(sims)}. "
          "Depois do preenchimento manual, rode o script de novo para atualizar os números.\n")

    A("## 1. Entradas do usuário\n")
    A(f"| Entrada | Valor |\n|---|---|\n| Aparelho atual | {ATUAL.modelo} |\n"
      f"| Revenda atual (R_atual,0) | {brl(ATUAL.revenda_atual)} |\n| Gasto previsto por ano (G_ano) | {brl(ATUAL.gasto_anual)} |\n"
      f"| Condição / saúde da bateria / atende | {ATUAL.condicao} / {ATUAL.saude_bateria:g}% / {ATUAL.atende} |\n"
      f"| Modelo pretendido | {COMPRA.modelo} |\n| Total pago (T), à vista | {brl(COMPRA.total)} |\n"
      f"| Horizonte (H) | {H} anos |\n"
      f"| Pesos (normalizados) | {', '.join(f'{ROTULOS[c]} {w[c]:.0%}' for c in CRITERIOS)} |\n")

    A("## 2. Dados do catálogo\n")
    linhas = []
    for nome, l in [(ATUAL.modelo, la), (COMPRA.modelo, ln)]:
        linhas.append({"modelo": nome, "segmento (k-means)": l["segmento"],
                       "câmera": l["nota_camera"], "processamento": l["nota_processamento"],
                       "bateria": l["nota_bateria"], "armazenamento": l["nota_armazenamento"],
                       "satisfação": l["satisfacao"], "a": l["fator_revenda_inicial"], "d": l["taxa_depreciacao"],
                       "fim do suporte": l["fim_suporte"], "preço catálogo": brl(l["preco_brl"])})
    A(tabela_md(pd.DataFrame(linhas).set_index("modelo")))
    A("\nAs notas vêm da **sumarização** (percentil no catálogo). `a` e `d` vêm da **regressão** (random forest, mediana do "
      "segmento). A satisfação vem do **classificador** (por marca). Fontes: "
      f"preço: {ln['fonte_preco']}; suporte: {la['fonte_fim_suporte']}; satisfação: {la['fonte_satisfacao']}.\n")

    A("## 3. Reprodução da fórmula da proposta\n")
    A("Parâmetros da proposta: `d` = 0,30, revenda do novo partindo do preço (`a` = 1) e G = 450 como **gasto único**.\n")
    A("| H | R_atual,H | C_manter = G − R_atual,H | R_novo,H | C_trocar = T − R_atual,0 − R_novo,H | Saldo |\n|---|---|---|---|---|---|")
    for h in (1, 2, 3):
        cm = custo_manter(450, h, 1650, 0.30, g_anual=False)
        ct = custo_trocar(5400, 1650, 5400, 0.30, h)
        A(f"| {h} | {brl(1650 * 0.7 ** h)} | {brl(cm)} | {brl(5400 * 0.7 ** h)} | {brl(ct)} | **{brl(saldo(cm, ct))}** |")
    A("\nO resultado bate com o caso de referência: **−675; −1.463; −2.014** (arredondados). O teste "
      "`test_caso_referencia_gasto_unico` verifica esses valores.\n")

    A("## 4. Modelo financeiro do TrocaCerta\n")
    A(f"O protótipo trata G como **anual** e usa `a` e `d` estimados. Atual: d = {n(tm['d'], 4)}. "
      f"Novo: a = {n(tp['a'], 4)}, d = {n(tp['d'], 4)}, logo R_novo,0 = {brl(COMPRA.preco)} × {n(tp['a'], 4)} = "
      f"{brl(COMPRA.preco * tp['a'])}.\n")
    sa = r.saldo_anos
    A("| H | R_atual,H | C_manter = G·H − R_atual,H | R_novo,H | C_trocar | Saldo |\n|---|---|---|---|---|---|")
    for _, l in sa.iterrows():
        A(f"| {int(l['ano'])} | {brl(l['revenda_atual'])} | {brl(l['custo_manter'])} | {brl(l['revenda_novo'])} | "
          f"{brl(l['custo_trocar'])} | **{brl(l['saldo'])}** |")
    A(f"\nEm H = {H}, o saldo do pretendido é **{brl(ind['saldo_pretendido'])}** "
      f"({'trocar sai mais barato' if ind['saldo_pretendido'] > 0 else 'manter sai mais barato'}). "
      "A queda imediata de valor do aparelho novo (`a` < 1) pesa contra a troca.\n")

    A("## 5. Ajustes do aparelho atual\n")
    f = p.fatores_condicao[ATUAL.condicao]
    A(f"- Fator de condição ({ATUAL.condicao}) = {n(f)}, aplicado a câmera, processamento e bateria.\n"
      f"- Bateria × saúde: {n(la['nota_bateria'])} × {n(f)} × {n(ATUAL.saude_bateria / 100)} = {n(tm['bateria'])}.\n"
      f"- Segurança = min(meses restantes, 12H)/(12H) × 10 = min({tm['meses_suporte']:.0f}, {12 * H})/{12 * H} × 10 "
      f"= {n(tm['seguranca'])}.\n- 'Atende = {ATUAL.atende}': sem redução.\n")

    A("## 6. Alternativas comparáveis\n")
    A(f"São o pretendido mais os modelos do mesmo segmento (k-means) com preço até ±{p.faixa_preco:.0%} de "
      f"{brl(COMPRA.preco)}, no máximo {p.max_alternativas} contando *manter*: "
      + ", ".join(i for i in t.index) + ".\n")

    A("## 7. TOPSIS passo a passo\n")
    passos = topsis_passos(t, w, BENEFICIO, CUSTO)
    rot = {c: ROTULOS[c] for c in CRITERIOS}
    X = t[BENEFICIO + CUSTO].rename(columns=rot)
    X.index.name = "Alternativa"
    A("**7.1 Matriz de decisão** (notas de 0 a 10; custo em R$ no horizonte):\n")
    A(tabela_md(X, 2))
    if (t["custo"] <= 0).any():
        A(f"\nComo há custo ≤ 0, o custo foi transladado para x − mín + 1 antes da normalização "
          f"(mín = {brl(t['custo'].min())}). A ordem se mantém.\n")
    for titulo, M in [("7.2 Matriz normalizada R = x / √(Σx²)", passos["R"]),
                      ("7.3 Matriz ponderada V = w × R", passos["V"])]:
        A(f"\n**{titulo}:**\n")
        M = M.rename(columns=rot)
        M.index.name = "Alternativa"
        A(tabela_md(M, 4))
    ideais = pd.DataFrame({"A+ (ideal positivo)": passos["ideal_pos"], "A− (ideal negativo)": passos["ideal_neg"],
                           "peso w": passos["w"]}).rename(index=rot).T
    ideais.index.name = ""
    A("\n**7.4 Soluções ideais** (máximo nos benefícios e mínimo no custo para A+; o inverso para A−):\n")
    A(tabela_md(ideais, 4))
    res = pd.DataFrame({"D+": passos["d_pos"], "D−": passos["d_neg"], "C = D−/(D+ + D−)": passos["proximidade"],
                        "posição": t["posicao"].astype(int).astype(str) + "º"}
                       ).sort_values("C = D−/(D+ + D−)", ascending=False)
    res.index.name = "Alternativa"
    A("\n**7.5 Distâncias e proximidade:**\n")
    A(tabela_md(res, 4))

    A("\n## 8. Regras e veredito\n")
    A(f"- Suporte do atual: {tm['meses_suporte']:.0f} meses contra o limite de {p.limite_suporte_meses} → "
      f"{'regra acionada' if r.regra_aplicada == 'suporte' else 'regra não acionada'}.\n"
      f"- Atende às necessidades: {ATUAL.atende} → "
      f"{'regra acionada' if r.regra_aplicada == 'nao_atende' else 'regra não acionada'}.\n"
      f"- Sem regra acionada, vale o TOPSIS entre as comparáveis.\n")
    A(f"**Veredito: {r.veredito}.** {r.motivo}\n")
    A("| Indicador | Valor |\n|---|---|")
    A(f"| Adequação atual | {n(ind['adequacao_atual'], 2)} / 10 |")
    A(f"| Adequação do {ind['referencia_indicadores']} | {n(t.loc[ind['referencia_indicadores'], 'adequacao'], 2)} / 10 |")
    A(f"| Ganho de adequação | {n(ind['ganho_adequacao'], 2)} |")
    A(f"| Saldo em {H} anos | {brl(ind['saldo_horizonte'])} |")
    A(f"| Custo por ponto ganho | {brl(ind['custo_por_ponto']) if ind['custo_por_ponto'] else '—'} |")
    A(f"| Posição de *manter* / do pretendido | {ind['posicao_manter']}º / {ind['posicao_pretendido']}º de {ind['n_ranking']} |\n")

    A("## 9. Análise de sensibilidade\n")
    s = sensibilidade(ATUAL, COMPRA, PESOS, H, cat, p, hoje)
    A(f"Cada peso foi variado em ±20% (com renormalização) e a taxa `d` de todos os modelos em ±10 p.p. "
      f"O veredito se manteve em **{s['pct_cenarios_mesmo_veredito']:.0%}** dos cenários, e o 1º lugar do ranking "
      f"em **{s['pct_cenarios_mesmo_primeiro']:.0%}**.\n")
    tp_ = s["pesos"][["parametro", "variacao", "veredito", "primeiro", "margem", "mantem_veredito"]].copy()
    tp_ = pd.concat([tp_, s["depreciacao"][["parametro", "variacao", "veredito", "primeiro", "margem", "mantem_veredito"]]])
    tp_["mantem_veredito"] = tp_["mantem_veredito"].map({True: "sim", False: "**não**"})
    tp_ = tp_.rename(columns={"parametro": "Parâmetro", "variacao": "Variação", "veredito": "Veredito",
                              "primeiro": "1º lugar", "margem": "Margem (troca − manter)",
                              "mantem_veredito": "Mantém?"}).set_index("Parâmetro")
    A(tabela_md(tp_, 4))
    A("\n**Pontos de virada.** Cada parâmetro foi varrido sozinho até o veredito mudar. Para os pesos, o valor é a "
      "parcela do critério no total, com os demais pesos redistribuídos na proporção original:\n")
    pv = pontos_virada(ATUAL, COMPRA, PESOS, H, cat, p, hoje)
    A("| Parâmetro | Valor atual | Virada em | Novo veredito |\n|---|---|---|---|")
    for _, l in pv.iterrows():
        if l["chave"] == "preco":
            va, vv = brl(l["valor_atual"]), (brl(l["valor_virada"]) if pd.notna(l["valor_virada"]) else "—")
        elif l["chave"] == "d":
            va, vv = "0 p.p.", (f"{l['valor_virada'] * 100:+.0f} p.p." if pd.notna(l["valor_virada"]) else "—")
        else:
            va, vv = f"{l['valor_atual']:.0%}", (f"{l['valor_virada']:.0%}" if pd.notna(l["valor_virada"]) else "—")
        A(f"| {l['parametro']} | {va} | {vv} | {l['novo_veredito'] if pd.notna(l['novo_veredito']) else l['observacao']} |")
    A("\nA grade tem 41 pontos por parâmetro. A virada é o ponto médio entre os dois pontos vizinhos da grade em que o "
      "veredito muda. Faixas testadas: pesos de 0% a 95%, `d` de −30 a +50 p.p., preço de 30% a 200% do informado.\n")

    SAIDA.parent.mkdir(exist_ok=True)
    SAIDA.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"Gerado: {SAIDA}")
    print(f"Veredito: {r.veredito} | saldo {brl(ind['saldo_horizonte'])} | "
          f"estável em {s['pct_cenarios_mesmo_veredito']:.0%} dos cenários")


if __name__ == "__main__":
    main()
