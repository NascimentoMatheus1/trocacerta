# Caso concreto: passo a passo

Gerado por `scripts/caso_concreto.py` em 15/11/2026, com o catálogo e os parâmetros atuais. Os números saem das mesmas funções usadas pelo app.

> ⚠️ **Valores simulados neste caso** (modo demonstração): fim_suporte, preco_brl, satisfacao. Depois do preenchimento manual, rode o script de novo para atualizar os números.

## 1. Entradas do usuário

| Entrada | Valor |
|---|---|
| Aparelho atual | Samsung Galaxy A54 5G |
| Revenda atual (R_atual,0) | R$ 1.650,00 |
| Gasto previsto por ano (G_ano) | R$ 450,00 |
| Condição / saúde da bateria / atende | boa / 85% / sim |
| Modelo pretendido | Samsung Galaxy S24 5G |
| Total pago (T), à vista | R$ 5.400,00 |
| Horizonte (H) | 3 anos |
| Pesos (normalizados) | Câmera 15%, Processamento 15%, Bateria 15%, Segurança (suporte) 15%, Armazenamento 10%, Satisfação 10%, Custo líquido 20% |

## 2. Dados do catálogo

| modelo | segmento (k-means) | câmera | processamento | bateria | armazenamento | satisfação | a | d | fim do suporte | preço catálogo |
|---|---|---|---|---|---|---|---|---|---|---|
| Samsung Galaxy A54 5G | Forte em bateria, fraco em processamento | 5,310 | 6,520 | 6,350 | 4,480 | 6,840 | 0,739 | 0,030 | 2029-11 | R$ 2.050,00 |
| Samsung Galaxy S24 5G | Forte em armazenamento, fraco em bateria | 5,310 | 8,600 | 1,880 | 8,440 | 6,840 | 0,670 | 0,064 | 2029-11 | R$ 5.200,00 |

As notas vêm da **sumarização** (percentil no catálogo). `a` e `d` vêm da **regressão** (random forest, mediana do segmento). A satisfação vem do **classificador** (por marca). Fontes: preço: SIMULADO (preço Índia × câmbio 0.065); suporte: SIMULADO (hoje + 36 meses); satisfação: classificador (reviews Amazon, por marca).

## 3. Reprodução da fórmula da proposta

Parâmetros da proposta: `d` = 0,30, revenda do novo partindo do preço (`a` = 1) e G = 450 como **gasto único**.

| H | R_atual,H | C_manter = G − R_atual,H | R_novo,H | C_trocar = T − R_atual,0 − R_novo,H | Saldo |
|---|---|---|---|---|---|
| 1 | R$ 1.155,00 | −R$ 705,00 | R$ 3.780,00 | −R$ 30,00 | **−R$ 675,00** |
| 2 | R$ 808,50 | −R$ 358,50 | R$ 2.646,00 | R$ 1.104,00 | **−R$ 1.462,50** |
| 3 | R$ 565,95 | −R$ 115,95 | R$ 1.852,20 | R$ 1.897,80 | **−R$ 2.013,75** |

O resultado bate com o caso de referência: **−675; −1.463; −2.014** (arredondados). O teste `test_caso_referencia_gasto_unico` verifica esses valores.

## 4. Modelo financeiro do TrocaCerta

O protótipo trata G como **anual** e usa `a` e `d` estimados. Atual: d = 0,0305. Novo: a = 0,6697, d = 0,0636, logo R_novo,0 = R$ 5.400,00 × 0,6697 = R$ 3.616,38.

| H | R_atual,H | C_manter = G·H − R_atual,H | R_novo,H | C_trocar | Saldo |
|---|---|---|---|---|---|
| 1 | R$ 1.599,67 | −R$ 1.149,67 | R$ 3.386,38 | R$ 363,62 | **−R$ 1.513,30** |
| 2 | R$ 1.550,88 | −R$ 650,88 | R$ 3.171,00 | R$ 579,00 | **−R$ 1.229,88** |
| 3 | R$ 1.503,58 | −R$ 153,58 | R$ 2.969,33 | R$ 780,67 | **−R$ 934,25** |
| 4 | R$ 1.457,72 | R$ 342,28 | R$ 2.780,48 | R$ 969,52 | **−R$ 627,24** |
| 5 | R$ 1.413,26 | R$ 836,74 | R$ 2.603,64 | R$ 1.146,36 | **−R$ 309,62** |

Em H = 3, o saldo do pretendido é **−R$ 934,25** (manter sai mais barato). A queda imediata de valor do aparelho novo (`a` < 1) pesa contra a troca.

## 5. Ajustes do aparelho atual

- Fator de condição (boa) = 0,90, aplicado a câmera, processamento e bateria.
- Bateria × saúde: 6,35 × 0,90 × 0,85 = 4,86.
- Segurança = min(meses restantes, 12H)/(12H) × 10 = min(36, 36)/36 × 10 = 10,00.
- 'Atende = sim': sem redução.

## 6. Alternativas comparáveis

São o pretendido mais os modelos do mesmo segmento (k-means) com preço até ±30% de R$ 5.400,00, no máximo 6 contando *manter*: Manter: Samsung Galaxy A54 5G, Xiaomi 14, Samsung Galaxy S24 5G.

## 7. TOPSIS passo a passo

**7.1 Matriz de decisão** (notas de 0 a 10; custo em R$ no horizonte):

| Alternativa | Câmera | Processamento | Bateria | Segurança (suporte) | Armazenamento | Satisfação | Custo líquido |
|---|---|---|---|---|---|---|---|
| Manter: Samsung Galaxy A54 5G | 4,78 | 5,87 | 4,86 | 10,00 | 4,48 | 6,84 | -153,58 |
| Xiaomi 14 | 5,31 | 9,22 | 3,12 | 10,00 | 10,00 | 6,55 | 398,07 |
| Samsung Galaxy S24 5G | 5,31 | 8,60 | 1,88 | 10,00 | 8,44 | 6,84 | 780,67 |

Como há custo ≤ 0, o custo foi transladado para x − mín + 1 antes da normalização (mín = −R$ 153,58). A ordem se mantém.


**7.2 Matriz normalizada R = x / √(Σx²):**

| Alternativa | Câmera | Processamento | Bateria | Segurança (suporte) | Armazenamento | Satisfação | Custo líquido |
|---|---|---|---|---|---|---|---|
| Manter: Samsung Galaxy A54 5G | 0,5369 | 0,4219 | 0,8001 | 0,5774 | 0,3239 | 0,5855 | 0,0009 |
| Xiaomi 14 | 0,5965 | 0,6630 | 0,5139 | 0,5774 | 0,7230 | 0,5607 | 0,5087 |
| Samsung Galaxy S24 5G | 0,5965 | 0,6184 | 0,3096 | 0,5774 | 0,6102 | 0,5855 | 0,8609 |

**7.3 Matriz ponderada V = w × R:**

| Alternativa | Câmera | Processamento | Bateria | Segurança (suporte) | Armazenamento | Satisfação | Custo líquido |
|---|---|---|---|---|---|---|---|
| Manter: Samsung Galaxy A54 5G | 0,0805 | 0,0633 | 0,1200 | 0,0866 | 0,0324 | 0,0586 | 0,0002 |
| Xiaomi 14 | 0,0895 | 0,0994 | 0,0771 | 0,0866 | 0,0723 | 0,0561 | 0,1017 |
| Samsung Galaxy S24 5G | 0,0895 | 0,0928 | 0,0464 | 0,0866 | 0,0610 | 0,0586 | 0,1722 |

**7.4 Soluções ideais** (máximo nos benefícios e mínimo no custo para A+; o inverso para A−):

|  | Câmera | Processamento | Bateria | Segurança (suporte) | Armazenamento | Satisfação | Custo líquido |
|---|---|---|---|---|---|---|---|
| A+ (ideal positivo) | 0,0895 | 0,0994 | 0,1200 | 0,0866 | 0,0723 | 0,0586 | 0,0002 |
| A− (ideal negativo) | 0,0805 | 0,0633 | 0,0464 | 0,0866 | 0,0324 | 0,0561 | 0,1722 |
| peso w | 0,1500 | 0,1500 | 0,1500 | 0,1500 | 0,1000 | 0,1000 | 0,2000 |

**7.5 Distâncias e proximidade:**

| Alternativa | D+ | D− | C = D−/(D+ + D−) | posição |
|---|---|---|---|---|
| Manter: Samsung Galaxy A54 5G | 0,0546 | 0,1871 | 0,7741 | 1º |
| Xiaomi 14 | 0,1103 | 0,0942 | 0,4607 | 2º |
| Samsung Galaxy S24 5G | 0,1875 | 0,0421 | 0,1834 | 3º |

## 8. Regras e veredito

- Suporte do atual: 36 meses contra o limite de 6 → regra não acionada.
- Atende às necessidades: sim → regra não acionada.
- Sem regra acionada, vale o TOPSIS entre as comparáveis.

**Veredito: Manter o atual.** Manter o Samsung Galaxy A54 5G ficou acima de todas as alternativas comparáveis (mesmo segmento e faixa de preço) no TOPSIS (proximidade 0,774 contra 0,461 de Xiaomi 14).

| Indicador | Valor |
|---|---|
| Adequação atual | 6,20 / 10 |
| Adequação do Samsung Galaxy S24 5G | 6,75 / 10 |
| Ganho de adequação | 0,55 |
| Saldo em 3 anos | −R$ 934,25 |
| Custo por ponto ganho | R$ 1.703,34 |
| Posição de *manter* / do pretendido | 1º / 3º de 3 |

## 9. Análise de sensibilidade

Cada peso foi variado em ±20% (com renormalização) e a taxa `d` de todos os modelos em ±10 p.p. O veredito se manteve em **100%** dos cenários, e o 1º lugar do ranking em **100%**.

| Parâmetro | Variação | Veredito | 1º lugar | Margem (troca − manter) | Mantém? |
|---|---|---|---|---|---|
| Câmera | -20% | Manter o atual | Manter: Samsung Galaxy A54 5G | -0,3146 | sim |
| Câmera | +20% | Manter o atual | Manter: Samsung Galaxy A54 5G | -0,3119 | sim |
| Processamento | -20% | Manter o atual | Manter: Samsung Galaxy A54 5G | -0,3348 | sim |
| Processamento | +20% | Manter o atual | Manter: Samsung Galaxy A54 5G | -0,2898 | sim |
| Bateria | -20% | Manter o atual | Manter: Samsung Galaxy A54 5G | -0,3062 | sim |
| Bateria | +20% | Manter o atual | Manter: Samsung Galaxy A54 5G | -0,3214 | sim |
| Segurança (suporte) | -20% | Manter o atual | Manter: Samsung Galaxy A54 5G | -0,3134 | sim |
| Segurança (suporte) | +20% | Manter o atual | Manter: Samsung Galaxy A54 5G | -0,3134 | sim |
| Armazenamento | -20% | Manter o atual | Manter: Samsung Galaxy A54 5G | -0,3398 | sim |
| Armazenamento | +20% | Manter o atual | Manter: Samsung Galaxy A54 5G | -0,2849 | sim |
| Satisfação | -20% | Manter o atual | Manter: Samsung Galaxy A54 5G | -0,3133 | sim |
| Satisfação | +20% | Manter o atual | Manter: Samsung Galaxy A54 5G | -0,3134 | sim |
| Custo líquido | -20% | Manter o atual | Manter: Samsung Galaxy A54 5G | -0,2627 | sim |
| Custo líquido | +20% | Manter o atual | Manter: Samsung Galaxy A54 5G | -0,3519 | sim |
| Taxa de depreciação d (todos os modelos) | -10 p.p. | Manter o atual | Manter: Samsung Galaxy A54 5G | -0,1532 | sim |
| Taxa de depreciação d (todos os modelos) | +10 p.p. | Manter o atual | Manter: Samsung Galaxy A54 5G | -0,2807 | sim |

**Pontos de virada.** Cada parâmetro foi varrido sozinho até o veredito mudar. Para os pesos, o valor é a parcela do critério no total, com os demais pesos redistribuídos na proporção original:

| Parâmetro | Valor atual | Virada em | Novo veredito |
|---|---|---|---|
| Câmera (parcela do peso) | 15% | 70% | Vale a pena trocar |
| Processamento (parcela do peso) | 15% | 39% | Vale a pena trocar |
| Bateria (parcela do peso) | 15% | — | não vira na faixa testada |
| Segurança (suporte) (parcela do peso) | 15% | — | não vira na faixa testada |
| Armazenamento (parcela do peso) | 10% | 27% | Vale a pena trocar |
| Satisfação (parcela do peso) | 10% | — | não vira na faixa testada |
| Custo líquido (parcela do peso) | 20% | 4% | Vale a pena trocar |
| Taxa de depreciação d (deslocamento) | 0 p.p. | — | não vira na faixa testada |
| Preço do pretendido (R$) | R$ 5.400,00 | R$ 4.259,25 | Vale a pena trocar |

A grade tem 41 pontos por parâmetro. A virada é o ponto médio entre os dois pontos vizinhos da grade em que o veredito muda. Faixas testadas: pesos de 0% a 95%, `d` de −30 a +50 p.p., preço de 30% a 200% do informado.

