"""Página 1 — Aparelho atual: formulário + painel 'encontrado no catálogo' + adequação atual."""
from datetime import date

import pandas as pd
import streamlit as st

from src import ui
from src.analitica import posicao_mercado
from src.decisao import AparelhoAtual, adequacao, normalizar_pesos, notas_atual, revenda

ui.exigir_papel("consumidor", "admin")
cat = ui.cat()
p = ui.params()
st.title("📱 Seu aparelho atual")
ui.aviso_demo()

ant = st.session_state.get("atual", {})
modelos = cat["modelo"].tolist()

col_form, col_cat = st.columns([1, 1], gap="large")
with col_form:
    modelo = st.selectbox("Modelo", modelos, index=modelos.index(ant.get("modelo", "Samsung Galaxy A14 5G")))
    linha = cat.set_index("modelo").loc[modelo]
    c1, c2 = st.columns(2)
    valor_pago = c1.number_input("Valor pago (R$)", 0.0, 50_000.0, float(ant.get("valor_pago", 1300.0)), 50.0)
    anos_uso = c2.number_input("Anos de uso", 0.0, 10.0, float(ant.get("anos_uso", 2.0)), 0.5)

    # sugestão de revenda pela regressão (o usuário pode e deve ajustar com o valor real de mercado)
    sugestao = revenda(valor_pago * float(linha["fator_revenda_inicial"]), float(linha["taxa_depreciacao"]), anos_uso)
    revenda_atual = st.number_input("Quanto você conseguiria vendendo hoje (R$) — R_atual,0", 0.0, 50_000.0,
                                    float(ant.get("revenda_atual", round(sugestao, -1))), 50.0)
    st.caption(f"Sugestão estimada pela regressão de depreciação: **{ui.brl(sugestao)}** "
               f"(= valor pago × {linha['fator_revenda_inicial']:.2f} × (1 − {linha['taxa_depreciacao']:.3f})"
               f"^{anos_uso:g}). Prefira o valor real de anúncios de usados.")

    c3, c4 = st.columns(2)
    condicao = c3.selectbox("Condição", list(ui.CONDICOES), format_func=ui.CONDICOES.get,
                            index=list(ui.CONDICOES).index(ant.get("condicao", "boa")))
    saude = c4.slider("Saúde da bateria (%)", 30, 100, int(ant.get("saude_bateria", 85)))
    atende = st.radio("O aparelho atende às suas necessidades?", list(ui.ATENDE), format_func=ui.ATENDE.get,
                      index=list(ui.ATENDE).index(ant.get("atende", "sim")), horizontal=True)
    gasto = st.number_input("Gastos previstos por ano com o atual (R$) — reparos, bateria, capa etc. (G_ano)",
                            0.0, 10_000.0, float(ant.get("gasto_anual", 150.0)), 50.0)

    st.session_state["atual"] = dict(modelo=modelo, valor_pago=valor_pago, anos_uso=anos_uso,
                                     revenda_atual=revenda_atual, condicao=condicao, saude_bateria=saude,
                                     atende=atende, gasto_anual=gasto)
    if atende == "nao":
        st.warning("Regra de prioridade: aparelho que **não atende** leva ao veredito **troca necessária**.")

with col_cat:
    st.subheader("Encontrado no catálogo")
    st.markdown(f"**{modelo}** · {linha['marca']} · segmento *{linha['segmento']}*")
    specs = pd.DataFrame({
        "Especificação": ["Câmera principal", "Processador", "Bateria", "RAM / armazenamento", "Sistema"],
        "Valor": [f"{linha['camera_mp']:g} MP", f"{linha['processador']} ({linha['clock_ghz']:g} GHz, "
                  f"spec score {linha['spec_score']:g})", f"{linha['bateria_mah']:g} mAh",
                  f"{linha['ram_gb']:g} GB / {linha['armazenamento_gb']:g} GB", linha["sistema"]],
    })
    st.dataframe(specs, hide_index=True, width="stretch")
    if isinstance(linha.get("campos_imputados"), str) and linha["campos_imputados"]:
        st.caption(f"⚠️ Imputado: {linha['campos_imputados']}")
    ui.fonte("specs da base Smartprix")

    h = ui.horizonte()
    atual = AparelhoAtual(**{k: v for k, v in st.session_state["atual"].items()})
    n = notas_atual(linha, atual, h, date.today(), p)
    w = normalizar_pesos(ui.pesos())
    adq = adequacao({**n, "seguranca": 0 if pd.isna(n["seguranca"]) else n["seguranca"]}, w)
    m1, m2 = st.columns(2)
    m1.metric("Nota de adequação atual", f"{adq:.1f} / 10")
    meses = n["meses_suporte"]
    m2.metric("Suporte restante", "—" if pd.isna(meses) else f"{max(meses, 0):.0f} meses")
    ui.fonte(f"adequação = soma ponderada das notas com os seus pesos (página Simulação), já com condição, "
             f"saúde da bateria e atendimento; suporte: {linha['fonte_fim_suporte']}")

    pos = posicao_mercado(cat, modelo)
    st.markdown("**Posição em relação ao mercado (catálogo)**")
    st.dataframe(pd.DataFrame([{"Critério": k.capitalize(), "Nota do modelo (0-10)": v["nota"],
                                "Modelos abaixo": f"{v['pct_modelos_abaixo']:.0f}%"} for k, v in pos.items()]),
                 hide_index=True, width="stretch")
    st.caption(f"Satisfação: {linha['satisfacao']:.1f}/10 — {linha['fonte_satisfacao']}")
    ui.fonte("sumarização por percentil no catálogo (nota de fábrica, sem os ajustes de uso)")

st.page_link("pages/2_simulacao.py", label="Próximo: simular a troca →", icon="🧮")
