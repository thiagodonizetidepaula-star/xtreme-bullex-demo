# Falha de continuação v1

Hipótese experimental própria solicitada em 03/11/2026: reação de preço à vela
anterior. Não há evidência de que seja inédita ou pouco usada. OHLC não identifica
intenções, ordens institucionais ou a sequência intravela; “rejeição” descreve
somente o extremo registrado e a posição do fechamento.

## Regras fixadas

Referência = penúltima vela fechada; confirmação = última vela fechada.
Escala = mediana das amplitudes de 8 velas anteriores à referência.

- Referência: corpo >= 55% da amplitude e amplitude entre 0,5 e 2 escalas.
- Confirmação: corpo >= 35%, amplitude entre 0,5 e 2,5 escalas; abertura no
  máximo 0,15 escala distante do fechamento da referência.
- BAIXA: referência de alta; confirmação de baixa com máxima pelo menos 0,05
  escala acima da máxima anterior, pavio superior >=25% da amplitude,
  fechamento abaixo do meio do corpo anterior e nos 30% inferiores da amplitude.
  Não pode ultrapassar também a mínima anterior.
- ALTA: condições espelhadas, rejeitando mínima anterior e fechando acima do
  meio do corpo anterior, nos 30% superiores; não pode ultrapassar também a máxima.
- Comparação M1/M5 por ativo, primeira comparação elegível; empate favorece M1.
- Esta família usa avaliação própria, sem EMA, RSI ou ADX. Estratégias antigas
  continuam com seus filtros. Se habilitadas juntas e divergirem, não há sinal.
- Um clique, no máximo um sinal pendente, sem envio de ordens.

## Registro e avaliação

Ativada sozinha por padrão. strategy_version=previous_candle_reaction_v1.
Registra OHLC da referência e confirmação, proporções e parâmetros para auditoria.
Histórico e placar filtrados por data e estratégia; resultados antigos preservados.
Pontuação interna fixa é somente desempate operacional, nunca confiança estatística.

Limite mantido: análise até 12s após fechamento, entrada na próxima abertura e
vencimento uma vela após entrada. A vela intermediária não é revalidada. Esse
intervalo pode invalidar a leitura e precisa ser considerado no teste prospectivo.
Não há comprovação de eficácia; testes verificam código e ausência de dados futuros.
