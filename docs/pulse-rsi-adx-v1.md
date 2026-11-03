# Pulse RSI + ADX v1 — teste prospectivo

Implementação experimental própria, não réplica do algoritmo NextGreen.
Referências: descrição pública https://nextgreen.pro/ (RSI, ADX e confirmação);
print fornecido em 03/11/2026 mostra ALTA GBP/AUD OTC M1, RSI 78,3, ADX 60,6,
80% de velas verdes e 20% vermelhas. Esses valores são uma observação de um sinal,
não os parâmetros da estratégia. O índice de confiança exibido não comprova
probabilidade calibrada. Não foi reproduzido.

## Parâmetros fixados antes da avaliação

- RSI 14: suavização de Wilder, semente pela média dos primeiros 14 ganhos/perdas.
- ADX/DMI 14: true range, movimentos direcionais exclusivos, suavização de Wilder.
  ADX inicial é a média dos primeiros 14 DX. Empate de movimentos zera ambos.
- Exigir 100 velas fechadas consecutivas (leitor solicita até 150).
- ALTA: RSI entre 52 e 80 e subindo, +DI > -DI, fechamento acima da abertura
  e do fechamento anterior; pelo menos 3 das últimas 5 velas verdes.
- BAIXA: RSI entre 20 e 48 e caindo, -DI > +DI, fechamento abaixo da abertura
  e do fechamento anterior; pelo menos 3 das últimas 5 velas vermelhas.
- Ambas: ADX >= 20 e não decrescente na última observação.
- Dojis não contam como verde nem vermelho; percentuais usam 5 como denominador.
- Mantidos filtros obrigatórios EMA 8/21, qualidade de entrada, dados frescos,
  catálogo válido e bloqueio de contexto contrário no outro período quando disponível.
- Pontuação existente compara M1/M5 por ativo; não representa probabilidade e
  não é ranking global de todos os ativos. A primeira comparação elegível encerra a busca.
- Todos estes limiares e a janela de 5 velas são escolhas nossas a validar.

## Teste e interface

Só esta estratégia fica habilitada por padrão. As anteriores permanecem disponíveis.
Um clique gera no máximo um sinal pendente; nenhuma ordem ou martingale.
Registros novos incluem strategy_version=rsi_adx_v1, métricas e parâmetros.
Histórico e placar começam filtrados por esta estratégia e pela data selecionada;
Todas as estratégias permite consultar os registros anteriores. Exportar preserva tudo.

## Limite de tempo ainda existente

Não houve alteração no agendamento: o último candle fechado é analisado até 12
segundos depois do fechamento, com entrada anunciada para a próxima abertura e
vencimento uma vela após a entrada. Existe uma vela intermediária sem revalidação.
Essa limitação precisa ser considerada na avaliação; não foi corrigida nesta versão.
Apuração usa abertura e fechamento exatos do intervalo anunciado, nunca preço anterior
à emissão. Não reinterpretar resultados antigos nem misturar recuperação por martingale.

## Validação

Testes sintéticos verificam cálculos, exclusão de vela aberta/futura, bloqueios,
seleção, metadados e emissão nas duas direções. Não são backtest de lucratividade.
Aguardar histórico prospectivo por ativo e prazo, preservando perdas e dados ausentes.
Comparar versões em condições equivalentes; não escolher vencedor por amostra pequena.

Referências dos cálculos:
https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/DMI
https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/RSI
