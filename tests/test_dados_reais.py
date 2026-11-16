"""Testes de integração com o catálogo real (modo demonstração)."""
from src.dados import carregar_catalogo
from src.decisao import AparelhoAtual, Compra, avaliar, plano_frota, PerfilFrota


def test_catalogo_completo_no_modo_demo(hoje):
    cat = carregar_catalogo(modo_demo=True, hoje=hoje)
    assert 30 <= len(cat) <= 50
    for c in ["preco_brl", "fim_suporte", "satisfacao", "nota_camera", "cluster", "taxa_depreciacao"]:
        assert cat[c].notna().all(), c
    assert (cat["taxa_depreciacao"] >= 0).all()


def test_avaliacao_com_catalogo_real(hoje):
    cat = carregar_catalogo(modo_demo=True, hoje=hoje)
    preco = float(cat.set_index("modelo").loc["Samsung Galaxy A55 5G", "preco_brl"])
    r = avaliar(AparelhoAtual("Samsung Galaxy A14 5G", 500, 150, "regular", 78, "parcialmente"),
                Compra("Samsung Galaxy A55 5G", preco), {"custo": 20, "bateria": 20, "camera": 10}, 3,
                cat, hoje=hoje)
    assert 2 <= len(r.tabela) <= 6                           # decisão: manter + comparáveis
    assert r.tabela["comparavel"].all()
    assert len(r.ranking_completo) == len(cat)               # informativo: manter + todo o catálogo
    assert set(cat["modelo"]) - {"Samsung Galaxy A14 5G"} <= set(r.ranking_completo.index)
    assert r.ranking_completo["proximidade"].is_monotonic_decreasing
    assert r.tabela["proximidade"].between(0, 1).all()
    assert len(r.saldo_anos) == 5


def test_frota_com_catalogo_real(hoje):
    cat = carregar_catalogo(modo_demo=True, hoje=hoje)
    perfis = [PerfilFrota("Operacional", 30, "Motorola Moto G04", 250, 80, "regular", 75, "sim",
                          {"custo": 40, "bateria": 25, "seguranca": 20, "processamento": 15})]
    r = plano_frota(perfis, 50_000, 3, cat, hoje=hoje, suporte_minimo_meses=24)
    assert len(r["modelos_escolhidos"]) <= 2
