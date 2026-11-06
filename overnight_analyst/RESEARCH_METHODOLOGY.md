## Atualização — seleção por 58% e confluência v2 (06/11/2026)

A versão ativa mantém apenas **Impulso após Pausa** (13 WIN / 7 LOSS, **65,0%**) e **Mudança de Ritmo** (21 WIN / 15 LOSS, **58,3%**), conforme o histórico verificado antes da alteração. **Falha no Extremo** (12 WIN / 13 LOSS, **48,0%**) foi suspensa do detector, com os resultados antigos preservados.

Uma família só pode ser suspensa automaticamente por ficar abaixo de 58% depois de atingir **20 resultados WIN/LOSS**. Depois de **25 resultados novos filtrados**, o desempenho da versão v2 passa a determinar sua permanência. Se uma combinação específica ativo+regime tiver **15 resultados filtrados** e menos de 58%, ela também é suspensa nesse mercado/regime. Casos com amostra pequena continuam em estudo; isso evita transformar 0/2 em descarte definitivo.

Antes de registrar uma nova simulação, a confluência usa até sete verificações e exige **pelo menos seis**, incluindo obrigatoriamente força do corpo, ausência de sombra contrária dominante e confirmação de movimento na cotação atual. As demais incluem fechamento perto da extremidade favorável, amplitude sem spike extremo, volatilidade dentro do intervalo de referência e coerência com o deslocamento recente. A cotação deve ser observada até quatro segundos após abrir o novo candle de 30 segundos, com idade máxima de um segundo. A política também exige payout **indicativo** do catálogo de pelo menos 80% e respeita as janelas de notícia cadastradas.

Cada padrão candidato gera uma decisão auditável no Supabase: permitida para simulação virtual, bloqueada por confluência ou suspensa pelo histórico. O placar **BASE_ANTIGA** não é misturado ao **FILTRADO_V2**. A seleção das duas famílias usando dados passados causa viés de seleção: é necessária validação com novas amostras para medir se os filtros reduziram LOSS.

**Nenhuma estratégia faz operações reais ou DEMO neste laboratório.** O valor de 58% é um limiar de monitoramento; não assegura lucro, e sinais descartados podem conter operações que teriam ganho. Uma redução da quantidade de LOSS isoladamente não é melhoria suficiente sem avaliar proporção de WIN, quantidade de oportunidades e rendimento esperado.

---

# Radar de Regimes — protocolo de pesquisa em opções binárias

**Objetivo:** examinar padrões em preços de 30 segundos e testar hipóteses de comportamento futuro com cotações observadas da conta PRACTICE da Bulex. **Não existem ordens enviadas à corretora neste laboratório.** Toda entrada marcada WIN/LOSS é virtual, não é preenchimento garantido de uma ordem.

## Evidências publicadas

1. Duvinage et al., *The intra-day performance of market timing strategies and trading systems based on Japanese candlesticks*, Quantitative Finance (2013). A previsibilidade aparente pode desaparecer após custos e correção por múltiplos testes: https://www.tandfonline.com/doi/full/10.1080/14697688.2013.768774
2. Bailey et al., *The Probability of Backtest Overfitting* (2017). Procurar muitos vencedores no mesmo histórico cria o risco de seleção de coincidências: https://scholarworks.wmich.edu/math_pubs/42/
3. Federal Reserve, *Trading Activity and Exchange Rates in High-Frequency EBS Data* (2007). A resposta a divulgações macroeconômicas pode acontecer em segundos: https://www.federalreserve.gov/pubs/ifdp/2007/903/ifdp903.htm
4. Federal Reserve, *Macroeconomic News Announcements, Systemic Risk, Financial Market Volatility and Jumps* (2015). Saltos são mais frequentes em dias de notícias: https://www.federalreserve.gov/econres/feds/macroeconomic-news-announcements-systemic-risk-financial-market-volatility-and-jumps.htm
5. CFTC/SEC, *Binary Options and Fraud*. Há reclamações e alertas sobre certos operadores de opções binárias. Isso não prova manipulação de uma corretora específica: https://www.cftc.gov/LearnAndProtect/AdvisoriesAndArticles/fraudadv_binaryoptions.html

## O motor atual

O scanner lê o catálogo de mercados abertos do endpoint Bulex e os acompanha **em rodízio de grupos de até oito**, não todos simultaneamente. O conjunto disponível varia. Os dados devem passar por verificação de timestamps, integridade de OHLC, contiguidade, frescor da cotação e tipo PRACTICE.

O laboratório foi iniciado com três famílias; desde a versão de confluência v2, duas permanecem ativas:

- **IMPULSO_APOS_PAUSA:** cinco candles curtos seguidos por deslocamento relevante além da faixa. Testa continuidade nos próximos 30 segundos.
- **EXAUSTAO_DO_EXTREMO (SUSPENSA):** hipótese antiga de falha no extremo; 48% no histórico verificado. Não gera novas simulações. **Não é prova de manipulação do broker**.
- **MUDANCA_DE_RITMO:** alternância de candles seguida por dois fechamentos consistentes. Testa continuidade.

A condição de mercado recebe um rótulo TENDENCIA, LATERAL, TRANSICAO ou VOLATIL com base no deslocamento líquido, na soma dos movimentos e na amplitude mediana de candles. Cada estratégia é avaliada **separadamente por ativo e regime**, e o nome do ativo não é inferido do comportamento de outro.

## Integridade de dados e resultados

1. Detectar formação apenas após a vela de 30 segundos fechar, sem usar candles em aberto na pesquisa do gatilho.
2. Registrar entrada virtual **somente** quando a vela seguinte receber cotação atualizada, com idade máxima de 1,5 segundo e janela de entrada de até 6 segundos.
3. Encerrar virtualmente após exatamente 30 segundos, usando uma nova cotação observada; uma confirmação até quatro segundos depois é rotulada como preço de observação próximo ao vencimento, não como fill de corretora.
4. Se não houver cotação adequada, marcar SEM_COTACAO, não WIN/LOSS imaginários.
5. Gravar estratégia, regime, direção, preço referencial, idade da cotação, carimbo UTC, status e payout *indicativo do catálogo*.
6. Registrar diferenças antes/depois em velas fechadas. Sem fonte independente, chamar o evento de **revisão observada**, jamais manipulação comprovada.
7. Notícias importantes bloqueiam novas simulações em uma janela de ±15 minutos **somente se horários previamente verificados forem cadastrados**. Sem sincronização do calendário externo, o status fica NÃO VERIFICADO.

## Critério de seleção

A taxa de equilíbrio para um contrato binário de lucro fixo, sem devolução no LOSS, é 100/(100+payout%) quando o payout é expresso em porcentagem. Para payout de 80%, aproximadamente 55,56%. O payout turbo do catálogo não confirma o payout real de um contrato de 30 segundos.

Uma combinação (ativo + regra + regime) só é colocada na seção de estudo prioritário após **80 resultados prospectivos WIN/LOSS**, assertividade **≥70%**, e limite inferior de Wilson de **95%** superior à taxa de equilíbrio estimada mais **dois pontos percentuais**. Esse destaque ainda não valida lucro real, pois há múltiplos ativos, múltiplas regras e diferenças de execução.

As regras não são reajustadas após perdas no mesmo conjunto de dados para evitar overfitting. Uma hipótese promissora precisa voltar a funcionar em um novo período que não participou da escolha. Empates e falta de cotação têm contagem separada. Zero observações significam acerto desconhecido, não 0% ou 100%.

## Segurança e permanência

No Render, o envio automático anterior foi desativado. O processo de integração também bloqueia os comandos legados de ordem. O painel só oferece GET de dados e rejeita POSTs para operar. Os registros antigos continuam arquivados, **fora** do novo placar. O Supabase guarda candles fechados recentes por sete dias e preserva permanentemente os resultados de experiências.

Esta ferramenta identifica **hipóteses passíveis de teste**, não uma estratégia garantida. O diagnóstico SEM OPERAÇÃO é esperado sempre que não houver dados suficientemente confiáveis.
