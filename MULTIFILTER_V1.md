# Quantitativa Multifiltros V1.0 — implementação experimental

## Escopo e integração

Módulo independente multifilter.py, interface multifilter-ui.js e aba MULTIFILTROS · PAPER no HTML existente. Endpoint POST /api/paper/evaluate recebe dois CSVs e configuração; não requer credenciais da corretora, não acessa redes externas, não cria sessões Bullex nem escreve no Supabase. Resposta inclui relatório exportável JSON. Uma análise por processo; limite de requisição de4MB aplicado somente a esta rota; limites anteriores de8KB e autenticação/CSRF dos demais endpoints preservados. A rota analítica é pública, limitada e sem estado. Nenhuma regra é inserida em ACTIVE ou EXECUTABLE, que continuam vazios. O processo da corretora permanece bloqueando novas ordens.

## Contrato dos dados

Um ativo e uma origem declarada por execução. Arquivos M1 e M5 nativos separados, até5.000 velas/1,5MB cada. Não agregamos M1 para obter contexto M5. Cabeçalhos: from,open,high,low,close; também aceita timestamp/time e max/min. Opcionais asset,timeframe,payout. Timestamp é abertura da vela em Unix/segundos ou ISO8601 com fuso. Timeframe em minutos. Arquivo separado por vírgula ou ponto e vírgula; ponto decimal preferível. Valores financeiros positivos finitos até1e12.

Ordena cronologicamente; rejeita duplicidades, OHLC inconsistente, alinhamento incorreto, ativo/timeframe incompatíveis e valores inválidos. Exclui velas abertas ou posteriores ao instante as_of. Gaps reiniciam indicadores; exige150 velas consecutivas em cada timeframe. Última M5 fechada deve terminar exatamente na última fronteira M5 disponível na decisão M1. Onde há cinco M1 correspondentes, compara OHLC M5 com tolerância relativa1e-7/absoluta1e-9 e bloqueia contexto conflitante. Isso verifica coerência, não autenticidade/autorizações da fonte.

## Indicadores

EMA9/21/50 sobre fechamento, semente no primeiro fechamento de cada segmento contínuo. RSI14 de Wilder: primeira média de14 variações, depois atualização recursiva. ATR14: primeiro TR usa amplitude, primeira ATR média de14 TR, depois Wilder. Bandas: SMA20 ±2 desvios populacionais. Não usa candle aberto nem indicadores futuros. Bandas são registradas como contexto; não garantem reversão nem geram sinal isolado.

## Tradução efetiva das regras

CALL exige EMA9>EMA21>EMA50; separação mínima entre médias; EMA21 crescente com inclinação mínima na última vela e não negativa na anterior; M5 não ordenada em baixa. PUT aplica inverso.

Pullback: ao menos uma das3 velas anteriores intersecta a região EMA9/21 com tolerância de0,15ATR; todas preservam EMA50, com tolerância0,15ATR. Confirmação: corpo a favor, fechamento supera o anterior na direção e fecha além da EMA9. Amplitude máxima1,8ATR; distância máxima1,5ATR da EMA21. RSI CALL50–65, PUT35–50; variação de RSI não pode enfraquecer a direção. Médias separadas por ao menos0,15ATR; inclinação EMA21 mínima0,03ATR por vela. ATR/preço entre0,00005 e0,03. Barreira: máxima/mínima das20 velas anteriores; bloqueia compra/venda se a barreira à frente estiver a menos de0,3ATR.

Todos esses limites numéricos não especificados pelo proprietário são propostas EXPERIMENTAIS, configuráveis e exportadas no relatório. Não foram calibrados nem aprovados por dados reais. As faixas preferenciais de RSI foram implementadas como filtros obrigatórios nesta versão, escolha explícita conservadora. Mudanças geram nova configuração registrada no hash, nunca reescrevem um relatório anterior.

## Candidata, simulação e aprovação

Candidata técnica é somente confluência dos filtros. Toda decisão continua com order_eligible=false, validation=NÃO VALIDADA e estado SEM OPERAÇÃO por evidência insuficiente. É possível estudar resultados hipotéticos sem promover a estratégia, somente após aceitar expressamente o modelo de liquidação.

Modelo opcional: entrada na abertura da próxima M1; vencimento hipotético1/2/3/5 minutos; saída no fechamento M1 do vencimento; direção determina WIN/LOSS/EMPATE, empate devolve, sem slippage/custos. Vencimentos e liquidação não são anunciados como disponíveis na Bullex. Payout do CSV é declarado e não autenticado; payout manual é cenário hipotético. Sem payout, modelo aceito, M5 válido ou qualidade suficiente, não simula. Sem abertura de entrada não cria operação; sem velas de liquidação registra SEM COTAÇÃO e interrompe a amostra. Não transfere sinal expirado para outro horário.

Uma posição por vez, valor fixo, sem martingale. Limites de ordens, perda, lucro e sequência de perdas são independentes do filtro. O valor da próxima entrada precisa caber no saldo restante do stop loss. WIN/LOSS só após o timestamp de liquidação verificável nos dados. Fim incompleto permanece ABERTA/SEM COTAÇÃO, nunca vitória presumida.

## Validação e métricas

Divisão temporal configurável; padrão70/30 por timestamps de M1. Indicadores usam somente histórico disponível, inclusive aquecimento pré-validação. Operações cruzando a fronteira são purgadas. Risco reinicia em cada amostra, para não esgotar o limite antes de avaliar validação; essa escolha é documentada na interface. Não há ajuste automático de parâmetros.

Taxa: WIN/(WIN+LOSS), empate excluído. Wilson95% da taxa. Saldo e expectativa por operação incluem empates; máximo drawdown e maior sequência LOSS calculados cronologicamente. Distribuição por horário UTC; ativo, timeframe e expiração ficam separados por relatório. Payout médio de WIN e perda média registrados. Ponto de equilíbrio usa cenário de payout médio disponível nas operações concluídas; EV decisiva usa retorno observado condicional de WIN e frequência de LOSS. Limite inferior de EV é apenas aproximação no cenário de payout médio, não intervalo completo de rentabilidade nem correção por múltiplos testes.

Referências: fechamento acima/abaixo da EMA21 e primeiro Sniper alinhado ao ATR18×2 de tendência, replay das fórmulas anteriores, nunca reativação do robô. Usa mesmos dados, corte, payout, liquidação e limites, mas calendários de entrada próprios. O replay anterior processa segmentos contínuos completos; não afirma reproduzir exatamente cache/latência/ordens da versão antiga. Sensibilidade opcional testa distância EMA21 ±10%, sem selecionar vencedora automaticamente.

## Auditoria, entrega e limitações

Relatório contém todas as decisões, inclusive filtros rejeitados, dados de indicadores, ordens hipotéticas, interrupções, parâmetros, versão, origem, corte temporal e hash SHA256 dos dados/configuração. Interface exibe últimas200 decisões; exportação inclui todas. Sem armazenamento automático: salvar relatório JSON é necessário para comparar execuções. Botão de demonstração usa dados FICTÍCIOS, identificado na origem e no relatório; seus resultados não são evidência de mercado.

Testes conhecidos cobrem indicadores, CALL/PUT, filtros, ausência/gaps/conflito M5, dados futuros, CSV inválido, duplicação, liquidação, risco, separação temporal, métricas, endpoint sem corretora, origem e limites de upload. Testes com dados fictícios nunca comprovam taxa de acerto real.

Pendências: dados reais de fonte autorizada, condições documentadas de automação/liquidação/payout/vencimentos, pesquisa regulatória atual, parâmetros e amostras mínimas pré-definidos, walk-forward completo, análise de diferentes regimes e validação prospectiva. Nenhuma estratégia é classificada como promissora nesta entrega. Nenhuma ordem real ou demo pode ser habilitada automaticamente por um resultado do laboratório.
