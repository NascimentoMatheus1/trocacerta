"""Página 5 — Administração: parâmetros, catálogo e pendências (somente admin)."""
import pandas as pd
import streamlit as st

from src import ui
from src.dados import ARQ_PENDENCIAS, carregar_parametros, salvar_parametros

ui.exigir_papel("admin")
st.title("⚙️ Administração")
p = carregar_parametros()

st.subheader("Parâmetros do modelo")
with st.form("parametros"):
    c1, c2, c3 = st.columns(3)
    d_fb = c1.number_input("Taxa de depreciação de fallback (d)", 0.0, 0.9, float(p["taxa_depreciacao_fallback"]), 0.01,
                           help="Usada só quando a regressão não tem estimativa para o modelo.")
    lim = c2.number_input("Limite de suporte para 'troca necessária' (meses)", 0, 36, int(p["limite_suporte_meses"]))
    faixa = c3.number_input("Faixa de preço das alternativas (±)", 0.05, 1.0, float(p.get("faixa_preco", 0.30)), 0.05)
    c4, c5, c6 = st.columns(3)
    red = c4.number_input("Redução por 'atende parcialmente'", 0.0, 0.9, float(p["reducao_atende_parcialmente"]), 0.05)
    sup_min = c5.number_input("Frota: suporte mínimo (meses)", 0, 84, int(p["frota"]["suporte_minimo_meses"]))
    max_mod = c6.number_input("Frota: máximo de modelos diferentes", 1, 5, int(p["frota"]["max_modelos_diferentes"]))
    st.markdown("**Modo demonstração**")
    c7, c8, c9 = st.columns(3)
    demo = c7.toggle("Ativo (simular dados ausentes)", bool(p["modo_demo"]))
    cambio = c8.number_input("Câmbio INR→BRL (preço simulado)", 0.01, 0.2, float(p["demo"]["cambio_inr_brl"]), 0.005,
                             format="%.3f")
    sup_sim = c9.number_input("Suporte simulado (meses a partir de hoje)", 0, 120, int(p["demo"]["meses_suporte_simulado"]))
    if st.form_submit_button("Salvar parâmetros", type="primary"):
        p.update(taxa_depreciacao_fallback=d_fb, limite_suporte_meses=int(lim), faixa_preco=faixa,
                 reducao_atende_parcialmente=red, modo_demo=demo)
        p["frota"].update(suporte_minimo_meses=int(sup_min), max_modelos_diferentes=int(max_mod))
        p["demo"].update(cambio_inr_brl=cambio, meses_suporte_simulado=int(sup_sim))
        salvar_parametros(p)
        st.cache_data.clear()
        st.success("Parâmetros salvos em data/parametros.json.")
st.caption("No Streamlit Community Cloud o disco é temporário: alterações valem até o app reiniciar. "
           "Para torná-las permanentes, faça commit de data/parametros.json.")

st.subheader("Catálogo")
cat = ui.cat()
cols = ["modelo", "marca", "segmento", "preco_brl", "fonte_preco", "fim_suporte", "fonte_fim_suporte",
        "nota_camera", "nota_processamento", "nota_bateria", "nota_armazenamento", "satisfacao",
        "fonte_satisfacao", "fator_revenda_inicial", "taxa_depreciacao", "campos_simulados"]
st.dataframe(cat[cols], hide_index=True, width="stretch")
n_sim = (cat["campos_simulados"] != "").sum()
st.caption(f"{len(cat)} modelos; {n_sim} com algum campo simulado.")

st.subheader("Pendências de dados")
pend = pd.read_csv(ARQ_PENDENCIAS)
st.dataframe(pend.groupby(["campo", "arquivo"]).size().rename("modelos pendentes").reset_index(),
             hide_index=True, width="stretch")
with st.expander("Ver lista completa"):
    st.dataframe(pend, hide_index=True, width="stretch")
st.download_button("Baixar pendencias.csv", pend.to_csv(index=False).encode("utf-8"), "pendencias.csv", "text/csv")
st.caption("Para resolver: preencha data/precos_manuais.csv, data/suporte_manual.csv e data/avaliacoes_manuais.csv "
           "e rode `python scripts/gerar_catalogo.py` e `python scripts/gerar_analitica.py --pular-classificador`.")
