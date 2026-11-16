"""TrocaCerta — Sistema de Apoio à Decisão para troca de smartphones.

Entrada do Streamlit: login (usuários em st.secrets) e navegação por papel:
  consumidor -> modo consumidor (aparelho atual, simulação, relatório, validação)
  gestor     -> modo frota (plano de renovação, validação)
  admin      -> administração + todas as páginas
Executar: streamlit run app.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st  # noqa: E402

from src import ui  # noqa: E402

st.set_page_config(page_title="TrocaCerta", page_icon="📱", layout="wide")


def tela_login() -> None:
    st.title("📱 TrocaCerta")
    st.write("Sistema de apoio à decisão: **vale a pena trocar de smartphone ou manter o atual?**")
    if not ui.usuarios():
        st.error("Nenhum usuário configurado. Crie `.streamlit/secrets.toml` a partir de "
                 "`.streamlit/secrets.toml.example` (ou configure os secrets no Streamlit Cloud).")
        st.stop()
    with st.form("login"):
        usuario = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        ok = st.form_submit_button("Entrar", type="primary")
    if ok:
        papel = ui.autenticar(usuario, senha)
        if papel:
            st.session_state.update(usuario=usuario.strip().lower(), papel=papel)
            st.rerun()
        else:
            st.error("Usuário ou senha inválidos.")
    st.caption("Credenciais de teste no README: **consumidor** (modo consumidor), "
               "**gestor** (modo frota) e **admin** (administração).")


if "papel" not in st.session_state:
    st.navigation([st.Page(tela_login, title="Entrar", icon="🔐")]).run()
    st.stop()

papel = st.session_state["papel"]
inicial = {"consumidor": "atual", "gestor": "frota"}.get(papel, "admin")
PAGINAS = {
    "atual": ("pages/1_aparelho_atual.py", "Aparelho atual", "📱"),
    "sim": ("pages/2_simulacao.py", "Simulação", "🧮"),
    "rel": ("pages/3_relatorio.py", "Relatório", "📄"),
    "frota": ("pages/6_frota.py", "Plano da frota", "🏢"),
    "val": ("pages/4_validacao.py", "Validação", "✅"),
    "admin": ("pages/5_admin.py", "Administração", "⚙️"),
}
P = {k: st.Page(arq, title=t, icon=i, default=(k == inicial)) for k, (arq, t, i) in PAGINAS.items()}
if papel == "consumidor":
    nav = {"Modo consumidor": [P["atual"], P["sim"], P["rel"]], "Sobre o modelo": [P["val"]]}
elif papel == "gestor":
    nav = {"Modo frota": [P["frota"]], "Sobre o modelo": [P["val"]]}
else:
    nav = {"Administração": [P["admin"]], "Modo consumidor": [P["atual"], P["sim"], P["rel"]],
           "Modo frota": [P["frota"]], "Sobre o modelo": [P["val"]]}

with st.sidebar:
    st.markdown(f"**TrocaCerta** · {st.session_state['usuario']} ({papel})")
    if st.button("Sair"):
        st.session_state.clear()
        st.rerun()

st.navigation(nav).run()
