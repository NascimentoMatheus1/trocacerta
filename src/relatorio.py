"""Geração do resumo em texto a partir dos indicadores do modelo de decisão."""
from __future__ import annotations

import pandas as pd

from src.decisao import BENEFICIO, MANTER, ROTULOS, TROCA_NECESSARIA, AparelhoAtual, Compra, Resultado


def brl(v: float | None) -> str:
    if v is None or pd.isna(v):
        return "—"
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'−' if v < 0 else ''}R$ {s}"


def num(v: float, casas: int = 1, sinal: bool = False) -> str:
    """Número no padrão brasileiro (vírgula decimal)."""
    return f"{v:{'+' if sinal else ''}.{casas}f}".replace(".", ",")


def resumo_consumidor(r: Resultado, atual: AparelhoAtual, compra: Compra, simulados: list[str]) -> str:
    ind = r.indicadores
    h = ind["horizonte"]
    tab = r.tabela
    manter = tab[tab["tipo"] == "manter"].iloc[0]
    ref_nome = ind["referencia_indicadores"]
    ref = tab.loc[ref_nome]

    p = [f"**Veredito: {r.veredito}.** {r.motivo}"]

    # financeiro
    s = ind["saldo_horizonte"]
    sentido = ("trocar sai **mais barato** que manter" if s > 0 else
               "manter sai **mais barato** que trocar" if s < 0 else "os dois caminhos custam o mesmo")
    p.append(
        f"**Financeiro ({h} {'ano' if h == 1 else 'anos'}).** Manter o {atual.modelo} custa {brl(manter['custo'])} "
        f"(gastos previstos menos a revenda ao fim do período). Trocar pelo {ref_nome} custa "
        f"{brl(ref['custo'])} (valor pago menos a revenda do atual hoje e a revenda do novo ao fim). "
        f"Saldo de {brl(s)}: {sentido}."
    )
    if ref_nome != compra.modelo:
        p.append(f"O modelo que você pretendia, {compra.modelo}, ficou em {ind['posicao_pretendido']}º no "
                 f"ranking, com saldo de {brl(ind['saldo_pretendido'])}.")

    # adequação
    g = ind["ganho_adequacao"]
    txt = (f"**Adequação.** Seu aparelho atual tem nota {num(ind['adequacao_atual'])}/10 para as suas prioridades")
    if r.veredito != MANTER or g > 0:
        txt += f"; o {ref_nome} tem {num(tab.loc[ref_nome, 'adequacao'])}/10 (ganho de {num(g, sinal=True)} ponto(s))"
        if ind["custo_por_ponto"] is not None:
            txt += f", o que custa {brl(ind['custo_por_ponto'])} por ponto ganho"
    p.append(txt + ".")

    # critérios em que o recomendado ganha/perde
    if r.veredito != MANTER:
        dif = {ROTULOS[c]: ref[c] - manter[c] for c in BENEFICIO}
        ganha = [k for k, v in sorted(dif.items(), key=lambda t: -t[1]) if v > 0.5][:3]
        perde = [k for k, v in sorted(dif.items(), key=lambda t: t[1]) if v < -0.5][:2]
        if ganha:
            p.append(f"Principais ganhos: {', '.join(ganha).lower()}."
                     + (f" Perde em: {', '.join(perde).lower()}." if perde else ""))

    if ind["meses_suporte_atual"] is not None:
        p.append(f"**Suporte.** O aparelho atual tem {max(ind['meses_suporte_atual'], 0)} meses de "
                 f"atualizações restantes.")

    if simulados:
        p.append("⚠️ **Atenção:** este resultado usa valores **simulados** para: "
                 + "; ".join(simulados) + ". Preencha os dados reais para uma decisão definitiva.")
    return "\n\n".join(p)


def resumo_frota(res: dict) -> str:
    pl = res["plano"]
    trocas = pl[pl["decisao"] != MANTER]
    p = [f"**Modelos padronizados na frota:** {', '.join(res['modelos_escolhidos'])} "
         f"(no máximo {len(res['modelos_escolhidos'])} modelo(s), todos com o suporte mínimo exigido)."]
    for _, l in pl.iterrows():
        if l["decisao"] == MANTER:
            p.append(f"- **{l['perfil']}** ({l['quantidade']} aparelhos): manter o {l['modelo_atual']}.")
        else:
            extra = " (regra obrigatória)" if l["decisao"] == TROCA_NECESSARIA else ""
            p.append(f"- **{l['perfil']}** ({l['quantidade']} aparelhos): {l['decisao'].lower()}{extra} → "
                     f"{l['modelo_recomendado']}; desembolso {brl(l['desembolso_total'])}, "
                     f"saldo no horizonte {brl(l['saldo_total'])}, ganho de adequação {num(l['ganho_adequacao'], sinal=True)}.")
    if res["cabe_no_orcamento"]:
        p.append(f"O custo total das trocas ({brl(res['custo_total_trocas'])}) **cabe no orçamento** de "
                 f"{brl(res['orcamento'])}; sobram {brl(res['saldo_orcamento'])}.")
    else:
        adiados = int(trocas["aparelhos_adiados"].sum())
        p.append(f"O custo total das trocas ({brl(res['custo_total_trocas'])}) **excede o orçamento** de "
                 f"{brl(res['orcamento'])}. Foram financiadas {brl(res['custo_financiado'])}, priorizando trocas "
                 f"obrigatórias, depois maior ganho de adequação por real e suporte mais próximo do fim; "
                 f"{adiados} aparelho(s) ficam para o próximo ciclo.")
    return "\n".join(p)
