# Mesa Trader – Laboratório Quantitativo (somente DEMO)

> Esta branch `mesa-quant-research` é uma **versão de pesquisa isolada** da `mesa-traders-demo`.
> Ela **não está publicada no Render de produção**. A conta Bullex real é proibida
> pelas travas existentes em `worker.py`. Não há previsão de ganho.

## Ordem de prioridades e motivação

1. **Telemetria antes de otimização:** grava no JSONB de cada operação a foto da decisão
   (par, data ISO UTC e America/Sao_Paulo, M1/M5, CALL/PUT, payout anunciado,
   payout efetivo quando a corretora confirma, stake, WIN/LOSS/ignorado, EMA 20/50/100,
   ADX14, DI+/DI-, MACD, histograma, RSI14, ATR14, distância EMA20 normalizada por ATR,
   corpo da vela, pavio contra a direção, seis votos e testes-sombra de cada filtro).
   Valores ausentes permanecem null; não serão inventados.
   A estrutura atual de `mesa_trade_history.payload` no Supabase aceita os campos JSON
   novos **sem migrar o esquema**. Grava somente no servidor, usando a conexão existente.
2. **Risco obrigatório:** stop win + stop loss, 2% do saldo PRACTICE no máximo por
   ordem fixa, sem martingale, uma operação aberta, intervalo mínimo entre entradas
   por par, payout mínimo consultado antes do envio, pausa se últimos 50 WIN/LOSS
   ficarem abaixo do equilíbrio com payout médio histórico.
3. **Filtros adicionais EM PESQUISA, desligados por padrão:**
   - Horário: terça–sexta/segunda, somente miolo das sessões de Londres e NY
     com horário de verão por `zoneinfo`; filtra OTC porque janela de
     liquidez interbancária não se aplica a OTC.
   - ATR/volatilidade: ATR atual entre 0,70x e 1,80x a mediana dos últimos 40 ATRs.
   - ADX: versões isoladas de limiar 20, 25 e 30.
   - Resistência/suporte: zona oposta baseada nos 50 candles fechados anteriores.
   - Vela: corpo >= 0,35x ATR e pavio adverso <=0,18x ATR.
   - Notícias: eventos `impact: high` de fonte verificável, bloqueio ±15 min.
     **Sem calendário fornecido, filtro ativo bloqueia** (não supõe dia sem notícias).
   - Pares/horários ruins: sinal estatístico só com >=300 operações
     históricas desse segmento e limite **SUPERIOR** Wilson 95% abaixo do equilíbrio.
     Treinamento nunca usa o próprio período de teste.
   Não há ativação automática em produção antes de comprovação.
4. **Backtest real somente com CSV de fonte auditável:** M1 contínuo e payout
   histórico ***observado no início do candle de entrada***. M5 é derivado
   apenas de blocos M1 de cinco minutos já fechados. Nenhum lookahead.
5. **Walk-forward:** 60% inicial para treino, 20% teste seguinte,
   depois treino expandido 80%, 20% teste futuro. Variações **uma por vez**.
   Indicadores da vela e filtros usam somente passado. Entradas de 4/6
   são **contrafactuais no backtest**, nunca executadas na DEMO.
6. **Aprovação:** no mínimo 300 operações **fora da amostra**, e limite
   inferior Wilson de 95% acima de `1/(1+payout_medio/100)`. Ao comparar
   muitas variantes, considere ainda o problema de múltiplos testes; o código
   não transforma resultado exploratório em autorização de operar real.
7. **Painel de desempenho:** em Configurações, clique
   `Atualizar desempenho`. Mostra acerto, intervalo de confiança, percentual
   de equilíbrio pelo payout, expectativa por unidade arriscada, drawdown,
   curva de saldo e segmentos por par, hora UTC, 4/5/6 votos e filtros-sombra.

## Como rodar offline

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -p "test_quant_research.py" -v
python -m unittest discover -s tests -p "test_mesa_strategy.py" -v
python mesa_backtest.py --csv dados_m1_reais.csv --out relatorio_walk_forward.json
```

### Formato CSV (UTC)

Cabeçalho EXATO:

```csv
asset,from,open,max,min,close,payout
```

Cada linha: `asset` da Bullex, `from` timestamp UNIX UTC **no começo
do M1**, `open`, `max`, `min`, `close` do candle real e `payout` em
porcentagem **disponível naquele instante** (não payout atual reaproveitado).
Use somente dados autorizados pela corretora e de procedência documentada.

O simulador assume entrada no OPEN do minuto seguinte ao candle de sinal,
expiração de 60s no CLOSE seguinte, sem latência, spread, slippage ou rejeição.
Resultados do broker DEMO podem divergir desses pressupostos. **Não use**
dados sintéticos para aprovar filtros, apenas para testes técnicos.

### Calendário de notícias (opcional)

```json
[
  {"timestamp_utc":"2026-10-22T12:30:00+00:00","impact":"high"}
]
```

A data acima é apenas um **exemplo de formato**, não afirma que exista
alguma notícia naquele horário. Use um calendário verificado e atualizado.
Ative somente em análises com fonte e período completos:

```bash
python mesa_backtest.py --csv dados_m1_reais.csv --news-file noticias_verificadas.json --out resultado.json
```

## Qual é a conclusão **hoje**?

No Supabase em 2026-10-20 a consulta encontrou 3 WIN, 1 LOSS e
17 operações IGNORADAS, sem indicadores históricos completos.
Há apenas **4 operações encerradas**. O acerto simples 75% não é
estatisticamente conclusivo. **NENHUM filtro adicional mostrou aumento
comprovado de acerto até agora.** Não existe série histórica M1 com
payout temporal suficiente disponível nesta branch para produzir
um backtest real: portanto não foi produzido número de acerto
de filtros nem realizado autoajuste.

### Antes de publicar a versão experimental no Render

- Rode a bateria no GitHub Actions, sem secrets.
- Capture/exporte candles M1 de fonte autorizada e payout histórico por horário.
- Gere relatório walk-forward com 300+ operações na janela OOS.
- Compare expectativa e drawdown, não somente taxa de acerto.
- Faça ensaio da versão DEMO sem mover para dinheiro real.
- Atualização do Render reinicia conexões; **não publicar automaticamente**
  enquanto o robô estiver operando no PRACTICE.

*Alto risco. Uso exclusivamente DEMO. Sem garantia de ganhos.*
