# TrocaCerta

**Sistema de apoio à decisão (SAD) para a troca de smartphones.** Protótipo acadêmico.

O TrocaCerta ajuda a decidir se **vale a pena trocar o smartphone atual por um novo ou manter o atual**. A resposta tem três partes:

1. **Saldo financeiro em reais** no horizonte escolhido, de 1 a 5 anos, com a evolução ano a ano.
2. **Ranking TOPSIS** com as alternativas. Uma delas é *manter o atual*.
3. **Veredito com justificativa em texto:** *troca necessária*, *vale a pena trocar* ou *manter o atual*.

A decisão é **semiestruturada** (Gorry & Scott Morton, 1971). O cálculo financeiro é objetivo, mas os pesos dos critérios dependem de quem decide.

A arquitetura e o diagrama de fluxo de dados estão em [docs/arquitetura.md](docs/arquitetura.md).

## Modos de uso

O login define o modo. Os dois modos usam o mesmo motor de decisão (regras, modelo financeiro e TOPSIS).

| Modo | Usuário | Para quem | Saída |
|---|---|---|---|
| **Consumidor** | `consumidor` | Uma pessoa decidindo sobre o próprio aparelho, com pesos livres | Veredito, saldo, ranking e relatório |
| **Frota** | `gestor` | Um gestor de TI renovando os celulares corporativos | Plano de renovação por perfil de uso, respeitando orçamento, suporte mínimo e no máximo 2 modelos |
| **Administração** | `admin` | Quem mantém o sistema | Edição de parâmetros, catálogo e pendências de dados |

## Credenciais de teste

| Usuário | Senha |
|---|---|
| `consumidor` | `consumidor123` |
| `gestor` | `gestor123` |
| `admin` | não publicada: solicite ao autor |

As senhas ficam em `st.secrets`, nunca no código. O usuário `admin` altera parâmetros do modelo, por isso a senha dele não é divulgada. Na instância publicada, defina uma senha forte para o admin nos secrets do Streamlit Cloud.

## Como rodar localmente

Requisitos: Python 3.11 ou superior.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    |    Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

# credenciais de login
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # depois edite as senhas

streamlit run app.py
```

O app abre em http://localhost:8501. **Não é preciso rodar os pipelines:** os dados processados que o app usa já estão no repositório (`data/catalogo_br.csv` e `data/processed/`).

### Testes

```bash
python -m pytest -q
```

Os testes cobrem o caso de referência da proposta, a análise de sensibilidade e os pontos de virada, as regras de troca obrigatória, a normalização dos pesos, o TOPSIS (inclusive com alternativas idênticas), o modo frota (orçamento e limite de modelos) e a integração com o catálogo real.

## Como gerar os dados processados

Só é necessário para reconstruir o catálogo ou as métricas. As bases brutas não vão para o repositório, por causa do tamanho: baixe-as e coloque-as em `data/raw/`.

| Arquivo em `data/raw/` | Base | Uso |
|---|---|---|
| `smartprix_cleaned_dataste_final.csv` | Smartprix (specs de smartphones, preços em INR) | Specs do catálogo |
| `Amazon_Unlocked_Mobile.csv` | Amazon Reviews: Unlocked Mobile Phones (EUA) | Classificador de satisfação |
| `used_device_data.csv` | Used Phones & Tablets Pricing Dataset | Regressão de depreciação |

```bash
python scripts/fase0_matching.py        # (opcional) relatório do matching Smartprix × Amazon
python scripts/gerar_catalogo.py        # catálogo + arquivos manuais + pendências
python scripts/gerar_analitica.py       # 4 funções analíticas -> catálogo e metricas.json
# depois de preencher dados manuais, sem retreinar o classificador (cerca de 30 s a menos):
python scripts/gerar_analitica.py --pular-classificador
```

### Dados preenchidos manualmente

As bases não trazem preço no Brasil, fim do suporte de software nem avaliações em português. Esses dados vêm de três arquivos que você preenche. O gerador nunca apaga o que já foi preenchido.

| Arquivo | Campos | Fonte sugerida |
|---|---|---|
| `data/precos_manuais.csv` | `preco_brl`, `data_coleta`, `fonte_preco` | Amazon.com.br ou Mercado Livre |
| `data/suporte_manual.csv` | `fim_suporte` (AAAA-MM), `fonte_fim_suporte` | Política oficial de cada fabricante |
| `data/avaliacoes_manuais.csv` | `nota_media` (0–5), `n_avaliacoes` | Página do produto no ML ou na Amazon.com.br |

O arquivo `data/pendencias.csv` lista tudo o que falta.

Enquanto houver campos vazios, o **modo demonstração** (`"modo_demo": true` em `data/parametros.json`) preenche os valores com estimativas **simuladas** e as identifica em todo o app:

- preço: preço na Índia × câmbio;
- fim do suporte: hoje + 36 meses;
- satisfação: média do catálogo.

### Coleta automática no Mercado Livre (opcional)

O script `scripts/coletar_ml.py` usa a API oficial e grava os resultados em `data/precos_ml.csv` e `data/avaliacoes_ml.csv`. Os valores manuais têm prioridade sobre os coletados.

- **Preços:** mediana dos anúncios novos, obtida pelo catálogo de produtos.
- **Avaliações:** coletadas apenas se o endpoint estiver liberado para o app.
- **Boas práticas:** pausa entre chamadas, backoff no erro 429, cache local e nenhum dado pessoal coletado.

O app publicado **não** chama a API: ele lê apenas os CSVs.

```bash
cp .env.example .env          # preencha ML_CLIENT_ID e ML_CLIENT_SECRET
python scripts/coletar_ml.py --testar   # testa o token e os endpoints com 1 modelo
python scripts/coletar_ml.py            # coleta o catálogo inteiro
python scripts/gerar_catalogo.py && python scripts/gerar_analitica.py --pular-classificador
```

## Funções analíticas

As métricas de todas as funções estão em `data/processed/metricas.json` e na página **Validação** do app.

| Função | Entrada | Processamento | Resultado decisório |
|---|---|---|---|
| **Sumarização** | Specs brutas do catálogo | Percentil de cada modelo no catálogo (0–10) para câmera, processamento, bateria e armazenamento. Estatísticas por marca e por segmento | Notas objetivas para o TOPSIS e posição do aparelho no mercado |
| **Agrupamento** | Notas de specs | k-means com k entre 3 e 6, escolhido pela silhueta (k = 3, silhueta 0,36) | Alternativas do mesmo segmento do aparelho pretendido |
| **Regressão** | Base de usados (preços em escala log) | Regressão linear × random forest, com validação cruzada de 5 folds. Random forest: R² 0,60, MAE 0,079, RMSE 0,100. Ajuste da curva razão(t) = a·(1−d)^t | Fator de revenda inicial `a` e taxa anual `d` por segmento. Substituem a taxa fixa de 30%, que fica como fallback |
| **Classificação** | Texto das reviews da Amazon | TF-IDF + regressão logística com classes balanceadas e divisão 80/20 estratificada. Acurácia 0,941, F1 macro 0,931 | % de reviews positivas por marca × 10, usado como critério de satisfação |

## Modelo de decisão (`src/decisao.py`)

### Modelo financeiro

| Grandeza | Fórmula |
|---|---|
| Total pago | `T` = preço à vista, ou `n` × parcela |
| Revenda do aparelho atual no horizonte | `R_atual,H = R_atual,0 · (1 − d)^H` |
| Revenda do aparelho novo no horizonte | `R_novo,H = preço · a · (1 − d)^H` |
| Custo de manter | `C_manter = G_ano · H − R_atual,H` |
| Custo de trocar | `C_trocar = T − R_atual,0 − R_novo,H` |
| Saldo | `Saldo(H) = C_manter − C_trocar` (positivo: trocar sai mais barato) |

### Regras

As regras têm prioridade sobre o ranking:

- Se o suporte do aparelho atual acaba em menos de N meses (N = 6 por padrão), o veredito é **troca necessária**.
- Se o aparelho atual **não atende** às necessidades, o veredito é **troca necessária**.
- Fora dessas regras, o veredito é **vale a pena trocar** se alguma alternativa **comparável** ficar acima de *manter* no TOPSIS. Caso contrário, é **manter o atual**.

### TOPSIS

- **Critérios de benefício:** câmera, processamento, bateria, segurança, armazenamento e satisfação.
- **Critério de custo:** custo líquido no horizonte.
- **Método:** normalização vetorial, soluções ideais positiva e negativa, distância euclidiana.
- **Alternativas da decisão:** *manter*, o pretendido e os modelos do mesmo segmento com preço ±30%, no máximo 6 alternativas. Esse TOPSIS gera o veredito.
- **Relatório completo:** ao ser aberto pelo usuário, mostra um segundo TOPSIS, só informativo, com *manter* e **todos os aparelhos do catálogo**. Ele não altera o veredito.
- **No modo frota:** o ranking de cada perfil inclui todos os modelos com o suporte mínimo exigido.
- **Segurança:** `min(meses de suporte restantes, 12H) / 12H × 10`.

### Ajustes do aparelho atual

- A nota de bateria é multiplicada pela saúde da bateria (%).
- A condição do aparelho multiplica câmera, processamento e bateria por um fator: ótima 1,0; boa 0,9; regular 0,75; ruim 0,5.
- "Atende parcialmente" reduz todas as notas de benefício em 15%.

As referências acadêmicas de cada fórmula estão em [docs/referencias.md](docs/referencias.md).

### Caso de referência da proposta

Dados: `R_atual,0` = 1.650; `T` = 5.400; `G` = 450; `d` = 0,30; `a` = 1.

| Horizonte | Saldo com G como gasto único (proposta) | Saldo com G anual (protótipo) |
|---|---|---|
| 1 ano | −675 | −675,00 |
| 2 anos | −1.463 | −1.012,50 |
| 3 anos | −2.014 | −1.113,75 |

As duas versões estão cobertas por testes.

## Validação

A página **Validação** do app e o documento [docs/caso_concreto.md](docs/caso_concreto.md) trazem três verificações:

1. **Métricas das funções analíticas:** silhueta, R², MAE e RMSE com validação cruzada, acurácia, F1 e matriz de confusão.
2. **Análise de sensibilidade:** cada peso é variado em ±20% (com renormalização) e a taxa `d` de todos os modelos em ±10 p.p. O app informa se o veredito e o 1º lugar do ranking se mantêm. Também mostra o **ponto de virada** de cada parâmetro: a parcela de cada peso, o deslocamento de `d` e o preço do pretendido em que o veredito muda.
3. **Caso concreto passo a passo**, com os números do catálogo: entradas, dados do catálogo, reprodução da fórmula da proposta, modelo financeiro, ajustes, alternativas, matrizes do TOPSIS, regras, veredito e sensibilidade.

```bash
python scripts/caso_concreto.py   # regenera docs/caso_concreto.md
```

No caso de referência (Galaxy A54 → S24 por R$ 5.400, 3 anos), o veredito **manter o atual** se manteve em **100%** dos cenários de sensibilidade. Ele só vira para *vale a pena trocar* em três situações:

- o preço do S24 cai para cerca de **R$ 4.260**;
- o peso do custo cai para menos de 4%;
- o peso de processamento passa de cerca de 39%.

## Estrutura do projeto

```
app.py                    entrada do Streamlit: login e navegação por papel
pages/                    1 aparelho atual · 2 simulação · 3 relatório · 4 validação · 5 admin · 6 frota
src/dados.py              carga, normalização de nomes, matching, catálogo e modo demonstração
src/analitica.py          sumarização, agrupamento, regressão e classificação
src/decisao.py            modelo financeiro, regras, TOPSIS, veredito e plano da frota
src/relatorio.py          resumo em texto
src/validacao.py          sensibilidade (pesos ±20%, d ±10 p.p.) e pontos de virada
src/ui.py                 autenticação, cache, formatação e gráficos (Plotly)
scripts/                  pipelines: matching, catálogo, analítica, coleta no ML e caso concreto
data/catalogo_br.csv      catálogo final (48 modelos)
data/parametros.json      parâmetros do administrador
data/*_manuais.csv        dados preenchidos à mão
data/pendencias.csv       o que falta preencher
data/processed/           métricas e estatísticas usadas pelo app
docs/arquitetura.md       diagramas Mermaid: fluxo de dados, pipelines e módulos
docs/referencias.md       referências acadêmicas
docs/caso_concreto.md     caso concreto passo a passo (gerado)
tests/                    pytest
```

## Publicar no Streamlit Community Cloud

1. Envie o repositório ao GitHub. O `.gitignore` já exclui `.env`, `secrets.toml`, `data/raw/` e `data/cache/`.
2. Em [share.streamlit.io](https://share.streamlit.io), escolha **Create app**. Indique o repositório, a branch e o arquivo principal `app.py`. Em *Advanced settings*, escolha Python 3.12.
3. Em **Advanced settings → Secrets**, cole o conteúdo de `.streamlit/secrets.toml.example` com as senhas definitivas.
4. Clique em **Deploy** e copie o link público para o relatório do trabalho.

As alterações feitas na página de Administração valem até o app reiniciar, porque o disco do Streamlit Cloud é temporário. Para torná-las permanentes, faça commit de `data/parametros.json`.

## Limitações

- **Bases estrangeiras e de épocas diferentes.**
  - Specs: mercado indiano, 2023–2024.
  - Reviews: Amazon dos EUA, cerca de 2016.
  - Usados: aparelhos de 2013 a 2020, com no máximo 3 anos de uso. Por isso, horizontes de 4 e 5 anos são **extrapolados** pela curva.
- **Sem matching entre modelos da Smartprix e da Amazon.** As épocas não coincidem, então a satisfação vem **por marca**. Xiaomi e Realme não têm reviews suficientes.
- **Preço no Brasil, fim do suporte e avaliações vêm de preenchimento manual.** Sem eles, o app usa valores **simulados**, sempre sinalizados. Com o fim do suporte simulado igual para todos os modelos, o critério de segurança não diferencia os aparelhos.
- **Specs brutas** (MP da câmera, mAh da bateria) não medem qualidade. Elas penalizam topo de linha compactos, como os iPhones.
- **Não há custo de oportunidade** (juros) nem valor do dinheiro no tempo.
- **Ajustes de projeto:** os pesos padrão dos perfis da frota e o critério de alternativas comparáveis (mesmo segmento, preço ±30%, no máximo 6) são escolhas de projeto e podem ser editados.
- **O TOPSIS depende do conjunto de alternativas** (*rank reversal*; García-Cascales & Lamata, 2012). Por isso as posições do ranking do catálogo inteiro (relatório completo) podem diferir das do ranking da decisão.

## Situação das fases

| Fase | Situação |
|---|---|
| 0 · Inspeção e matching | ✅ |
| 1 · Catálogo | ✅ |
| 2 · Funções analíticas | ✅ |
| 3 · Modelo de decisão e testes | ✅ |
| 4 · App Streamlit | ✅ |
| 5 · Validação (sensibilidade e caso concreto) | ✅ |
| 6 · Diagrama de fluxo de dados (`docs/arquitetura.md`) e documentação | ✅ |
| 6 · Publicação no GitHub e no Streamlit Cloud | ⏳ aguardando a conta do GitHub |
