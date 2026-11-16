"""Fase 1 — gera data/catalogo_br.csv a partir da Smartprix + arquivos manuais.

Fluxo:
  1. Seleciona os modelos de SELECAO (linhas globais vendidas no Brasil).
  2. Para cada modelo, usa a variante base (menor armazenamento, depois menor
     preço); specs ausentes nessa variante são completadas com as de outras
     variantes do MESMO aparelho (mesmo chip/câmera/bateria).
  3. Junta preço (data/precos_ml.csv, se existir, sobrescrito por
     data/precos_manuais.csv), suporte (data/suporte_manual.csv) e avaliações
     (data/avaliacoes_manuais.csv).
  4. Cria os arquivos manuais como modelos vazios (sem apagar o que já foi
     preenchido) e gera data/pendencias.csv com tudo o que falta.

Nunca inventa valores: o que não existe fica vazio e vai para as pendências.
Uso: python scripts/gerar_catalogo.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from src.dados import (  # noqa: E402
    ARQ_AVAL_ML, ARQ_AVALIACOES, ARQ_CATALOGO, ARQ_PENDENCIAS, ARQ_PRECOS_MANUAIS, ARQ_PRECOS_ML,
    ARQ_SUPORTE, carregar_smartprix,
)

# Nome na Smartprix -> marca exibida. Curadoria: linhas globais vendidas no
# Brasil, cobrindo entrada, intermediário e topo de cada marca. Ficaram de fora
# séries exclusivas da Índia (Galaxy M/F, Realme Narzo/P, Redmi Prime/Power).
SELECAO = {
    "Apple": [
        "Apple iPhone 11", "Apple iPhone 12", "Apple iPhone 13", "Apple iPhone 14",
        "Apple iPhone 15", "Apple iPhone 15 Plus", "Apple iPhone 15 Pro", "Apple iPhone 15 Pro Max",
    ],
    "Samsung": [
        "Samsung Galaxy A05", "Samsung Galaxy A05s", "Samsung Galaxy A14 5G", "Samsung Galaxy A15 5G",
        "Samsung Galaxy A25 5G", "Samsung Galaxy A34 5G", "Samsung Galaxy A35 5G", "Samsung Galaxy A54 5G",
        "Samsung Galaxy A55 5G", "Samsung Galaxy S23 FE 5G", "Samsung Galaxy S23 5G", "Samsung Galaxy S24 5G",
        "Samsung Galaxy S24 Ultra", "Samsung Galaxy Z Flip 5",
    ],
    "Motorola": [
        "Motorola Moto E13", "Motorola Moto G04", "Motorola Moto G14", "Motorola Moto G34 5G",
        "Motorola Moto G54 5G", "Motorola Moto G84 5G", "Motorola Edge 40 Neo", "Motorola Edge 50 Fusion",
        "Motorola Edge 50 Pro", "Motorola Razr 40",
    ],
    "Xiaomi": [
        "Xiaomi Redmi A3", "Xiaomi Redmi 13C", "Xiaomi Redmi Note 12", "Xiaomi Redmi Note 13 5G",
        "Xiaomi Redmi Note 13 Pro 5G", "Xiaomi Redmi Note 13 Pro Plus 5G", "Poco X6 5G", "Poco X6 Pro 5G",
        "Poco F5", "Xiaomi 14",
    ],
    "Realme": [
        "Realme C51", "Realme C53", "Realme C55", "Realme C67 5G", "Realme 11 Pro Plus",
        "Realme 12 Pro Plus 5G",
    ],
}

COLS_PRECOS = ["modelo", "preco_brl", "data_coleta", "fonte_preco", "observacao"]
COLS_AVAL = ["modelo", "nota_media", "n_avaliacoes", "data_coleta", "fonte_avaliacao"]
COLS_SUPORTE = ["modelo", "fim_suporte", "fonte_fim_suporte"]


def _num(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie.astype(str).str.strip(), errors="coerce")


def specs_smartprix() -> pd.DataFrame:
    sp = carregar_smartprix()
    nomes = [n for lista in SELECAO.values() for n in lista]
    faltando = sorted(set(nomes) - set(sp["name"]))
    if faltando:
        raise SystemExit(f"Modelos da SELECAO ausentes na Smartprix: {faltando}")
    sp = sp[sp["name"].isin(nomes)].copy()

    sp["camera_mp"] = _num(sp["primary_camera_rear"])
    sp["clock_ghz"] = _num(sp["clock_speed"])
    sp["bateria_mah"] = _num(sp["battery_power(in mAh)"])
    sp["ram_gb"] = _num(sp["RAM(in GB)"])
    # A coluna ROM perde a unidade (1 TB vira 1.0); o texto de `ram` a mantém.
    arm = sp["ram"].str.extract(r"(\d+(?:\.\d+)?)\s*(GB|TB|MB)\s*inbuilt", expand=True)
    fator = arm[1].map({"GB": 1, "TB": 1024, "MB": 1 / 1024})
    sp["armazenamento_gb"] = pd.to_numeric(arm[0], errors="coerce") * fator
    sp["processador"] = sp["processor"].str.split(",").str[0].str.strip()
    # filtros de sanidade (valores fora disso são erros de alinhamento da base)
    sp.loc[~sp["camera_mp"].between(2, 250), "camera_mp"] = pd.NA
    sp.loc[~sp["clock_ghz"].between(1, 4.5), "clock_ghz"] = pd.NA
    sp.loc[~sp["bateria_mah"].between(1000, 8000), "bateria_mah"] = pd.NA
    sp.loc[~sp["ram_gb"].between(1, 24), "ram_gb"] = pd.NA

    linhas = []
    for nome, g in sp.groupby("name"):
        base = g.sort_values(["armazenamento_gb", "price"]).iloc[0].copy()
        # completa specs ausentes com outras variantes do mesmo aparelho
        for c in ["camera_mp", "clock_ghz", "bateria_mah", "spec_score"]:
            if pd.isna(base[c]):
                base[c] = g[c].dropna().max() if g[c].notna().any() else pd.NA
        versao = g["os"][g["os"].str.startswith("Android")]
        linhas.append({
            "modelo": nome.replace("Xiaomi ", "") if nome.startswith("Xiaomi Redmi") else nome,
            "nome_smartprix": nome,
            "marca": next(m for m, lst in SELECAO.items() if nome in lst),
            "camera_mp": base["camera_mp"],
            "processador": base["processador"],
            "clock_ghz": base["clock_ghz"],
            "spec_score": base["spec_score"],
            "bateria_mah": base["bateria_mah"],
            "ram_gb": base["ram_gb"],
            "armazenamento_gb": base["armazenamento_gb"],
            "sistema": "iOS" if nome.startswith("Apple") else "Android",
            "versao_sistema": versao.iloc[0] if len(versao) else pd.NA,
            "tem_5g": bool(g["has_5g"].any()),
            "tela_pol": base["screen_size"],
            "preco_inr_ref": base["price"],
            "variantes_smartprix": len(g),
        })
    return pd.DataFrame(linhas)


def garantir_manual(caminho: Path, colunas: list[str], modelos: list[str]) -> pd.DataFrame:
    """Cria/atualiza um CSV manual sem apagar valores já preenchidos."""
    if caminho.exists():
        atual = pd.read_csv(caminho, dtype=str)
    else:
        atual = pd.DataFrame(columns=colunas)
    novos = [m for m in modelos if m not in set(atual["modelo"])]
    if novos:
        atual = pd.concat([atual, pd.DataFrame({"modelo": novos})], ignore_index=True)
    atual = atual.reindex(columns=colunas)
    atual.to_csv(caminho, index=False, encoding="utf-8")
    return atual


def main() -> None:
    cat = specs_smartprix()
    modelos = cat["modelo"].tolist()

    precos = garantir_manual(ARQ_PRECOS_MANUAIS, COLS_PRECOS, modelos)
    aval = garantir_manual(ARQ_AVALIACOES, COLS_AVAL, modelos)
    sup = garantir_manual(ARQ_SUPORTE, COLS_SUPORTE, modelos)

    # Preço: coleta do ML (se houver) e, por cima, o preenchimento manual.
    preco = pd.DataFrame({"modelo": modelos})
    preco[["preco_brl", "data_preco", "fonte_preco"]] = pd.NA
    if ARQ_PRECOS_ML.exists():
        ml = pd.read_csv(ARQ_PRECOS_ML).set_index("modelo")
        for c_dst, c_src in [("preco_brl", "preco_brl"), ("data_preco", "data_coleta")]:
            preco[c_dst] = preco["modelo"].map(ml[c_src])
        preco.loc[preco["preco_brl"].notna(), "fonte_preco"] = "Mercado Livre (API, mediana anúncios novos)"
    man = precos.set_index("modelo")
    tem_man = preco["modelo"].map(_num(man["preco_brl"])).notna()
    preco.loc[tem_man, "preco_brl"] = preco.loc[tem_man, "modelo"].map(_num(man["preco_brl"]))
    preco.loc[tem_man, "data_preco"] = preco.loc[tem_man, "modelo"].map(man["data_coleta"])
    preco.loc[tem_man, "fonte_preco"] = preco.loc[tem_man, "modelo"].map(man["fonte_preco"]).fillna("manual")

    cat = cat.merge(preco, on="modelo", how="left")
    cat = cat.merge(sup[COLS_SUPORTE], on="modelo", how="left")
    # Avaliações: ML (se coletado) e, por cima, o preenchimento manual.
    av = pd.DataFrame({"modelo": modelos})
    av[["avaliacao_media", "avaliacao_n", "fonte_avaliacao"]] = pd.NA
    if ARQ_AVAL_ML.exists():
        aml = pd.read_csv(ARQ_AVAL_ML).set_index("modelo")
        av["avaliacao_media"] = av["modelo"].map(aml["nota_media"])
        av["avaliacao_n"] = av["modelo"].map(aml["n_avaliacoes"])
        av.loc[av["avaliacao_media"].notna(), "fonte_avaliacao"] = "Mercado Livre (API)"
    am = aval.set_index("modelo")
    tem = av["modelo"].map(_num(am["nota_media"])).notna()
    av.loc[tem, "avaliacao_media"] = av.loc[tem, "modelo"].map(_num(am["nota_media"]))
    av.loc[tem, "avaliacao_n"] = av.loc[tem, "modelo"].map(_num(am["n_avaliacoes"]))
    av.loc[tem, "fonte_avaliacao"] = av.loc[tem, "modelo"].map(am["fonte_avaliacao"]).fillna("manual")
    cat = cat.merge(av, on="modelo", how="left")

    status_ml = (pd.read_csv(ARQ_PRECOS_ML).set_index("modelo")["status"]
                 if ARQ_PRECOS_ML.exists() else pd.Series(dtype=str))

    # Colunas preenchidas na Fase 2 (funções analíticas).
    for c in ["cluster", "segmento", "nota_camera", "nota_processamento", "nota_bateria",
              "nota_armazenamento", "satisfacao", "fonte_satisfacao", "taxa_depreciacao"]:
        cat[c] = pd.NA

    cat.to_csv(ARQ_CATALOGO, index=False, encoding="utf-8")

    # Pendências
    pend = []
    regras = [
        ("preco_brl", "Preço à vista do aparelho novo (versão base) em R$",
         "data/precos_manuais.csv", "Amazon.com.br ou Mercado Livre; anotar data e link"),
        ("fim_suporte", "Fim do suporte de software/segurança (AAAA-MM)",
         "data/suporte_manual.csv", "Política oficial do fabricante; anotar link em fonte_fim_suporte"),
        ("avaliacao_media", "Nota média (0-5) e nº de avaliações",
         "data/avaliacoes_manuais.csv", "Página do produto no Mercado Livre ou Amazon.com.br"),
    ]
    for campo, oque, arq, fonte in regras:
        for m in cat.loc[cat[campo].isna(), "modelo"]:
            obs = "não encontrado no catálogo do ML" if status_ml.get(m) == "nao_encontrado_no_ml" else ""
            pend.append({"modelo": m, "campo": campo, "o_que_preencher": oque, "arquivo": arq,
                         "fonte_sugerida": fonte, "observacao": obs})
    for campo in ["camera_mp", "clock_ghz", "bateria_mah", "ram_gb", "armazenamento_gb"]:
        for m in cat.loc[cat[campo].isna(), "modelo"]:
            pend.append({"modelo": m, "campo": campo, "o_que_preencher": f"Spec ausente na Smartprix: {campo}",
                         "arquivo": "data/catalogo_br.csv (corrigir na base ou aceitar imputação)",
                         "fonte_sugerida": "Ficha técnica oficial do fabricante"})
    pd.DataFrame(pend).to_csv(ARQ_PENDENCIAS, index=False, encoding="utf-8")

    print(f"Catálogo: {len(cat)} modelos -> {ARQ_CATALOGO}")
    print(cat.groupby("marca").size().to_string())
    print(f"Pendências: {len(pend)} -> {ARQ_PENDENCIAS}")
    print(pd.DataFrame(pend).groupby("campo").size().to_string() if pend else "")


if __name__ == "__main__":
    main()
