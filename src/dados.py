"""Carga, limpeza, normalização de nomes e matching entre bases.

Funções reaproveitadas pelos scripts de pipeline (scripts/) e pelo app.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz, process

RAIZ = Path(__file__).resolve().parents[1]
RAW = RAIZ / "data" / "raw"
PROCESSED = RAIZ / "data" / "processed"

ARQ_SMARTPRIX = RAW / "smartprix_cleaned_dataste_final.csv"
ARQ_AMAZON = RAW / "Amazon_Unlocked_Mobile.csv"
ARQ_USADOS = RAW / "used_device_data.csv"

DATA = RAIZ / "data"
ARQ_CATALOGO = DATA / "catalogo_br.csv"
ARQ_PENDENCIAS = DATA / "pendencias.csv"
ARQ_PRECOS_MANUAIS = DATA / "precos_manuais.csv"
ARQ_PRECOS_ML = DATA / "precos_ml.csv"          # gerado por scripts/coletar_ml.py
ARQ_AVALIACOES = DATA / "avaliacoes_manuais.csv"
ARQ_AVAL_ML = DATA / "avaliacoes_ml.csv"         # gerado por scripts/coletar_ml.py
ARQ_SUPORTE = DATA / "suporte_manual.csv"
ARQ_PARAMETROS = DATA / "parametros.json"

LIMIAR_MATCH = 85

# Marcas equivalentes: Redmi e Poco são submarcas da Xiaomi.
MAPA_MARCAS = {
    "redmi": "xiaomi",
    "poco": "xiaomi",
    "mi": "xiaomi",
    "lg electronics": "lg",
    "apple computer": "apple",
    "motorola mobility": "motorola",
    "moto": "motorola",
    "oneplus": "oneplus",
    "one plus": "oneplus",
}

CORES = [
    "space gray", "space grey", "rose gold", "jet black", "midnight black",
    "black", "white", "gold", "silver", "gray", "grey", "blue", "red", "green",
    "pink", "purple", "violet", "yellow", "orange", "bronze", "titanium",
    "graphite", "champagne", "midnight", "starlight", "coral", "lavender",
]

# Termos que não identificam o modelo (comerciais, operadora, conectividade).
RUIDO = [
    r"factory unlocked", r"unlocked", r"refurbished", r"certified", r"renewed",
    r"pre-?owned", r"international version", r"us version", r"global version",
    r"no warranty", r"\bsmart ?phone\b", r"\bcell ?phone\b", r"\bmobile phone\b", r"\bphone\b",
    r"\bcellular\b", r"\bwireless\b",
    r"dual sim", r"single sim", r"gsm", r"cdma", r"4g lte", r"lte", r"\b[345]g\b",
    r"at&t", r"verizon", r"t-mobile", r"sprint", r"cricket", r"boost mobile",
    r"straight talk", r"tracfone", r"metropcs", r"\bwith\b.*$", r"\bw/.*$",
    r"\bnew\b", r"\bused\b", r"\bversion\b", r"\bedition\b",
]


def normalizar_marca(marca: str | float) -> str:
    """Minúsculas, sem espaços extras, aplicando equivalências de submarcas."""
    if not isinstance(marca, str):
        return ""
    m = re.sub(r"\s+", " ", marca.strip().lower())
    return MAPA_MARCAS.get(m, m)


def normalizar_nome(nome: str | float) -> str:
    """Normaliza o nome do modelo para comparação.

    Remove: texto após ' - ' ou ',', parênteses/colchetes, capacidades (GB/TB),
    cores, termos comerciais/de operadora e códigos de modelo (ex.: SM-G930F).
    """
    if not isinstance(nome, str):
        return ""
    n = nome.lower()
    n = re.split(r"\s[-–|]\s|,", n)[0]          # descarta o "rabo" descritivo
    n = re.sub(r"\(.*?\)|\[.*?\]", " ", n)        # parênteses e colchetes
    n = re.sub(r"\d+(\.\d+)?\s*(gb|tb|mb)\b", " ", n)  # capacidades
    n = re.sub(r"\d+\s*mp\b", " ", n)             # megapixels
    for c in CORES:
        n = re.sub(rf"\b{c}\b", " ", n)
    for r in RUIDO:
        n = re.sub(r, " ", n)
    # códigos de modelo do fabricante: sm-g930f, g930a, xt1575, a1660...
    n = re.sub(r"\b(sm-)?[a-z]{1,3}-?\d{3,5}[a-z]{0,2}\b", " ", n)
    n = re.sub(r"[^a-z0-9+ ]", " ", n)
    return re.sub(r"\s+", " ", n).strip()


QUALIFICADORES = {"pro", "max", "plus", "ultra", "lite", "fe", "neo", "mini", "fusion",
                   "power", "prime", "flip", "fold", "edge", "note", "+", "s", "e", "se"}


def tokens_numericos(nome_norm: str) -> frozenset[str]:
    """Tokens que identificam o modelo e precisam coincidir exatamente:
    os que contêm dígitos ('s23', '15', 'a55') e os qualificadores de linha
    ('pro', 'max', 'plus'...), pois 'iPhone 15' ≠ 'iPhone 15 Pro'.
    """
    return frozenset(t for t in nome_norm.split()
                     if any(ch.isdigit() for ch in t) or t in QUALIFICADORES)


def carregar_smartprix() -> pd.DataFrame:
    df = pd.read_csv(ARQ_SMARTPRIX).drop(columns=["Unnamed: 0"], errors="ignore")
    df["marca_norm"] = df["brand_name"].map(normalizar_marca)
    df["nome_norm"] = df["name"].map(normalizar_nome)
    return df


def carregar_parametros() -> dict:
    with open(ARQ_PARAMETROS, encoding="utf-8") as f:
        return json.load(f)


def salvar_parametros(params: dict) -> None:
    with open(ARQ_PARAMETROS, "w", encoding="utf-8") as f:
        json.dump(params, f, ensure_ascii=False, indent=2)


def carregar_catalogo(modo_demo: bool | None = None, hoje: date | None = None) -> pd.DataFrame:
    """Lê data/catalogo_br.csv.

    No modo de demonstração, preenche SÓ os campos vazios com valores
    simulados e registra isso em `campos_simulados` e nas colunas de fonte:
      - preco_brl  = preco_inr_ref × câmbio (parâmetro demo.cambio_inr_brl)
      - fim_suporte = hoje + demo.meses_suporte_simulado
      - satisfacao  = média do catálogo (marcas sem reviews suficientes)
    Valores reais (preenchidos nos arquivos manuais) nunca são sobrescritos.
    """
    texto = ["fonte_preco", "data_preco", "fim_suporte", "fonte_fim_suporte", "fonte_avaliacao",
             "segmento", "fonte_satisfacao", "versao_sistema", "campos_imputados"]
    cat = pd.read_csv(ARQ_CATALOGO, dtype={c: "object" for c in texto})
    params = carregar_parametros()
    if modo_demo is None:
        modo_demo = params.get("modo_demo", False)
    cat["campos_simulados"] = ""
    if not modo_demo:
        return cat

    demo = params["demo"]
    hoje = hoje or date.today()
    sem_preco = cat["preco_brl"].isna()
    cat.loc[sem_preco, "preco_brl"] = (cat.loc[sem_preco, "preco_inr_ref"] * demo["cambio_inr_brl"]).round(-1)
    cat.loc[sem_preco, "fonte_preco"] = f"SIMULADO (preço Índia × câmbio {demo['cambio_inr_brl']})"
    cat.loc[sem_preco, "campos_simulados"] += "preco_brl;"

    sem_sup = cat["fim_suporte"].isna()
    m = hoje.year * 12 + (hoje.month - 1) + int(demo["meses_suporte_simulado"])
    cat["fim_suporte"] = cat["fim_suporte"].astype("object")
    cat.loc[sem_sup, "fim_suporte"] = f"{m // 12:04d}-{m % 12 + 1:02d}"
    cat.loc[sem_sup, "fonte_fim_suporte"] = f"SIMULADO (hoje + {demo['meses_suporte_simulado']} meses)"
    cat.loc[sem_sup, "campos_simulados"] += "fim_suporte;"

    sem_sat = cat["satisfacao"].isna()
    media = round(float(cat["satisfacao"].mean()), 2)
    cat.loc[sem_sat, "satisfacao"] = media
    cat.loc[sem_sat, "fonte_satisfacao"] = "SIMULADO (média do catálogo; marca sem reviews suficientes)"
    cat.loc[sem_sat, "campos_simulados"] += "satisfacao;"
    return cat


def carregar_amazon(colunas=None) -> pd.DataFrame:
    df = pd.read_csv(ARQ_AMAZON, usecols=colunas)
    return df


def casar_modelos(
    nomes_origem: pd.DataFrame,
    nomes_alvo: pd.DataFrame,
    limiar: int = LIMIAR_MATCH,
) -> pd.DataFrame:
    """Casa cada nome de origem com o melhor nome-alvo da MESMA marca.

    Ambos os DataFrames precisam das colunas: nome, marca_norm, nome_norm.
    Usa rapidfuzz.fuzz.token_sort_ratio; mantém só pares com score >= limiar.
    Restrição adicional: os tokens numéricos (número do modelo) devem ser
    idênticos — sem ela, 'galaxy s5' casa com 'galaxy s23' (score 91), pois a
    similaridade é por caracteres.
    """
    linhas = []
    for marca, grupo in nomes_origem.groupby("marca_norm"):
        alvos = nomes_alvo[nomes_alvo["marca_norm"] == marca]
        if alvos.empty or not marca:
            continue
        escolhas = dict(zip(alvos["nome"], alvos["nome_norm"]))
        num_alvo = {k: tokens_numericos(v) for k, v in escolhas.items()}
        for _, r in grupo.iterrows():
            if not r["nome_norm"]:
                continue
            num = tokens_numericos(r["nome_norm"])
            cands = {k: v for k, v in escolhas.items() if num_alvo[k] == num}
            if not cands:
                continue
            res = process.extractOne(
                r["nome_norm"], cands, scorer=fuzz.token_sort_ratio, score_cutoff=limiar
            )
            if res:
                _, score, nome_alvo = res
                linhas.append({
                    "nome_origem": r["nome"], "nome_origem_norm": r["nome_norm"],
                    "nome_alvo": nome_alvo, "nome_alvo_norm": escolhas[nome_alvo],
                    "marca": marca, "score": round(score, 1),
                })
    return pd.DataFrame(linhas)
