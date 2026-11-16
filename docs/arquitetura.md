# Arquitetura e fluxo de dados do TrocaCerta

O protótipo tem duas partes separadas:

- **Pipelines offline** (`scripts/`). Rodam na máquina do desenvolvedor, leem as bases brutas e geram arquivos pequenos em `data/`.
- **App Streamlit** (`app.py` e `pages/`). Lê só esses arquivos processados. Por isso o deploy não depende das bases brutas nem da API do Mercado Livre.

## 1. Diagrama de fluxo de dados

```mermaid
flowchart TD
    %% ---------- Fontes ----------
    subgraph F["1 · Bases de dados"]
        SP[("Smartprix<br/>specs · preços INR")]
        AZ[("Amazon Unlocked Mobile<br/>413 mil reviews · EUA")]
        US[("Used Phones & Tablets<br/>preços usados em log")]
        MAN[/"Preenchimento manual<br/>preços R$ · fim do suporte · avaliações"/]
        ML[("API Mercado Livre<br/>opcional · coletar_ml.py")]
    end

    %% ---------- Tratamento ----------
    subgraph T["2 · Tratamento e matching (src/dados.py)"]
        NORM["Normalização de nomes<br/>cor, GB, unlocked, operadora…"]
        MATCH["Matching rapidfuzz<br/>token_sort_ratio ≥ 85, mesma marca,<br/>números e qualificadores iguais"]
        SEL["Seleção de 48 modelos vendidos no Brasil<br/>variante base · conversão TB→GB"]
    end

    %% ---------- Funções analíticas ----------
    subgraph A["3 · Funções analíticas (src/analitica.py)"]
        SUM["Sumarização<br/>percentil 0–10 por critério"]
        AGR["Agrupamento<br/>k-means · k pela silhueta"]
        REG["Regressão<br/>linear × random forest, CV 5 folds<br/>razão(t) = a·(1−d)^t"]
        CLA["Classificação<br/>TF-IDF + regressão logística<br/>satisfação por marca"]
    end

    %% ---------- Catálogo ----------
    CAT[("4 · Catálogo<br/>data/catalogo_br.csv")]
    MET[("data/processed/metricas.json")]
    PAR[/"data/parametros.json<br/>editado pelo admin"/]
    PEND[("data/pendencias.csv")]

    %% ---------- Decisão ----------
    subgraph D["5 · Modelo de decisão (src/decisao.py)"]
        FIN["Modelo financeiro<br/>C_manter · C_trocar · saldo ano a ano"]
        AJ["Ajustes do atual<br/>condição · saúde da bateria · atende"]
        REGRAS{"Regras<br/>suporte acaba em menos de N meses?<br/>não atende?"}
        TOP["TOPSIS<br/>manter + comparáveis<br/>(mesmo segmento · preço ±30%)"]
        FROTA["Plano da frota<br/>≤ 2 modelos · suporte mínimo · orçamento"]
    end

    %% ---------- Interface ----------
    subgraph I["6 · Interface Streamlit (app.py · pages/)"]
        LOGIN["Login · st.secrets<br/>consumidor · gestor · admin"]
        UC["Consumidor<br/>aparelho atual · simulação"]
        UG["Gestor<br/>perfis · orçamento"]
        UA["Admin<br/>parâmetros · pendências"]
        VAL["Validação<br/>métricas · sensibilidade (src/validacao.py)"]
    end

    REL["7 · Relatório (src/relatorio.py)<br/>veredito · justificativa · ranking ·<br/>comparativo · origem de cada número"]

    %% ---------- Fluxos ----------
    SP --> NORM
    AZ --> NORM
    NORM --> MATCH
    MATCH -. "0 matches reais<br/>(épocas diferentes)" .-> CLA
    SP --> SEL
    MAN --> SEL
    ML -.-> SEL
    SEL --> SUM --> AGR
    US --> REG
    AGR --> REG
    AZ --> CLA
    SUM & AGR & REG & CLA --> CAT
    SUM & AGR & REG & CLA --> MET
    SEL --> PEND

    CAT --> FIN & AJ & TOP & FROTA
    PAR --> FIN & REGRAS & TOP & FROTA
    LOGIN --> UC & UG & UA
    UC -- "entradas e pesos" --> FIN
    UC --> AJ
    UG -- "perfis · pesos · orçamento" --> FROTA
    UA -- "salva" --> PAR
    PEND --> UA
    FIN --> TOP
    AJ --> TOP
    AJ --> REGRAS
    TOP --> REGRAS
    FROTA --> TOP
    REGRAS -- "veredito" --> REL
    FROTA -- "plano por perfil" --> REL
    MET --> VAL
    TOP --> VAL
```

**Como ler o diagrama:**
- Setas tracejadas são fluxos opcionais ou sem efeito. A API do ML só é usada quando há credenciais. O matching com a Amazon não encontrou modelos em comum, e por isso a satisfação é calculada por marca.
- As regras têm prioridade sobre o ranking do TOPSIS.

## 2. Pipelines offline (ordem de execução)

```mermaid
flowchart LR
    A["fase0_matching.py<br/>(diagnóstico)"] --> B["coletar_ml.py<br/>(opcional)"]
    B --> C["gerar_catalogo.py"]
    C --> D["gerar_analitica.py"]
    D --> E["caso_concreto.py"]
    C -. "pendências" .-> P["preenchimento manual"]
    P -. "rodar de novo" .-> C
```

| Script | Lê | Grava |
|---|---|---|
| `fase0_matching.py` | Smartprix, Amazon | `processed/matching_amazon.csv`, `processed/reviews_por_modelo.csv` |
| `coletar_ml.py` | catálogo, API do ML, `.env` | `precos_ml.csv`, `avaliacoes_ml.csv`, `processed/reviews_ml.csv`, `cache/` |
| `gerar_catalogo.py` | Smartprix, `*_manuais.csv`, `*_ml.csv` | `catalogo_br.csv`, `pendencias.csv`, modelos dos arquivos manuais |
| `gerar_analitica.py` | catálogo, usados, Amazon | catálogo (notas, segmento, `a`, `d`, satisfação), `processed/metricas.json`, estatísticas |
| `caso_concreto.py` | catálogo, parâmetros | `docs/caso_concreto.md` |

## 3. Dependências entre módulos

```mermaid
flowchart LR
    app["app.py"] --> ui["src/ui.py"]
    pages["pages/*.py"] --> ui
    pages --> decisao["src/decisao.py"]
    pages --> relatorio["src/relatorio.py"]
    pages --> validacao["src/validacao.py"]
    pages --> analitica["src/analitica.py"]
    ui --> dados["src/dados.py"]
    relatorio --> decisao
    validacao --> decisao
    scripts["scripts/*.py"] --> dados
    scripts --> analitica
    scripts --> decisao
```

O modelo de decisão (`decisao.py`) não depende do Streamlit. Isso permite testá-lo com pytest e reaproveitá-lo nos scripts e no documento do caso concreto.

## 4. Decisões de projeto

| Decisão | Motivo |
|---|---|
| Sem banco de dados, só CSV e JSON | Volume pequeno (48 modelos) e deploy gratuito no Streamlit Cloud |
| O app não chama APIs em tempo de execução | Reprodutibilidade, limites de requisição e funcionamento sem credenciais |
| Dados manuais separados do catálogo gerado | Regenerar o catálogo nunca apaga o que foi preenchido à mão |
| Modo demonstração com valores sinalizados | Permite rodar antes do preenchimento manual, sem esconder que os valores são simulados |
| `a` e `d` por segmento, não por modelo | As estimativas por modelo foram instáveis (dois valores de `d` saíram negativos) |
| Veredito decidido só entre as comparáveis | Evita que um topo de linha fora do orçamento vire a troca recomendada. O ranking do catálogo inteiro aparece só no relatório completo |
