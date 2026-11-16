"""Página 2 — Simulação: pesos, novo aparelho, pagamento e horizonte; resultado imediato."""
from datetime import date

import streamlit as st

from src import ui
from src.decisao import MANTER, TROCA_NECESSARIA, AparelhoAtual, Compra, avaliar

ui.exigir_papel("consumidor", "admin")
cat = ui.cat()
p = ui.params()
st.title("🧮 Simulação")
ui.aviso_demo()

if "atual" not in st.session_state:
    st.warning("Preencha primeiro o seu aparelho atual.")
    st.page_link("pages/1_aparelho_atual.py", label="Ir para Aparelho atual", icon="📱")
    st.stop()
atual_d = st.session_state["atual"]
atual = AparelhoAtual(**atual_d)

col_in, col_out = st.columns([2, 3], gap="large")
with col_in:
    with st.expander("⚖️ Pesos dos critérios", expanded=True):
        st.session_state["pesos"] = ui.editor_pesos("w", ui.pesos())

    st.subheader("Novo aparelho")
    modelos = [m for m in cat["modelo"] if m != atual.modelo]
    ant = st.session_state.get("compra", {})
    novo = st.selectbox("Modelo pretendido", modelos,
                        index=modelos.index(ant["modelo"]) if ant.get("modelo") in modelos else
                        modelos.index("Samsung Galaxy A55 5G") if "Samsung Galaxy A55 5G" in modelos else 0)
    ln = cat.set_index("modelo").loc[novo]
    preco_cat = float(ln["preco_brl"])
    preco = st.number_input("Preço à vista (R$)", 0.0, 30_000.0,
                            float(ant.get("preco", preco_cat)) if ant.get("modelo") == novo else preco_cat, 50.0)
    ui.fonte(f"preço do catálogo {ui.brl(preco_cat)} — {ln['fonte_preco']}")
    forma = st.radio("Pagamento", ["À vista", "Parcelado"], horizontal=True,
                     index=1 if ant.get("parcelado") else 0)
    n_parc, v_parc = 1, 0.0
    if forma == "Parcelado":
        c1, c2 = st.columns(2)
        # Ao vir de "à vista", o estado guarda n_parcelas = 1 e parcela = 0: usa padrões válidos.
        n_ini = int(ant.get("n_parcelas") or 10)
        n_ini = n_ini if 2 <= n_ini <= 24 else 10
        n_parc = c1.number_input("Parcelas", 2, 24, n_ini)
        v_ini = float(ant.get("valor_parcela") or 0.0)
        if not 0 < v_ini <= 10_000:
            v_ini = min(round(preco / n_parc, 2), 10_000.0)
        v_parc = c2.number_input("Valor da parcela (R$)", 0.0, 10_000.0, v_ini, 10.0)
    h = st.slider("Horizonte de análise (anos)", 1, 5, ui.horizonte())
    st.session_state["horizonte"] = h
    compra = Compra(novo, preco, forma == "Parcelado", int(n_parc), float(v_parc))
    st.session_state["compra"] = dict(modelo=novo, preco=preco, parcelado=compra.parcelado,
                                      n_parcelas=compra.n_parcelas, valor_parcela=compra.valor_parcela)
    st.caption(f"Total pago T = **{ui.brl(compra.total)}**"
               + (f" ({n_parc} × {ui.brl(v_parc)})" if compra.parcelado else ""))

r = avaliar(atual, compra, ui.pesos(), h, cat, p, date.today())
st.session_state["resultado"] = r

with col_out:
    cor = {TROCA_NECESSARIA: "red", MANTER: "gray"}.get(r.veredito, "blue")
    st.markdown(f"### :{cor}[{r.veredito}]")
    st.write(r.motivo)
    if r.regra_aplicada:
        st.caption("Regra de prioridade aplicada: as regras prevalecem sobre o ranking TOPSIS.")
    ind = r.indicadores
    m1, m2, m3 = st.columns(3)
    m1.metric(f"Saldo em {h} ano(s)", ui.brl(ind["saldo_horizonte"]),
              help="C_manter − C_trocar. Positivo = trocar sai mais barato.")
    m2.metric("Ganho de adequação", f"{ind['ganho_adequacao']:+.1f} pts",
              help=f"Adequação do {ind['referencia_indicadores']} menos a do atual.")
    m3.metric("Custo por ponto ganho", "—" if ind["custo_por_ponto"] is None else ui.brl(ind["custo_por_ponto"]))
    st.caption(f"Indicadores calculados para: **{ind['referencia_indicadores']}**")

    st.plotly_chart(ui.grafico_saldo(r.saldo_anos, h), width="stretch")
    ui.fonte(f"saldo do modelo pretendido ({novo}). Depreciação do atual: {r.origens['d_atual']}; "
             f"do novo: {r.origens['d_novo']} (revenda do novo = preço × a × (1 − d)^H)")
    st.plotly_chart(ui.grafico_ranking(r.tabela, r.recomendado), width="stretch")
    ui.fonte("TOPSIS com normalização vetorial; alternativas = manter + pretendido + mesmo segmento "
             f"(k-means) com preço ±{p.faixa_preco:.0%}")

st.subheader("Ranking")
ui.mostrar_ranking(r.tabela)
st.caption("O ranking com o catálogo inteiro está no relatório completo.")
with st.expander("Ver saldo ano a ano em tabela"):
    st.dataframe(r.saldo_anos.rename(columns={"ano": "Ano", "custo_manter": "C_manter", "custo_trocar": "C_trocar",
                                              "revenda_atual": "R_atual,H", "revenda_novo": "R_novo,H",
                                              "saldo": "Saldo"}), hide_index=True, width="stretch")

sim = ui.simulados(cat, [atual.modelo] + list(r.tabela["modelo"]))
if sim:
    st.warning("Valores simulados neste resultado: " + "; ".join(sim))
st.page_link("pages/3_relatorio.py", label="Ver relatório completo →", icon="📄")
