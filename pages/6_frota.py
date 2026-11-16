"""Página — Modo frota: plano de renovação dos celulares corporativos."""
from datetime import date

import pandas as pd
import streamlit as st

from src import ui
from src.dados import carregar_parametros
from src.decisao import CRITERIOS, MANTER, ROTULOS, PerfilFrota, plano_frota
from src.relatorio import resumo_frota

ui.exigir_papel("gestor", "admin")
cat = ui.cat()
p = ui.params()
cfg = carregar_parametros()["frota"]
st.title("🏢 Plano de renovação da frota")
ui.aviso_demo()

modelos = cat["modelo"].tolist()
if "frota_perfis" not in st.session_state:
    st.session_state["frota_perfis"] = pd.DataFrame([
        {"perfil": "Campo/vendas", "quantidade": 40, "modelo_atual": "Motorola Moto G14", "revenda_atual": 350.0,
         "gasto_anual": 180.0, "condicao": "regular", "saude_bateria": 72, "atende": "parcialmente"},
        {"perfil": "Operacional", "quantidade": 60, "modelo_atual": "Samsung Galaxy A05", "revenda_atual": 300.0,
         "gasto_anual": 120.0, "condicao": "boa", "saude_bateria": 80, "atende": "sim"},
        {"perfil": "Executivo", "quantidade": 10, "modelo_atual": "Apple iPhone 12", "revenda_atual": 1800.0,
         "gasto_anual": 250.0, "condicao": "boa", "saude_bateria": 78, "atende": "sim"},
    ])
    st.session_state["frota_pesos"] = pd.DataFrame(cfg["pesos_perfis"]).T.reset_index(names="perfil")

st.subheader("1. Perfis de uso")
perfis_df = st.data_editor(
    st.session_state["frota_perfis"], num_rows="dynamic", width="stretch", key="ed_perfis",
    column_config={
        "perfil": "Perfil", "quantidade": st.column_config.NumberColumn("Qtd.", min_value=1, step=1),
        "modelo_atual": st.column_config.SelectboxColumn("Modelo atual", options=modelos, required=True),
        "revenda_atual": st.column_config.NumberColumn("Revenda/aparelho (R$)", min_value=0, format="%.0f"),
        "gasto_anual": st.column_config.NumberColumn("Gasto anual/aparelho (R$)", min_value=0, format="%.0f"),
        "condicao": st.column_config.SelectboxColumn("Condição", options=list(ui.CONDICOES)),
        "saude_bateria": st.column_config.NumberColumn("Saúde bateria (%)", min_value=30, max_value=100),
        "atende": st.column_config.SelectboxColumn("Atende?", options=list(ui.ATENDE)),
    })

st.subheader("2. Pesos por perfil")
st.caption("Pesos pré-definidos por perfil (editáveis); cada linha é normalizada para somar 100%.")
pesos_df = st.session_state["frota_pesos"]
faltam = [x for x in perfis_df["perfil"].dropna() if x not in set(pesos_df["perfil"])]
if faltam:
    pesos_df = pd.concat([pesos_df, pd.DataFrame([{"perfil": x, **ui.PESOS_PADRAO} for x in faltam])], ignore_index=True)
pesos_df = st.data_editor(pesos_df, width="stretch", key="ed_pesos", hide_index=True,
                          column_config={c: st.column_config.NumberColumn(ROTULOS[c], min_value=0, max_value=100)
                                         for c in CRITERIOS} | {"perfil": st.column_config.TextColumn("Perfil", disabled=True)})

st.subheader("3. Restrições")
c1, c2, c3, c4 = st.columns(4)
orc = c1.number_input("Orçamento total (R$)", 0.0, 10_000_000.0, 150_000.0, 5_000.0)
sup = c2.number_input("Suporte mínimo exigido (meses)", 0, 84, int(cfg["suporte_minimo_meses"]))
maxm = c3.number_input("Máximo de modelos na frota", 1, 5, int(cfg["max_modelos_diferentes"]))
h = c4.slider("Horizonte (anos)", 1, 5, 3)

if st.button("Gerar plano de renovação", type="primary"):
    pesos_por = pesos_df.set_index("perfil")
    perfis = []
    for _, l in perfis_df.dropna(subset=["perfil", "modelo_atual"]).iterrows():
        w = pesos_por.loc[l["perfil"], CRITERIOS].to_dict() if l["perfil"] in pesos_por.index else ui.PESOS_PADRAO
        perfis.append(PerfilFrota(l["perfil"], int(l["quantidade"]), l["modelo_atual"], float(l["revenda_atual"]),
                                  float(l["gasto_anual"]), l["condicao"], float(l["saude_bateria"]), l["atende"], w))
    try:
        with st.spinner("Avaliando perfis e combinações de modelos..."):
            st.session_state["frota_res"] = plano_frota(perfis, orc, h, cat, p, date.today(), int(sup), int(maxm))
    except ValueError as e:
        st.error(str(e))

res = st.session_state.get("frota_res")
if res:
    st.divider()
    st.subheader("Plano de renovação")
    k = st.columns(4)
    k[0].metric("Modelos escolhidos", len(res["modelos_escolhidos"]))
    k[1].metric("Custo total das trocas", ui.brl(res["custo_total_trocas"]))
    k[2].metric("Orçamento", ui.brl(res["orcamento"]),
                delta="cabe" if res["cabe_no_orcamento"] else "insuficiente",
                delta_color="normal" if res["cabe_no_orcamento"] else "inverse")
    k[3].metric("Saldo total no horizonte", ui.brl(res["plano"]["saldo_total"].sum()),
                help="Σ (C_manter − C_trocar) × quantidade. Positivo = trocar sai mais barato.")
    st.markdown(resumo_frota(res))
    pl = res["plano"]
    st.dataframe(pd.DataFrame({
        "Perfil": pl["perfil"], "Qtd.": pl["quantidade"], "Atual": pl["modelo_atual"], "Decisão": pl["decisao"],
        "Modelo recomendado": pl["modelo_recomendado"], "Ganho adequação": pl["ganho_adequacao"],
        "Desembolso total": pl["desembolso_total"].map(ui.brl), "Saldo total": pl["saldo_total"].map(ui.brl),
        "Prioridade": pl["prioridade"], "Financiados": pl["aparelhos_financiados"], "Adiados": pl["aparelhos_adiados"],
    }), hide_index=True, width="stretch")
    ui.fonte("custo por aparelho × quantidade; desembolso = preço − revenda do atual; depreciação pela regressão "
             "(mediana do segmento); elegíveis = modelos com suporte ≥ mínimo; conjunto de modelos escolhido "
             "testando todas as combinações permitidas")
    sim = ui.simulados(cat, list(res["modelos_escolhidos"]) + list(pl["modelo_atual"]))
    if sim:
        st.warning("Valores simulados neste plano: " + "; ".join(sim))
    with st.expander("Ranking TOPSIS completo por perfil"):
        st.caption(f"Todos os {len(res['elegiveis'])} modelos elegíveis (suporte ≥ mínimo exigido) + manter o atual.")
        for nome, r in res["resultados_perfil"].items():
            st.markdown(f"**{nome}**")
            st.dataframe(ui.tabela_ranking(r.tabela).drop(columns=["Comparável"]), hide_index=True,
                         width="stretch", height=min(38 + 35 * len(r.tabela), 420))
