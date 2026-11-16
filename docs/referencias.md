# Referências acadêmicas do TrocaCerta

Cada fórmula ou método do protótipo e a referência que o fundamenta.

## Sistema de apoio à decisão e tipo de decisão
- **Decisão semiestruturada / SAD.** GORRY, G. A.; SCOTT MORTON, M. S. A framework for management information systems. *Sloan Management Review*, v. 13, n. 1, p. 55–70, 1971.
- SPRAGUE, R. H.; CARLSON, E. D. *Building Effective Decision Support Systems*. Englewood Cliffs: Prentice-Hall, 1982.
- SIMON, H. A. *The New Science of Management Decision*. New York: Harper & Row, 1960.

## Modelo financeiro: manter × trocar
- **Análise de substituição "defensor × desafiante"** (custo de manter o equipamento atual contra o de adquirir um novo, no mesmo horizonte). BLANK, L.; TARQUIN, A. *Engineering Economy*. New York: McGraw-Hill (capítulo *Replacement and Retention Decisions*).
- BELLMAN, R. Equipment replacement policy. *Journal of the Society for Industrial and Applied Mathematics*, v. 3, n. 3, p. 133–136, 1955.

**Fórmulas no protótipo:** `C_manter = G_ano·H − R_atual,H`, `C_trocar = T − R_atual,0 − R_novo,H` e `Saldo = C_manter − C_trocar`.

## Depreciação: R_t = a · R_0 · (1 − d)^t
- **Depreciação geométrica**, taxa anual constante `d`. HULTEN, C. R.; WYKOFF, F. C. The estimation of economic depreciation using vintage asset prices: an application of the Box-Cox power transformation. *Journal of Econometrics*, v. 15, n. 3, p. 367–396, 1981.
- FRAUMENI, B. M. The measurement of depreciation in the U.S. National Income and Product Accounts. *Survey of Current Business*, v. 77, n. 7, p. 7–23, 1997.
- **Queda imediata na revenda** (fator `a` < 1). Ela é explicada pela assimetria de informação entre vendedor e comprador no mercado de usados. AKERLOF, G. A. The market for "lemons": quality uncertainty and the market mechanism. *The Quarterly Journal of Economics*, v. 84, n. 3, p. 488–500, 1970.

**Estimação:** `ln(razão) = ln(a) + t·ln(1 − d)` sobre as previsões da regressão. Com `a = 1`, volta-se à fórmula original da proposta, usada no teste de referência.

## Funções analíticas
- **Random forest.** BREIMAN, L. Random forests. *Machine Learning*, v. 45, n. 1, p. 5–32, 2001.
- **Validação cruzada k-fold.** KOHAVI, R. A study of cross-validation and bootstrap for accuracy estimation and model selection. In: *IJCAI*, 1995, p. 1137–1145.
- **k-means.** MACQUEEN, J. Some methods for classification and analysis of multivariate observations. In: *Proc. 5th Berkeley Symposium on Mathematical Statistics and Probability*, v. 1, p. 281–297, 1967.
- **Silhueta.** ROUSSEEUW, P. J. Silhouettes: a graphical aid to the interpretation and validation of cluster analysis. *Journal of Computational and Applied Mathematics*, v. 20, p. 53–65, 1987.
- **TF-IDF.** SALTON, G.; BUCKLEY, C. Term-weighting approaches in automatic text retrieval. *Information Processing & Management*, v. 24, n. 5, p. 513–523, 1988.
- **Classificação de sentimento com aprendizado de máquina.** PANG, B.; LEE, L.; VAITHYANATHAN, S. Thumbs up? Sentiment classification using machine learning techniques. In: *EMNLP*, 2002, p. 79–86.
- **Desbalanceamento** (ponderação de classes na regressão logística). KING, G.; ZENG, L. Logistic regression in rare events data. *Political Analysis*, v. 9, n. 2, p. 137–163, 2001.

## Modelo multicritério
- **TOPSIS** (normalização vetorial, soluções ideais positiva e negativa, proximidade relativa). HWANG, C.-L.; YOON, K. *Multiple Attribute Decision Making: Methods and Applications*. Berlin: Springer, 1981.
- BEHZADIAN, M. et al. A state-of the-art survey of TOPSIS applications. *Expert Systems with Applications*, v. 39, n. 17, p. 13051–13069, 2012.
- **Inversão de ranking (*rank reversal*) no TOPSIS.** GARCÍA-CASCALES, M. S.; LAMATA, M. T. On rank reversal and TOPSIS method. *Mathematical and Computer Modelling*, v. 56, n. 5–6, p. 123–132, 2012.
- **Análise de sensibilidade dos pesos.** TRIANTAPHYLLOU, E.; SÁNCHEZ, A. A sensitivity analysis approach for some deterministic multi-criteria decision-making methods. *Decision Sciences*, v. 28, n. 1, p. 151–194, 1997.

> Antes de usar no relatório final, confira na fonte original os números de página e a edição.
