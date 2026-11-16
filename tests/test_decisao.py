import numpy as np
import pandas as pd
import pytest

from src.decisao import (BENEFICIO, CUSTO, MANTER, TROCA_NECESSARIA, VALE_TROCAR, AparelhoAtual,
                         Compra, Parametros, PerfilFrota, avaliar, custo_manter, custo_trocar,
                         meses_restantes, normalizar_pesos, nota_seguranca, plano_frota, saldo,
                         saldo_ano_a_ano, topsis, total_pago)

PESOS = {"camera": 15, "processamento": 15, "bateria": 15, "seguranca": 15,
         "armazenamento": 10, "satisfacao": 10, "custo": 20}


# ---------------------------------------------------------------- caso de referência
def test_caso_referencia_gasto_unico():
    """Caso da proposta: R_atual0 = 1.650; T = 5.400; G = 450 (gasto ÚNICO); d = 0,30;
    revenda do novo partindo do preço (a = 1) -> saldos −675, −1.463, −2.014."""
    esperado = {1: -675, 2: -1463, 3: -2014}
    for h, s in esperado.items():
        cm = custo_manter(450, h, 1650, 0.30, g_anual=False)
        ct = custo_trocar(5400, 1650, 5400 * 1.0, 0.30, h)
        assert round(saldo(cm, ct)) == s


def test_caso_referencia_gasto_anual():
    """Diferença documentada: no protótipo G é ANUAL (G_ano × H).
    Em H = 1 nada muda; a partir de H = 2 o custo de manter cresce 450/ano:
    saldos −675; −1.012,50; −1.113,75."""
    tab = saldo_ano_a_ano(450, 1650, 0.30, 5400, 5400, 0.30, anos=range(1, 4))
    assert tab["saldo"].tolist() == pytest.approx([-675.0, -1012.5, -1113.75])


def test_total_pago_parcelado():
    assert total_pago(5000) == 5000
    assert total_pago(5000, parcelado=True, n_parcelas=12, valor_parcela=450) == 5400


def test_fator_revenda_inicial_reduz_revenda_do_novo():
    """Com a < 1 (queda imediata estimada pela regressão), trocar fica mais caro."""
    sem_queda = custo_trocar(5400, 1650, 5400 * 1.0, 0.05, 2)
    com_queda = custo_trocar(5400, 1650, 5400 * 0.6, 0.05, 2)
    assert com_queda > sem_queda


# ---------------------------------------------------------------- regras
def test_suporte_acabando_em_5_meses_troca_necessaria(cat_sintetico, hoje):
    atual = AparelhoAtual("Alfa Velho", revenda_atual=400, gasto_anual=0, condicao="otima",
                          saude_bateria=100, atende="totalmente")
    assert meses_restantes("2027-04", hoje) == 5
    r = avaliar(atual, Compra("Delta Basico", 1200), PESOS, 2, cat_sintetico, hoje=hoje)
    assert r.veredito == TROCA_NECESSARIA
    assert r.regra_aplicada == "suporte"
    assert not r.recomendado.startswith("Manter")


def test_nao_atende_troca_necessaria(cat_sintetico, hoje):
    atual = AparelhoAtual("Beta Medio", revenda_atual=2000, atende="nao")
    r = avaliar(atual, Compra("Alfa Top", 5000), PESOS, 2, cat_sintetico, hoje=hoje)
    assert r.veredito == TROCA_NECESSARIA and r.regra_aplicada == "nao_atende"


def test_aparelho_novo_bem_avaliado_e_adequado_mantem(cat_sintetico, hoje):
    atual = AparelhoAtual("Alfa Top", revenda_atual=3500, gasto_anual=0, condicao="otima",
                          saude_bateria=100, atende="totalmente")
    r = avaliar(atual, Compra("Beta Medio", 4500), PESOS, 3, cat_sintetico, hoje=hoje)
    assert r.veredito == MANTER
    assert r.indicadores["posicao_manter"] == 1


def test_aparelho_ruim_e_mal_avaliado_vale_trocar(cat_sintetico, hoje):
    atual = AparelhoAtual("Delta Basico", revenda_atual=300, gasto_anual=400, condicao="ruim",
                          saude_bateria=60, atende="parcialmente")
    r = avaliar(atual, Compra("Eta Basico", 1300), PESOS, 3, cat_sintetico, hoje=hoje)
    assert r.veredito == VALE_TROCAR


def test_ajustes_do_atual(cat_sintetico, hoje):
    """bateria × saúde × condição; 'parcialmente' reduz benefícios em 15%."""
    base = AparelhoAtual("Beta Medio", 2000, condicao="otima", saude_bateria=100, atende="sim")
    pior = AparelhoAtual("Beta Medio", 2000, condicao="regular", saude_bateria=80, atende="parcialmente")
    rb = avaliar(base, Compra("Gama Medio", 4800), PESOS, 2, cat_sintetico, hoje=hoje).tabela
    rp = avaliar(pior, Compra("Gama Medio", 4800), PESOS, 2, cat_sintetico, hoje=hoje).tabela
    nb, npr = rb.loc["Manter: Beta Medio"], rp.loc["Manter: Beta Medio"]
    assert npr["bateria"] == pytest.approx(nb["bateria"] * 0.75 * 0.80 * 0.85)
    assert npr["camera"] == pytest.approx(nb["camera"] * 0.75 * 0.85)
    assert npr["armazenamento"] == pytest.approx(nb["armazenamento"] * 0.85)


# ---------------------------------------------------------------- pesos e TOPSIS
def test_pesos_que_nao_somam_100_sao_normalizados():
    w = normalizar_pesos({"camera": 30, "processamento": 30, "bateria": 30, "seguranca": 30,
                          "armazenamento": 30, "satisfacao": 30, "custo": 30})
    assert sum(w.values()) == pytest.approx(1.0)
    assert w["camera"] == pytest.approx(1 / 7)
    w2 = normalizar_pesos({"camera": 2, "custo": 6})
    assert w2["custo"] == pytest.approx(0.75) and w2["bateria"] == 0
    assert sum(normalizar_pesos({}).values()) == pytest.approx(1.0)


def test_topsis_alternativas_identicas_nao_quebra():
    m = pd.DataFrame([{c: 5.0 for c in BENEFICIO} | {"custo": 1000.0}] * 3, index=list("ABC"))
    r = topsis(m, normalizar_pesos(PESOS), BENEFICIO, CUSTO)
    assert np.isfinite(r["proximidade"]).all()
    assert (r["proximidade"] == 0.5).all()


def test_topsis_dominancia_e_custo_negativo():
    """A domina B em tudo -> A em 1º; custo negativo é tratado sem inverter a ordem."""
    m = pd.DataFrame([{c: 8.0 for c in BENEFICIO} | {"custo": -500.0},
                      {c: 4.0 for c in BENEFICIO} | {"custo": 900.0}], index=["A", "B"])
    r = topsis(m, normalizar_pesos(PESOS), BENEFICIO, CUSTO)
    assert r.loc["A", "posicao"] == 1 and r.loc["A", "proximidade"] == pytest.approx(1.0)


def test_nota_seguranca():
    assert nota_seguranca(36, 3) == 10
    assert nota_seguranca(18, 3) == 5
    assert nota_seguranca(-4, 2) == 0


# ---------------------------------------------------------------- frota
def _perfis():
    return [
        PerfilFrota("Campo/vendas", 20, "Alfa Velho", 400, 100, "regular", 70, "sim",
                    {"bateria": 30, "seguranca": 25, "custo": 25, "processamento": 10, "camera": 10}),
        PerfilFrota("Executivo", 5, "Beta Medio", 2000, 0, "boa", 90, "sim",
                    {"processamento": 25, "camera": 20, "seguranca": 20, "satisfacao": 15, "custo": 20}),
    ]


def test_frota_respeita_max_modelos_e_suporte(cat_sintetico, hoje):
    r = plano_frota(_perfis(), orcamento=1e6, h=3, cat=cat_sintetico, hoje=hoje,
                    suporte_minimo_meses=36, max_modelos=2)
    assert len(r["modelos_escolhidos"]) <= 2
    assert "Alfa Velho" not in r["elegiveis"]          # suporte < 36 meses
    plano = r["plano"].set_index("perfil")
    assert plano.loc["Campo/vendas", "decisao"] == TROCA_NECESSARIA
    trocados = plano.loc[plano["decisao"] != MANTER, "modelo_recomendado"]
    assert set(trocados) <= set(r["modelos_escolhidos"])
    assert r["cabe_no_orcamento"]


def test_frota_orcamento_insuficiente_prioriza_troca_obrigatoria(cat_sintetico, hoje):
    r = plano_frota(_perfis(), orcamento=5000, h=3, cat=cat_sintetico, hoje=hoje,
                    suporte_minimo_meses=36, max_modelos=2)
    plano = r["plano"].set_index("perfil")
    assert not r["cabe_no_orcamento"]
    assert plano.loc["Campo/vendas", "prioridade"] == 1
    assert r["custo_financiado"] <= 5000
    assert plano.loc["Campo/vendas", "aparelhos_adiados"] > 0


def test_veredito_vem_so_das_comparaveis(cat_sintetico, hoje):
    """O ranking do catálogo inteiro é informativo: não altera a tabela da decisão."""
    atual = AparelhoAtual("Beta Medio", 2000, 100, "boa", 90, "sim")
    r = avaliar(atual, Compra("Gama Medio", 4800), PESOS, 3, cat_sintetico, hoje=hoje)
    assert set(r.tabela["modelo"]) <= {"Beta Medio", "Gama Medio", "Alfa Top"}   # cluster 1, preço ±30%
    assert len(r.ranking_completo) == len(cat_sintetico)                          # manter + 5 outros
    assert "Delta Basico" in r.ranking_completo.index and "Delta Basico" not in r.tabela.index
