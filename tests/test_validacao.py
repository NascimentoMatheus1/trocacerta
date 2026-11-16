import pandas as pd
import pytest

from src.decisao import CRITERIOS, MANTER, VALE_TROCAR, AparelhoAtual, Compra, Parametros, normalizar_pesos
from src.validacao import (cat_com_delta_d, curva, pesos_com_fator, pesos_com_parcela, ponto_virada,
                           pontos_virada, sensibilidade)

PESOS = {"camera": 15, "processamento": 15, "bateria": 15, "seguranca": 15,
         "armazenamento": 10, "satisfacao": 10, "custo": 20}


def test_pesos_com_fator_renormaliza():
    w = pesos_com_fator(PESOS, "custo", 1.2)
    assert sum(w.values()) == pytest.approx(1)
    assert w["custo"] > normalizar_pesos(PESOS)["custo"]


def test_pesos_com_parcela_mantem_proporcao_dos_demais():
    w = pesos_com_parcela(PESOS, "custo", 0.5)
    assert w["custo"] == pytest.approx(0.5) and sum(w.values()) == pytest.approx(1)
    assert w["camera"] / w["armazenamento"] == pytest.approx(15 / 10)


def test_delta_d_nunca_negativo(cat_sintetico):
    c = cat_com_delta_d(cat_sintetico, -0.5)
    assert (c["taxa_depreciacao"] >= 0).all()


def test_ponto_virada_localiza_fronteira_mais_proxima():
    cv = pd.DataFrame({"valor": [0.0, 0.1, 0.2, 0.3, 0.4],
                       "veredito": [VALE_TROCAR, MANTER, MANTER, MANTER, VALE_TROCAR]})
    pv = ponto_virada(cv, 0.15, MANTER)                        # fronteiras em 0,05 e 0,35 -> 0,05 é a mais próxima
    assert pv["valor_virada"] == pytest.approx(0.05) and pv["direcao"] == "reduzir"
    assert pv["novo_veredito"] == VALE_TROCAR
    pv2 = ponto_virada(cv, 0.3, MANTER)
    assert pv2["valor_virada"] == pytest.approx(0.35) and pv2["direcao"] == "aumentar"
    assert ponto_virada(cv.assign(veredito=MANTER), 0.2, MANTER) is None


def test_sensibilidade_estrutura(cat_sintetico, hoje):
    atual = AparelhoAtual("Beta Medio", 2000, 100, "boa", 90, "sim")
    s = sensibilidade(atual, Compra("Gama Medio", 4800), PESOS, 3, cat_sintetico, Parametros(), hoje)
    assert len(s["pesos"]) == 2 * len(CRITERIOS)               # ±20% para cada critério com peso > 0
    assert len(s["depreciacao"]) == 2                          # d ± 10 p.p.
    assert 0 <= s["pct_cenarios_mesmo_veredito"] <= 1


def test_regra_torna_veredito_insensivel(cat_sintetico, hoje):
    atual = AparelhoAtual("Alfa Velho", 400, 0, "otima", 100, "totalmente")   # suporte acaba em 5 meses
    s = sensibilidade(atual, Compra("Delta Basico", 1200), PESOS, 2, cat_sintetico, Parametros(), hoje)
    assert s["veredito_estavel"]
    pv = pontos_virada(atual, Compra("Delta Basico", 1200), PESOS, 2, cat_sintetico, Parametros(), hoje, passos=5)
    assert (pv["observacao"] == "veredito definido por regra").all()


def test_curva_preco_mais_barato_favorece_trocar(cat_sintetico, hoje):
    atual = AparelhoAtual("Beta Medio", 2000, 300, "boa", 80, "sim")
    cv = curva(atual, Compra("Gama Medio", 4800), PESOS, 3, cat_sintetico, Parametros(), hoje, "preco", passos=9)
    assert cv["margem"].iloc[0] >= cv["margem"].iloc[-1]       # preço menor -> margem maior
