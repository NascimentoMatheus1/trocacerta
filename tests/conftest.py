import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

HOJE = date(2026, 11, 15)


def _modelo(nome, cluster, preco, nota, fim, sat=7.0, d=0.06, a=0.7):
    return {"modelo": nome, "marca": nome.split()[0], "cluster": cluster, "preco_brl": preco,
            "nota_camera": nota, "nota_processamento": nota, "nota_bateria": nota,
            "nota_armazenamento": nota, "satisfacao": sat, "fim_suporte": fim,
            "fonte_fim_suporte": "teste", "fonte_satisfacao": "teste", "fonte_preco": "teste",
            "taxa_depreciacao": d, "fator_revenda_inicial": a}


@pytest.fixture
def cat_sintetico():
    """Catálogo pequeno e controlado (não depende dos dados reais)."""
    return pd.DataFrame([
        _modelo("Alfa Velho", 0, 1500, 3.0, "2027-04"),     # suporte acaba em 5 meses
        _modelo("Alfa Top", 1, 5000, 9.5, "2031-11", sat=9.0),
        _modelo("Beta Medio", 1, 4500, 6.0, "2030-11"),
        _modelo("Gama Medio", 1, 4800, 6.5, "2030-11"),
        _modelo("Delta Basico", 0, 1200, 4.0, "2029-11"),
        _modelo("Eta Basico", 0, 1300, 4.5, "2030-05"),
    ])


@pytest.fixture
def hoje():
    return HOJE
