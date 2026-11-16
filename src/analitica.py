"""Funções analíticas do TrocaCerta.

Cada função recebe dados de entrada, processa e devolve (resultado, métricas):
  1. sumarizar   — notas 0-10 por percentil + estatísticas por marca/cluster
  2. agrupar     — k-means com k escolhido pela silhueta (segmentos)
  3. depreciacao — regressão da razão preço_usado/preço_novo -> queda inicial a e taxa anual d
  4. satisfacao  — TF-IDF + regressão logística nas reviews -> satisfação 0-10 por marca
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestRegressor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (accuracy_score, balanced_accuracy_score, confusion_matrix,
                             f1_score, silhouette_score)
from sklearn.model_selection import KFold, cross_validate, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

SEED = 42
CRITERIOS_SPECS = ["nota_camera", "nota_processamento", "nota_bateria", "nota_armazenamento"]
ROTULOS = {"nota_camera": "câmera", "nota_processamento": "processamento",
           "nota_bateria": "bateria", "nota_armazenamento": "armazenamento"}


# ---------------------------------------------------------------- 1. SUMARIZAÇÃO
def percentil_0_10(serie: pd.Series) -> pd.Series:
    """Posição percentual dentro do catálogo (empates = média), em escala 0-10."""
    return (serie.rank(pct=True, method="average") * 10).round(2)


def sumarizar(cat: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Entrada: specs brutas. Saída: notas 0-10 por percentil e estatísticas descritivas.

    - câmera: megapixels da câmera traseira principal
    - processamento: média dos percentis de spec_score e clock (opção a)
    - bateria: mAh
    - armazenamento: GB internos
    Specs ausentes são imputadas pela mediana da marca e registradas em
    `campos_imputados` (nunca silenciosamente).
    """
    cat = cat.copy()
    if "campos_imputados" not in cat:
        cat["campos_imputados"] = ""
    cat["campos_imputados"] = cat["campos_imputados"].fillna("")
    for c in ["camera_mp", "clock_ghz", "spec_score", "bateria_mah", "armazenamento_gb"]:
        falta = cat[c].isna()
        if falta.any():
            cat.loc[falta, c] = cat.loc[falta, "marca"].map(cat.groupby("marca")[c].median())
            cat.loc[falta, "campos_imputados"] += f"{c} (mediana da marca);"

    cat["nota_camera"] = percentil_0_10(cat["camera_mp"])
    proc = (percentil_0_10(cat["spec_score"]) + percentil_0_10(cat["clock_ghz"])) / 2
    cat["nota_processamento"] = proc.round(2)
    cat["nota_bateria"] = percentil_0_10(cat["bateria_mah"])
    cat["nota_armazenamento"] = percentil_0_10(cat["armazenamento_gb"])

    specs = ["camera_mp", "spec_score", "clock_ghz", "bateria_mah", "ram_gb", "armazenamento_gb"]
    met = {
        "descricao": "Notas 0-10 = percentil do modelo dentro do catálogo.",
        "n_modelos": int(len(cat)),
        "imputacoes": cat.loc[cat["campos_imputados"] != "", ["modelo", "campos_imputados"]]
                        .to_dict("records"),
        "specs_catalogo": cat[specs].describe().round(2).to_dict(),
        "por_marca": estatisticas_grupo(cat, "marca"),
    }
    return cat, met


def estatisticas_grupo(cat: pd.DataFrame, grupo: str) -> dict:
    cols = CRITERIOS_SPECS + ["camera_mp", "bateria_mah", "armazenamento_gb", "preco_inr_ref"]
    g = cat.groupby(grupo)[cols].agg(["mean", "median", "min", "max"]).round(2)
    g.columns = [f"{a}_{b}" for a, b in g.columns]
    g.insert(0, "n", cat.groupby(grupo).size())
    return g.reset_index().to_dict("records")


def posicao_mercado(cat: pd.DataFrame, modelo: str) -> dict:
    """Posição do aparelho em relação ao mercado (catálogo): nota e % de modelos abaixo."""
    linha = cat.loc[cat["modelo"] == modelo].iloc[0]
    return {ROTULOS[c]: {"nota": float(linha[c]),
                         "pct_modelos_abaixo": round(float((cat[c] < linha[c]).mean() * 100), 1)}
            for c in CRITERIOS_SPECS}


# ---------------------------------------------------------------- 2. AGRUPAMENTO
def agrupar(cat: pd.DataFrame, ks=range(3, 7)) -> tuple[pd.DataFrame, dict]:
    """Entrada: notas de specs (já normalizadas 0-10). k-means com k em 3..6 pela silhueta.

    Clusters numerados pela nota média do centro; nome = perfil do centro.
    """
    cat = cat.copy()
    X = cat[CRITERIOS_SPECS].to_numpy()
    sil = {}
    modelos = {}
    for k in ks:
        km = KMeans(n_clusters=k, n_init=50, random_state=SEED).fit(X)
        sil[k] = float(silhouette_score(X, km.labels_))
        modelos[k] = km
    k_best = max(sil, key=sil.get)
    km = modelos[k_best]

    centros = pd.DataFrame(km.cluster_centers_, columns=CRITERIOS_SPECS)
    ordem = centros.mean(axis=1).sort_values().index.tolist()    # cluster mais fraco primeiro
    remap = {old: new for new, old in enumerate(ordem)}
    cat["cluster"] = pd.Series(km.labels_).map(remap).to_numpy()
    centros = centros.loc[ordem].reset_index(drop=True)

    # Nome pelo PERFIL (critério mais forte e mais fraco do centro), não por faixa:
    # com specs brutas (MP, mAh), topo de linha compactos têm notas baixas de câmera
    # e bateria, então "média das notas" não ordena por categoria de mercado.
    nomes = {}
    for c, linha in centros.iterrows():
        forte, fraco = ROTULOS[linha.idxmax()], ROTULOS[linha.idxmin()]
        nomes[c] = f"Forte em {forte}, fraco em {fraco}"
    cat["segmento"] = cat["cluster"].map(nomes)

    met = {
        "descricao": "k-means sobre as 4 notas de specs; k escolhido pela maior silhueta.",
        "silhueta_por_k": {str(k): round(v, 4) for k, v in sil.items()},
        "k_escolhido": int(k_best),
        "segmentos": [{"cluster": int(c), "nome": nomes[c],
                       "n": int((cat["cluster"] == c).sum()),
                       "centro": {ROTULOS[k]: round(float(v), 2) for k, v in centros.loc[c].items()},
                       "modelos": cat.loc[cat["cluster"] == c, "modelo"].tolist()}
                      for c in range(k_best)],
        "por_cluster": estatisticas_grupo(cat, "segmento"),
    }
    return cat, met


def alternativas_mesmo_segmento(cat: pd.DataFrame, modelo: str, preco_ref: float | None = None,
                                faixa: float = 0.30, maximo: int = 5) -> pd.DataFrame:
    """Modelos do mesmo cluster do pretendido; se preco_ref for dado, dentro de ±faixa do preço."""
    alvo = cat.loc[cat["modelo"] == modelo].iloc[0]
    alt = cat[(cat["cluster"] == alvo["cluster"]) & (cat["modelo"] != modelo)]
    if preco_ref is not None and "preco_brl" in alt:
        alt = alt[alt["preco_brl"].between(preco_ref * (1 - faixa), preco_ref * (1 + faixa))]
        alt = alt.assign(_dist=(alt["preco_brl"] - preco_ref).abs()).sort_values("_dist").drop(columns="_dist")
    return alt.head(maximo)


# ---------------------------------------------------------------- 3. REGRESSÃO
MARCAS_REG = ["Apple", "Samsung", "Motorola", "Xiaomi", "Realme"]
FEATS_REG = ["anos_uso", "preco_novo_log", "rear_camera_mp", "ram", "memoria_log", "battery", "tem_5g"] \
    + [f"marca_{m}" for m in MARCAS_REG]
GRADE_T = np.arange(0.5, 3.01, 0.25)  # anos dentro da faixa observada (0,25 a 3 anos)


def preparar_usados(u: pd.DataFrame) -> pd.DataFrame:
    """Base de usados: preços em LOG natural -> razão = exp(log_usado - log_novo)."""
    u = u.copy()
    u["razao"] = np.exp(u["normalized_used_price"] - u["normalized_new_price"])
    u["anos_uso"] = u["days_used"] / 365.25
    u["preco_novo_log"] = u["normalized_new_price"]
    u["memoria_log"] = np.log2(u["internal_memory"].clip(lower=1))
    u["tem_5g"] = (u["5g"] == "yes").astype(int)
    for m in MARCAS_REG:
        u[f"marca_{m}"] = (u["device_brand"] == m).astype(int)
    u = u.dropna(subset=FEATS_REG + ["razao"])
    return u


def _metricas_cv(modelo, X, y) -> dict:
    cv = KFold(n_splits=5, shuffle=True, random_state=SEED)
    r = cross_validate(modelo, X, y, cv=cv,
                       scoring=("r2", "neg_mean_absolute_error", "neg_root_mean_squared_error"))
    return {"R2": round(float(r["test_r2"].mean()), 4),
            "R2_dp": round(float(r["test_r2"].std()), 4),
            "MAE": round(float(-r["test_neg_mean_absolute_error"].mean()), 4),
            "RMSE": round(float(-r["test_neg_root_mean_squared_error"].mean()), 4)}


def features_catalogo(cat: pd.DataFrame, u: pd.DataFrame) -> pd.DataFrame:
    """Converte o catálogo para o espaço de features da base de usados.

    - preço novo: as moedas/épocas diferem, então usa-se a POSIÇÃO do preço
      (percentil do preco_inr_ref no catálogo -> mesmo quantil de preço novo na base de usados);
    - specs são limitadas à faixa observada na base (sem extrapolar).
    """
    f = pd.DataFrame(index=cat.index)
    pct = cat["preco_inr_ref"].rank(pct=True)
    f["preco_novo_log"] = np.quantile(u["preco_novo_log"], pct.clip(0, 1))
    lim = lambda col, s: s.clip(u[col].min(), u[col].max())  # noqa: E731
    f["rear_camera_mp"] = lim("rear_camera_mp", cat["camera_mp"])
    f["ram"] = lim("ram", cat["ram_gb"])
    f["memoria_log"] = lim("memoria_log", np.log2(cat["armazenamento_gb"]))
    f["battery"] = lim("battery", cat["bateria_mah"])
    f["tem_5g"] = cat["tem_5g"].astype(int)
    for m in MARCAS_REG:
        f[f"marca_{m}"] = (cat["marca"] == m).astype(int)
    return f


def ajustar_curva(t: np.ndarray, razao: np.ndarray) -> tuple[float, float]:
    """Ajusta ln(razão) = ln(a) + t·ln(1-d) por mínimos quadrados -> (a, d)."""
    b, ln_a = np.polyfit(t, np.log(razao), 1)
    return float(np.exp(ln_a)), float(1 - np.exp(b))


def depreciacao(u_raw: pd.DataFrame, cat: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Entrada: base de usados + catálogo. Processamento: linear × random forest (CV 5 folds).

    Resultado: para cada modelo do catálogo, prevê a razão usado/novo em uma
    grade de idades (0,5 a 3 anos) e ajusta razão(t) = a·(1-d)^t:
      a = fração do preço que resta logo após a compra (queda inicial)
      d = taxa de depreciação anual
    Agrega também por segmento (mediana).
    """
    u = preparar_usados(u_raw)
    X, y = u[FEATS_REG], u["razao"]
    candidatos = {
        "linear": make_pipeline(StandardScaler(), LinearRegression()),
        "random_forest": RandomForestRegressor(n_estimators=300, min_samples_leaf=5,
                                               random_state=SEED, n_jobs=-1),
    }
    comp = {nome: _metricas_cv(m, X, y) for nome, m in candidatos.items()}
    melhor = max(comp, key=lambda n: comp[n]["R2"])
    modelo = candidatos[melhor].fit(X, y)

    # curva empírica global (mediana observada por faixa de uso) para validação
    faixas = pd.cut(u["anos_uso"], [0, 1, 2, 3.1], labels=["0-1", "1-2", "2-3"])
    empirica = u.groupby(faixas, observed=True)["razao"].median().round(4).to_dict()

    fc = features_catalogo(cat, u)
    res = []
    for i in cat.index:
        grade = pd.DataFrame([fc.loc[i]] * len(GRADE_T)).assign(anos_uso=GRADE_T)[FEATS_REG]
        pred = np.clip(modelo.predict(grade), 0.01, 1.0)
        a, d = ajustar_curva(GRADE_T, pred)
        res.append({"a": round(a, 4), "d": round(d, 4)})
    res = pd.DataFrame(res, index=cat.index)
    cat = cat.copy()
    cat["fator_revenda_modelo"] = res["a"]      # referência (instável por modelo)
    cat["taxa_depreciacao_modelo"] = res["d"]
    # Valores usados na decisão: mediana do segmento (mais estável), d >= 0.
    grupo = cat["segmento"] if "segmento" in cat else pd.Series("todos", index=cat.index)
    cat["fator_revenda_inicial"] = cat.groupby(grupo)["fator_revenda_modelo"].transform("median").round(4)
    cat["taxa_depreciacao"] = cat.groupby(grupo)["taxa_depreciacao_modelo"].transform("median").clip(lower=0).round(4)

    # curva da base inteira (mesmo procedimento, sobre a mediana das previsões)
    a_g, d_g = ajustar_curva(
        GRADE_T, np.array([np.median(np.clip(modelo.predict(X.assign(anos_uso=t)), 0.01, 1)) for t in GRADE_T]))

    por_seg = (cat.groupby(grupo)[["fator_revenda_inicial", "taxa_depreciacao"]]
               .first().reset_index().to_dict("records"))
    negativos = cat.loc[cat["taxa_depreciacao_modelo"] < 0, "modelo"].tolist()

    imp = None
    if melhor == "random_forest":
        imp = dict(sorted(zip(FEATS_REG, modelo.feature_importances_.round(4).tolist()),
                          key=lambda t: -t[1]))
    else:
        lr = modelo[-1]
        imp = dict(zip(FEATS_REG, lr.coef_.round(4).tolist()))

    met = {
        "descricao": ("Alvo: razão preço_usado/preço_novo = exp(log_usado - log_novo) "
                      "(a base vem em escala logarítmica). Curva ajustada: razão(t) = a·(1-d)^t."),
        "n_amostras": int(len(u)),
        "features": FEATS_REG,
        "comparacao_cv5": comp,
        "modelo_escolhido": melhor,
        "importancia_ou_coeficientes": imp,
        "curva_global": {"a": round(a_g, 4), "d": round(d_g, 4)},
        "razao_mediana_observada_por_anos_uso": empirica,
        "d_por_modelo": cat["taxa_depreciacao_modelo"].describe().round(4).to_dict(),
        "a_por_modelo": cat["fator_revenda_modelo"].describe().round(4).to_dict(),
        "modelos_com_d_negativo": negativos,
        "por_segmento_usado_na_decisao": por_seg,
        "limitacoes": ["Base com aparelhos de 2013-2020 e no máximo 3 anos de uso: "
                       "horizontes de 4-5 anos são extrapolados pela curva.",
                       "Preço novo do catálogo entra pela posição relativa (percentil), "
                       "não pelo valor, por diferença de moeda e época."],
    }
    return cat, met


# ---------------------------------------------------------------- 4. CLASSIFICAÇÃO
MIN_REVIEWS_MARCA = 200


def satisfacao(reviews: pd.DataFrame, col_texto="Reviews", col_nota="Rating",
               col_marca="marca_norm") -> tuple[pd.DataFrame, dict]:
    """Entrada: texto + nota das reviews. Rótulo: 4-5 positivo, 1-2 negativo (3 descartado).

    TF-IDF (uni+bigramas) + regressão logística com class_weight='balanced'
    (trata o desbalanceamento); divisão treino/teste 80/20 estratificada.
    Textos duplicados são removidos antes da divisão (evita vazamento: a
    Amazon repete a mesma review em variantes de cor/capacidade).

    Resultado: proporção de reviews classificadas como positivas por marca,
    sobre TODAS as reviews da marca (inclusive as de nota 3), em escala 0-10.
    """
    r = reviews.dropna(subset=[col_texto]).copy()
    r[col_texto] = r[col_texto].astype(str).str.strip()
    r = r[r[col_texto].str.len() > 0].drop_duplicates(subset=[col_texto])
    rot = r[r[col_nota] != 3].copy()
    rot["y"] = (rot[col_nota] >= 4).astype(int)

    X_tr, X_te, y_tr, y_te = train_test_split(rot[col_texto], rot["y"], test_size=0.2,
                                              stratify=rot["y"], random_state=SEED)
    clf = make_pipeline(
        TfidfVectorizer(ngram_range=(1, 2), min_df=5, max_df=0.9, max_features=200_000,
                        sublinear_tf=True, strip_accents="unicode"),
        LogisticRegression(class_weight="balanced", max_iter=2000, C=4.0),
    )
    clf.fit(X_tr, y_tr)
    p = clf.predict(X_te)
    cm = confusion_matrix(y_te, p, labels=[0, 1])

    r["pred_pos"] = clf.predict(r[col_texto])
    marca = r.groupby(col_marca).agg(
        n_reviews=("pred_pos", "size"),
        prop_positiva_prevista=("pred_pos", "mean"),
    )
    obs = rot.groupby(col_marca)["y"].agg(prop_positiva_observada="mean", n_rotuladas="size")
    marca = marca.join(obs).reset_index()
    marca = marca[marca["n_reviews"] >= MIN_REVIEWS_MARCA].copy()
    marca["satisfacao"] = (marca["prop_positiva_prevista"] * 10).round(2)

    tfidf, lr = clf[0], clf[-1]
    vocab = np.array(tfidf.get_feature_names_out())
    ordem = np.argsort(lr.coef_[0])

    met = {
        "descricao": ("TF-IDF + regressão logística (class_weight=balanced). "
                      "Satisfação da marca = % de reviews previstas como positivas × 10."),
        "n_reviews_unicas": int(len(r)),
        "n_rotuladas": int(len(rot)),
        "prop_positivas_rotuladas": round(float(rot["y"].mean()), 4),
        "n_treino": int(len(X_tr)), "n_teste": int(len(X_te)),
        "acuracia": round(float(accuracy_score(y_te, p)), 4),
        "acuracia_balanceada": round(float(balanced_accuracy_score(y_te, p)), 4),
        "f1_macro": round(float(f1_score(y_te, p, average="macro")), 4),
        "f1_positiva": round(float(f1_score(y_te, p, pos_label=1)), 4),
        "f1_negativa": round(float(f1_score(y_te, p, pos_label=0)), 4),
        "baseline_classe_majoritaria": round(float(max(y_te.mean(), 1 - y_te.mean())), 4),
        "matriz_confusao": {"labels": ["negativa", "positiva"],
                            "linhas_real_colunas_previsto": cm.tolist()},
        "termos_mais_negativos": vocab[ordem[:15]].tolist(),
        "termos_mais_positivos": vocab[ordem[-15:]][::-1].tolist(),
        "min_reviews_por_marca": MIN_REVIEWS_MARCA,
        "por_marca": marca.round(4).to_dict("records"),
    }
    return marca, met
