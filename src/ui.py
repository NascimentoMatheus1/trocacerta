"""Utilitários compartilhados pelas páginas Streamlit: autenticação, cache, estado e gráficos."""
from __future__ import annotations

import hmac
import json
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.dados import PROCESSED, carregar_catalogo, carregar_parametros
from src.decisao import BENEFICIO, CRITERIOS, ROTULOS, Parametros

# Paleta de referência (validada): azul/vermelho = polaridade; azul/laranja = séries
AZUL, LARANJA, VERMELHO, CINZA = "#2a78d6", "#eb6834", "#e34948", "#8a8984"

PESOS_PADRAO = {"camera": 15, "processamento": 15, "bateria": 15, "seguranca": 15,
                "armazenamento": 10, "satisfacao": 10, "custo": 20}
CONDICOES = {"otima": "Ótima", "boa": "Boa", "regular": "Regular", "ruim": "Ruim"}
ATENDE = {"nao": "Não", "parcialmente": "Parcialmente", "sim": "Sim", "totalmente": "Totalmente"}


# ------------------------------------------------------------------ autenticação
def usuarios() -> dict:
    try:
        return {k: dict(v) for k, v in st.secrets["usuarios"].items()}
    except (KeyError, FileNotFoundError):
        return {}


def autenticar(usuario: str, senha: str) -> str | None:
    """Retorna o papel do usuário (consumidor, gestor, admin) ou None."""
    u = usuarios().get(usuario.strip().lower())
    if u and hmac.compare_digest(str(u.get("senha", "")), senha):
        return u.get("papel")
    return None


def exigir_papel(*papeis: str) -> None:
    if st.session_state.get("papel") not in papeis:
        st.error("Acesso restrito ao seu perfil.")
        st.stop()


# ------------------------------------------------------------------ dados
@st.cache_data(show_spinner=False)
def catalogo(_versao: str, hoje: date) -> pd.DataFrame:
    return carregar_catalogo(hoje=hoje)


def versao_parametros() -> str:
    return json.dumps(carregar_parametros(), sort_keys=True)


def cat() -> pd.DataFrame:
    return catalogo(versao_parametros(), date.today())


def params() -> Parametros:
    return Parametros.de_dict(carregar_parametros())


@st.cache_data(show_spinner=False)
def metricas() -> dict:
    arq = PROCESSED / "metricas.json"
    return json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}


def simulados(cat_df: pd.DataFrame, modelos: list[str]) -> list[str]:
    nomes = {"preco_brl": "preço", "fim_suporte": "fim do suporte", "satisfacao": "satisfação"}
    por_campo: dict[str, list[str]] = {}
    for m in dict.fromkeys(modelos):
        campos = cat_df.loc[cat_df["modelo"] == m, "campos_simulados"]
        for c in (campos.iloc[0] if len(campos) else "").split(";"):
            if c:
                por_campo.setdefault(nomes.get(c, c), []).append(m)
    return [f"{c} ({len(ms)} modelo{'s' if len(ms) > 1 else ''}: {', '.join(ms)})" for c, ms in por_campo.items()]


def aviso_demo() -> None:
    p = carregar_parametros()
    if p.get("modo_demo"):
        st.info("🧪 **Modo demonstração:** campos sem dado real usam valores **simulados**, sempre "
                "identificados como tal. " + p["demo"]["aviso"].split(":", 1)[-1].strip(), icon=None)


# ------------------------------------------------------------------ estado
def pesos() -> dict:
    if "pesos" not in st.session_state:
        st.session_state["pesos"] = dict(PESOS_PADRAO)
    return st.session_state["pesos"]


def normalizar(pesos: dict) -> dict:
    from src.decisao import normalizar_pesos
    return normalizar_pesos(pesos)


def horizonte() -> int:
    return int(st.session_state.get("horizonte", 3))


def fonte(texto: str) -> None:
    st.caption(f"ⓘ Fonte: {texto}")


# ------------------------------------------------------------------ formatação
def brl(v) -> str:
    from src.relatorio import brl as _brl
    return _brl(v)


def tabela_ranking(tab: pd.DataFrame) -> pd.DataFrame:
    t = tab.reset_index()
    tipo = {"manter": "Manter o atual", "pretendido": "Pretendido"}
    out = pd.DataFrame({
        "Posição": t["posicao"],
        "Alternativa": t["alternativa"],
        "Tipo": t["tipo"].map(tipo).fillna(""),
        "Comparável": t["comparavel"].map({True: "✔", False: ""}) if "comparavel" in t else "",
        "Preço": t["preco"].map(brl) if "preco" in t else "—",
        "Proximidade TOPSIS": t["proximidade"].round(3),
        "Adequação (0-10)": t["adequacao"].round(1),
        "Ganho": t["ganho_adequacao"].round(1),
        "Custo no horizonte": t["custo"].map(brl),
        "Saldo": t["saldo"].map(brl),
        "Suporte (meses)": t["meses_suporte"].map(lambda m: "—" if pd.isna(m) else f"{max(m, 0):.0f}"),
    })
    return out


# ------------------------------------------------------------------ gráficos
def _layout(fig: go.Figure, titulo: str, altura: int = 320) -> go.Figure:
    fig.update_layout(title=dict(text=titulo, x=0, font=dict(size=15)), height=altura,
                      margin=dict(l=8, r=8, t=48, b=8), bargap=0.35,
                      hoverlabel=dict(font_size=13), legend=dict(orientation="h", y=-0.15))
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.18)", zeroline=True,
                     zerolinecolor="rgba(128,128,128,0.6)", zerolinewidth=1)
    return fig


def grafico_saldo(saldo_anos: pd.DataFrame, h: int) -> go.Figure:
    cores = [AZUL if s >= 0 else VERMELHO for s in saldo_anos["saldo"]]
    opac = [1.0 if a == h else 0.55 for a in saldo_anos["ano"]]
    fig = go.Figure(go.Bar(
        x=[f"{a} ano" + ("s" if a > 1 else "") for a in saldo_anos["ano"]], y=saldo_anos["saldo"],
        marker=dict(color=cores, opacity=opac, cornerradius=4),
        customdata=saldo_anos[["custo_manter", "custo_trocar"]].map(brl).to_numpy(),
        text=[brl(s) if a == h else "" for a, s in zip(saldo_anos["ano"], saldo_anos["saldo"])],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>Saldo: R$ %{y:,.0f}<br>Manter: %{customdata[0]}"
                      "<br>Trocar: %{customdata[1]}<extra></extra>"))
    fig.update_yaxes(title="R$ (positivo = trocar sai mais barato)", tickformat=",.0f")
    return _layout(fig, "Saldo ano a ano (horizonte escolhido em destaque)")


def mostrar_ranking(tab: pd.DataFrame) -> None:
    """Ranking da decisão: manter + alternativas comparáveis."""
    st.dataframe(tabela_ranking(tab).drop(columns=["Comparável"]), hide_index=True, width="stretch")


def mostrar_ranking_catalogo(completo: pd.DataFrame) -> None:
    """Ranking informativo com o catálogo inteiro (TOPSIS independente)."""
    st.dataframe(tabela_ranking(completo), hide_index=True, width="stretch",
                 height=min(38 + 35 * len(completo), 600))
    st.caption(f"TOPSIS **separado** com {len(completo)} alternativas (manter + todo o catálogo), com os mesmos "
               "pesos e custos. ✔ = alternativas comparáveis usadas no veredito. É apenas uma referência de "
               "mercado: como o TOPSIS depende do conjunto avaliado (*rank reversal*), as posições aqui podem "
               "diferir das do ranking da decisão.")


def grafico_ranking(tab: pd.DataFrame, recomendado: str) -> go.Figure:
    t = tab.sort_values("proximidade")
    cores = [CINZA if tp == "manter" else AZUL for tp in t["tipo"]]
    fig = go.Figure(go.Bar(
        y=t.index, x=t["proximidade"], orientation="h",
        marker=dict(color=cores, cornerradius=4),
        text=[f"{v:.3f}".replace(".", ",") + ("  ★" if i == recomendado else "")
              for i, v in zip(t.index, t["proximidade"])],
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>Proximidade: %{x:.3f}<extra></extra>"))
    fig.update_xaxes(range=[0, 1.15], title="Proximidade à solução ideal (TOPSIS)")
    fig.update_yaxes(showgrid=False, zeroline=False)
    return _layout(fig, "Ranking TOPSIS (cinza = manter o atual; ★ = recomendado)", 60 + 48 * len(t))


def grafico_criterios(tab: pd.DataFrame, atual_idx: str, rec_idx: str) -> go.Figure:
    rot = [ROTULOS[c] for c in BENEFICIO]
    fig = go.Figure()
    for idx, cor, nome in [(atual_idx, LARANJA, f"Atual: {atual_idx.replace('Manter: ', '')}"),
                           (rec_idx, AZUL, f"Recomendado: {rec_idx}")]:
        fig.add_bar(y=rot, x=[tab.loc[idx, c] for c in BENEFICIO], name=nome, orientation="h",
                    marker=dict(color=cor, cornerradius=4),
                    hovertemplate="%{y}: %{x:.1f}<extra>" + nome + "</extra>")
    fig.update_layout(barmode="group", bargroupgap=0.12)
    fig.update_xaxes(range=[0, 10], title="Nota (0-10)")
    fig.update_yaxes(autorange="reversed", showgrid=False, zeroline=False)
    return _layout(fig, "Comparativo por critério", 380)


def editor_pesos(chave: str, pesos_ini: dict) -> dict:
    """Sliders 0-100 por critério; mostra a soma e os pesos normalizados (somam 100%)."""
    novos = {}
    cols = st.columns(2)
    for i, c in enumerate(CRITERIOS):
        novos[c] = cols[i % 2].slider(ROTULOS[c], 0, 100, int(pesos_ini.get(c, 0)), 5, key=f"{chave}_{c}")
    soma = sum(novos.values())
    if soma == 0:
        st.warning("Todos os pesos estão em zero: serão usados pesos iguais.")
    else:
        norm = " · ".join(f"{ROTULOS[c]} {v / soma:.0%}" for c, v in novos.items() if v)
        st.caption(f"Soma dos sliders: **{soma}** → normalizados para 100%: {norm}")
    return novos
