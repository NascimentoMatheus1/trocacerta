"""Página 3 — Relatório: resumo em texto, veredito, cartões, ranking e comparativo por critério."""
from datetime import date

import pandas as pd
import streamlit as st

from src import ui
from src.decisao import BENEFICIO, ROTULOS, AparelhoAtual, Compra, avaliar
from src.relatorio import resumo_consumidor

ui.exigir_papel("consumidor", "admin")
cat = ui.cat()
st.title("📄 Relatório da decisão")

if "atual" not in st.session_state or "compra" not in st.session_state:
    st.warning("Faça uma simulação primeiro.")
    st.page_link("pages/2_simulacao.py", label="Ir para Simulação", icon="🧮")
    st.stop()

atual = AparelhoAtual(**st.session_state["atual"])
compra = Compra(**st.session_state["compra"])
# Recalcula a partir das entradas (não reaproveita um resultado antigo guardado na sessão).
r = avaliar(atual, compra, ui.pesos(), ui.horizonte(), cat, ui.params(), date.today())
ind = r.indicadores
sim = ui.simulados(cat, [atual.modelo] + list(r.tabela["modelo"]))

st.markdown(resumo_consumidor(r, atual, compra, sim))

c1, c2, c3, c4 = st.columns(4)
c1.metric("Veredito", r.veredito)
c2.metric(f"Saldo em {ind['horizonte']} ano(s)", ui.brl(ind["saldo_horizonte"]))
c3.metric("Ganho de adequação", f"{ind['ganho_adequacao']:+.1f} pts")
c4.metric("Posição no TOPSIS", f"{ind['posicao_recomendado']}º de {ind['n_ranking']}",
          help=f"Proximidade {ind['proximidade_recomendado']:.3f}")

st.subheader("Ranking")
ui.mostrar_ranking(r.tabela)

completo = st.toggle(f"📋 Ver relatório completo: ranking de todo o catálogo ({ind['n_catalogo']} alternativas)",
                     key="rel_completo")
if completo:
    with st.container(border=True):
        st.markdown(f"#### Ranking de todo o catálogo ({ind['n_catalogo']} alternativas)")
        rec = (f"Manter o {atual.modelo}" if r.recomendado.startswith("Manter: ")
               else f"O recomendado, {r.recomendado},")
        st.write(f"Melhor aparelho do catálogo para os seus pesos: **{ind['melhor_catalogo']}**. "
                 f"{rec} ficaria em {ind['posicao_catalogo_recomendado']}º neste ranking.")
        ui.mostrar_ranking_catalogo(r.ranking_completo)

st.subheader("Comparativo por critério")
idx_atual = r.tabela.index[r.tabela["tipo"] == "manter"][0]
idx_rec = ind["referencia_indicadores"]
st.plotly_chart(ui.grafico_criterios(r.tabela, idx_atual, idx_rec), width="stretch")
comp = pd.DataFrame({
    "Critério": [ROTULOS[c] for c in BENEFICIO],
    "Peso": [f"{r.pesos[c]:.0%}" for c in BENEFICIO],
    "Atual (ajustado)": [round(r.tabela.loc[idx_atual, c], 1) for c in BENEFICIO],
    idx_rec: [round(r.tabela.loc[idx_rec, c], 1) for c in BENEFICIO],
})
st.dataframe(comp, hide_index=True, width="stretch")

st.subheader("De onde vêm os números")
st.markdown("\n".join(f"- **{k.replace('_', ' ').capitalize()}:** {v}" for k, v in r.origens.items()))
st.markdown(f"- **Pesos (normalizados):** " + ", ".join(f"{ROTULOS[c]} {v:.0%}" for c, v in r.pesos.items()))
