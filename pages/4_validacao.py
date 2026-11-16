"""Página 4 — Validação: métricas das funções analíticas, sensibilidade e caso concreto."""
from dataclasses import asdict
from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import ui
from src.dados import RAIZ
from src.decisao import CRITERIOS, ROTULOS, AparelhoAtual, Compra
from src.validacao import curva, pontos_virada, sensibilidade

# Caso de referência (o mesmo de scripts/caso_concreto.py)
REF_ATUAL = AparelhoAtual("Samsung Galaxy A54 5G", 1650, 450, "boa", 85, "sim", 2300, 2)
REF_COMPRA = Compra("Samsung Galaxy S24 5G", 5400)
REF_H = 3


@st.cache_data(show_spinner=False)
def _sens(atual_d: dict, compra_d: dict, pesos: dict, h: int, versao: str, hoje: date):
    return sensibilidade(AparelhoAtual(**atual_d), Compra(**compra_d), pesos, h, ui.cat(), ui.params(), hoje)


@st.cache_data(show_spinner=False)
def _viradas(atual_d: dict, compra_d: dict, pesos: dict, h: int, versao: str, hoje: date):
    return pontos_virada(AparelhoAtual(**atual_d), Compra(**compra_d), pesos, h, ui.cat(), ui.params(), hoje)


@st.cache_data(show_spinner=False)
def _curva(atual_d: dict, compra_d: dict, pesos: dict, h: int, versao: str, hoje: date, param: str):
    return curva(AparelhoAtual(**atual_d), Compra(**compra_d), pesos, h, ui.cat(), ui.params(), hoje, param)

st.title("✅ Validação do modelo")
m = ui.metricas()
if not m:
    st.error("Métricas não encontradas. Rode `python scripts/gerar_analitica.py`.")
    st.stop()
st.caption(f"Métricas geradas em {m.get('gerado_em', '—')} por `scripts/gerar_analitica.py`.")

aba = st.tabs(["Sumarização", "Agrupamento", "Regressão", "Classificação", "Sensibilidade", "Caso concreto"])

with aba[0]:
    s = m["sumarizacao"]
    st.markdown("**Entrada:** specs brutas do catálogo. **Processamento:** percentil de cada modelo no catálogo "
                "(0-10). Processamento = média dos percentis de *spec score* e *clock*. "
                "**Resultado decisório:** notas objetivas que alimentam o TOPSIS e a posição do aparelho no mercado.")
    st.metric("Modelos no catálogo", s["n_modelos"])
    pm = pd.DataFrame(s["por_marca"])
    cols = ["marca", "n"] + [c for c in pm.columns if c.endswith("_mean") and c.startswith("nota")]
    st.dataframe(pm[cols].rename(columns=lambda c: c.replace("nota_", "").replace("_mean", " (média)")),
                 hide_index=True, width="stretch")
    if s["imputacoes"]:
        st.caption("Imputações: " + "; ".join(f"{i['modelo']}: {i['campos_imputados']}" for i in s["imputacoes"]))
    st.caption("Limitação: MP e mAh brutos favorecem aparelhos com números altos de ficha técnica e penalizam "
               "topo de linha compactos (ex.: iPhones), pois a base não traz métricas de qualidade.")

with aba[1]:
    a = m["agrupamento"]
    st.markdown("**Entrada:** as 4 notas de specs. **Processamento:** k-means, k de 3 a 6 pela silhueta. "
                "**Resultado decisório:** alternativas do mesmo segmento do aparelho pretendido.")
    sil = a["silhueta_por_k"]
    fig = go.Figure(go.Bar(x=[f"k={k}" for k in sil], y=list(sil.values()),
                           marker=dict(color=[ui.AZUL if int(k) == a["k_escolhido"] else ui.CINZA for k in sil],
                                       cornerradius=4),
                           text=[f"{v:.3f}" for v in sil.values()], textposition="outside",
                           hovertemplate="%{x}: silhueta %{y:.3f}<extra></extra>"))
    st.plotly_chart(ui._layout(fig, f"Silhueta por k (escolhido: k={a['k_escolhido']})", 280), width="stretch")
    for seg in a["segmentos"]:
        with st.expander(f"{seg['nome']} — {seg['n']} modelos"):
            st.write("Centro: " + ", ".join(f"{k} {v:.1f}" for k, v in seg["centro"].items()))
            st.write(", ".join(seg["modelos"]))

with aba[2]:
    r = m["regressao"]
    st.markdown("**Entrada:** base de usados (preços em escala log → razão = exp(log usado − log novo)), "
                "anos de uso e specs. **Processamento:** linear × random forest, validação cruzada de 5 folds; "
                "curva razão(t) = a·(1 − d)^t. **Resultado decisório:** `a` e `d` substituem a taxa fixa de 30% "
                "(que fica como fallback configurável).")
    comp = pd.DataFrame(r["comparacao_cv5"]).T.reset_index(names="Modelo")
    comp["Escolhido"] = np.where(comp["Modelo"] == r["modelo_escolhido"], "✔", "")
    st.dataframe(comp, hide_index=True, width="stretch")
    cg = r["curva_global"]
    t = np.linspace(0.25, 5, 40)
    obs = r["razao_mediana_observada_por_anos_uso"]
    fig = go.Figure()
    fig.add_scatter(x=t, y=cg["a"] * (1 - cg["d"]) ** t, mode="lines", name="Curva ajustada a·(1−d)^t",
                    line=dict(color=ui.AZUL, width=2),
                    hovertemplate="%{x:.1f} anos: %{y:.2f}<extra>ajustada</extra>")
    fig.add_scatter(x=[0.5, 1.5, 2.5], y=list(obs.values()), mode="markers", name="Mediana observada (0-1, 1-2, 2-3 anos)",
                    marker=dict(color=ui.LARANJA, size=10), hovertemplate="%{x} anos: %{y:.2f}<extra>observada</extra>")
    fig.add_vrect(x0=3, x1=5, fillcolor="rgba(128,128,128,0.12)", line_width=0,
                  annotation_text="extrapolação", annotation_position="top left")
    fig.update_yaxes(range=[0, 1], title="Preço usado / preço novo")
    fig.update_xaxes(title="Anos de uso")
    st.plotly_chart(ui._layout(fig, f"Depreciação: a = {cg['a']:.2f}, d = {cg['d']:.1%} ao ano", 340), width="stretch")
    st.dataframe(pd.DataFrame(r["por_segmento_usado_na_decisao"]).rename(columns={
        "segmento": "Segmento", "fator_revenda_inicial": "a (revenda logo após a compra)",
        "taxa_depreciacao": "d (taxa anual)"}), hide_index=True, width="stretch")
    st.caption("Importância das variáveis: " + ", ".join(f"{k} {v:.2f}" for k, v in
                                                         list(r["importancia_ou_coeficientes"].items())[:6]))
    for lim in r["limitacoes"]:
        st.caption("Limitação: " + lim)

with aba[3]:
    c = m["classificacao"]
    st.markdown("**Entrada:** texto das reviews da Amazon (notas 4–5 positivas, 1–2 negativas, 3 descartadas). "
                "**Processamento:** TF-IDF + regressão logística com classes balanceadas; treino/teste 80/20 "
                "estratificado. **Resultado decisório:** % de reviews positivas por marca × 10 = critério satisfação.")
    k = st.columns(4)
    k[0].metric("Acurácia", f"{c['acuracia']:.1%}", help=f"Baseline (classe majoritária): {c['baseline_classe_majoritaria']:.1%}")
    k[1].metric("Acurácia balanceada", f"{c['acuracia_balanceada']:.1%}")
    k[2].metric("F1 macro", f"{c['f1_macro']:.3f}")
    k[3].metric("Reviews (teste)", f"{c['n_teste']:,}".replace(",", "."))
    cm = np.array(c["matriz_confusao"]["linhas_real_colunas_previsto"])
    fig = go.Figure(go.Heatmap(z=cm, x=["Prevista negativa", "Prevista positiva"],
                               y=["Real negativa", "Real positiva"], colorscale=[[0, "#cde2fb"], [1, "#184f95"]],
                               text=cm, texttemplate="%{text:,}", showscale=False,
                               hovertemplate="%{y} / %{x}: %{z:,}<extra></extra>"))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    st.plotly_chart(ui._layout(fig, "Matriz de confusão (conjunto de teste)", 300), width="stretch")
    pm = pd.DataFrame(c["por_marca"])
    pm = pm[pm["marca_norm"].isin(["apple", "samsung", "motorola", "xiaomi", "realme"])]
    st.dataframe(pm.rename(columns={"marca_norm": "Marca", "n_reviews": "Reviews", "satisfacao": "Satisfação (0-10)",
                                    "prop_positiva_prevista": "% positivas (previsto)",
                                    "prop_positiva_observada": "% positivas (observado, sem notas 3)"})
                 .drop(columns=["n_rotuladas"]), hide_index=True, width="stretch")
    st.caption("Xiaomi e Realme não têm reviews suficientes (mínimo de "
               f"{c['min_reviews_por_marca']}): satisfação simulada pela média do catálogo até o preenchimento manual.")
    st.caption("Termos mais positivos: " + ", ".join(c["termos_mais_positivos"][:10]))
    st.caption("Termos mais negativos: " + ", ".join(c["termos_mais_negativos"][:10]))

with aba[4]:
    st.markdown("**Pergunta:** o veredito resiste a mudanças razoáveis nas preferências e nos parâmetros? "
                "Cada peso é variado em **±20%** (com renormalização) e a taxa de depreciação `d` de todos os modelos "
                "em **±10 pontos percentuais**. Margem = proximidade TOPSIS da melhor troca comparável − proximidade "
                "de manter: margem positiva favorece trocar.")
    tem_sim = "atual" in st.session_state and "compra" in st.session_state
    opcoes = (["Minha simulação"] if tem_sim else []) + ["Caso de referência (A54 → S24, R$ 5.400, 3 anos)"]
    escolha = st.radio("Cenário analisado", opcoes, horizontal=True)
    if escolha == "Minha simulação":
        atual_d, compra_d = st.session_state["atual"], st.session_state["compra"]
        pesos_s, h_s = dict(ui.pesos()), ui.horizonte()
    else:
        atual_d, compra_d, pesos_s, h_s = asdict(REF_ATUAL), asdict(REF_COMPRA), dict(ui.PESOS_PADRAO), REF_H
    chave = (atual_d, compra_d, pesos_s, h_s, ui.versao_parametros(), date.today())

    with st.spinner("Recalculando o modelo em cada cenário..."):
        s_ = _sens(*chave)
    b = s_["base"]
    k = st.columns(3)
    k[0].metric("Veredito base", b["veredito"])
    k[1].metric("Cenários com o mesmo veredito", f"{s_['pct_cenarios_mesmo_veredito']:.0%}")
    k[2].metric("Cenários com o mesmo 1º lugar", f"{s_['pct_cenarios_mesmo_primeiro']:.0%}")
    if b["regra"]:
        st.info("O veredito deste cenário vem de uma **regra** (suporte ou 'não atende'): pesos e `d` não o alteram.")

    tab = pd.concat([s_["pesos"], s_["depreciacao"]], ignore_index=True)
    st.dataframe(pd.DataFrame({
        "Parâmetro": tab["parametro"], "Variação": tab["variacao"], "Veredito": tab["veredito"],
        "Mantém veredito": tab["mantem_veredito"].map({True: "✔", False: "✘"}),
        "1º lugar": tab["primeiro"], "Mantém 1º": tab["mantem_primeiro"].map({True: "✔", False: "✘"}),
        "Margem": tab["margem"].round(3), "Saldo": tab["saldo"].map(ui.brl),
    }), hide_index=True, width="stretch")

    st.markdown("#### Ponto de virada do veredito")
    st.caption("Varre um parâmetro por vez (41 pontos) e mostra onde o veredito muda. Para os pesos, o eixo é a "
               "parcela do critério no total; os demais pesos são redistribuídos na proporção original.")
    nomes = {c: ROTULOS[c] for c in CRITERIOS} | {"d": "Taxa de depreciação d", "preco": "Preço do pretendido"}
    param = st.selectbox("Parâmetro", list(nomes), format_func=nomes.get, index=list(nomes).index("custo"))
    with st.spinner("Varrendo o parâmetro..."):
        cv = _curva(*chave, param)
    if param in CRITERIOS:
        x, atual_x, titulo_x = cv["valor"] * 100, ui.normalizar(pesos_s)[param] * 100, "Parcela do peso (%)"
    elif param == "d":
        x, atual_x, titulo_x = cv["valor"] * 100, 0.0, "Deslocamento de d (pontos percentuais)"
    else:
        x, atual_x, titulo_x = cv["valor"], compra_d["preco"], "Preço do pretendido (R$)"
    fig = go.Figure()
    fig.add_scatter(x=x, y=cv["margem"], mode="lines", line=dict(color=ui.AZUL, width=2), name="Margem",
                    customdata=cv["veredito"], hovertemplate="%{x:.1f}: margem %{y:.3f}<br>%{customdata}<extra></extra>")
    fig.add_hline(y=0, line_color="rgba(128,128,128,0.8)", line_width=1)
    fig.add_vline(x=atual_x, line_dash="dot", line_color=ui.LARANJA,
                  annotation_text="valor atual", annotation_position="top")
    fig.update_xaxes(title=titulo_x)
    fig.update_yaxes(title="Margem (> 0 favorece trocar)")
    st.plotly_chart(ui._layout(fig, f"Margem do TOPSIS × {nomes[param].lower()}", 340), width="stretch")
    st.caption("Com regras acionadas, o veredito é 'troca necessária' em toda a faixa, mesmo com margem negativa.")

    if st.button("Calcular todos os pontos de virada"):
        with st.spinner("Varrendo os 9 parâmetros (alguns segundos)..."):
            st.session_state["viradas"] = _viradas(*chave)
    pv = st.session_state.get("viradas")
    if pv is not None:
        def _fmt(chv, v):
            if pd.isna(v):
                return "—"
            return ui.brl(v) if chv == "preco" else (f"{v * 100:+.0f} p.p." if chv == "d" else f"{v:.0%}")
        st.dataframe(pd.DataFrame({
            "Parâmetro": pv["parametro"],
            "Valor atual": [_fmt(c, v) if c != "d" else "0 p.p." for c, v in zip(pv["chave"], pv["valor_atual"])],
            "Virada em": [_fmt(c, v) for c, v in zip(pv["chave"], pv["valor_virada"])],
            "Novo veredito": pv["novo_veredito"].fillna(pv["observacao"]),
        }), hide_index=True, width="stretch")

with aba[5]:
    doc = RAIZ / "docs" / "caso_concreto.md"
    if doc.exists():
        st.caption("Documento gerado por `python scripts/caso_concreto.py` (mesmas funções do app).")
        st.markdown(doc.read_text(encoding="utf-8"))
    else:
        st.warning("Rode `python scripts/caso_concreto.py` para gerar o documento.")
