# Mesa Trader DEMO — Aprendizado de Padrões

## Situação inicial e princípio de segurança

Este módulo é **somente Bullex PRACTICE**, não usa martingale e **não opera
enquanto não houver padrões aprovados no Supabase**. Nunca inventa séries,
candles, payouts, histórico ou taxa de acerto. O robô original Sniper/Tendência
fica preservado para comparar o benchmark 5/6; quando `pattern_only=true`,
uma seta desse motor só é negociável se **também** corresponder a uma regra
aprovada. Logo, o classificador não substitui sozinho o motor de entrada.

O Render gratuito hiberna e NÃO garante 24h de coleta contínua. A coleta
depende de conexão PRACTICE válida e do servidor ligado. Bloqueios de rede,
payout indisponível, chamadas de websocket lentas e dados incompletos são
registrados como lacunas, não preenchidos com candles fictícios.

## Etapa 1 — Coleta real (já codificada)

- `worker.py` recebe M1 fechado de TODOS os pares de payout elegível para
  o scanner ativo; o stream inscreve aproximadamente um par por segundo.
- `mesa_market_capture.py` salva cada M1 com OHLC, volume se fornecido,
  timestamp UTC; agrega M5 apenas quando cinco M1 consecutivas fecharam.
- Catálogo real gera `mesa_pattern_payouts`, uma amostra por par por hora,
  **observada no momento**. Nunca preenche payout retroativamente.
- Buffer local de no máximo 12 MB; upload assinado e idempotente para Supabase
  em lotes de até 160 observações, com retry. Erros paralisam upload sem
  avançar cursor. O painel mostra cobertura e erros.
- O scanner de coleta opera mesmo com robô de ordens parado; quando o
  robô opera, aproveita os snapshots existentes para não disputar RPCs.
- Supabase mantém janela móvel de **7 dias**, com exclusão a cada hora e
  aviso/trava aos ~350 MB. 85 pares * 1.440 velas = **122.400 M1/dia**
  se todos abrirem o dia inteiro; M5 acrescenta até 24.480/dia.
  É limite proposital para reduzir risco de ultrapassar cota, não armazenamento
  vitalício. Para guardar anos, adotar arquivo Parquet com custo revisado.
- Render gratuito pode hibernar mesmo com scanner; não afirmar 24/7 garantido.

## Etapa 2 — Features sem visão do futuro

`mesa_pattern_features.py` é compartilhado pelo treinamento e pelo gate
ao vivo, e usa APENAS candles M1 já fechados: EMA 20/50/100; distâncias
normalizadas pelo ATR; RSI 14; ADX 14; DI+/DI-; MACD 12/26/9; histograma
MACD; ATR; corpo e pavios / ATR; posição nas últimas 20 velas; hora UTC e
sessão Ásia, Londres ou NY (horários de verão por fuso). A presença de lacunas
impede calcular um padrão — não preenche dados interpolados.

As features são COMPUTADAS quando a janela é analisada; ficam fora de cada
registro bruto OHLC para evitar inflar a base e a fatura. No futuro pode-se
salvar apenas features dos sinais efetivamente candidatos.

## Etapa 3 — Rotulagem

`mesa_pattern_train.py` compara OPEN da vela seguinte com CLOSE da
`expiração` (1 ou 5 M1), rotulando CALL, PUT ou EMPATE. Usa payout cujo
`observed_at` é ANTERIOR à entrada e no máximo 60 min antigo.
Payout capturado apenas por hora não garante cotação do segundo exato.
Expiração 5 serve para PESQUISA; o robô atual envia ordens M1 (60 s).
Empates não são tratados como vitórias.

## Etapa 4 — Modelos e walk-forward

Dependências ML ficam só em `requirements-learning.txt`; não são
instaladas no Render de execução. Com dois dias anteriores, treina árvore
rasa (`max_depth=3,min_samples_leaf=200`) e floresta aleatória
(`n_estimators=60,max_depth=4,min_samples_leaf=150`), compara os dois
com a estratégia original Mesa 5/6. Testa regras da árvore em dias
posteriores sem reotimizá-las na amostra testada.

Critérios de ativação ao mesmo tempo:
- pelo menos 300 ocorrências em TESTE fora da amostra;
- limite INFERIOR Wilson 95% acima de `1/(1+payout_médio)`;
- correção conservadora para testar múltiplas regras;
- expectativa por operação positiva;
- sustentação em pelo menos 2 dias futuros com no mínimo 30 ocorrências
  por dia, desempenho no dia não abaixo do equilíbrio.

Se não passar, publica **lista vazia** e desativa padrões anteriores.
Um RPC transacional impede ativação parcial.

## Etapa 5 — Execução e risco

Modo `pattern_only=true` é opcional e exclusivo para validação de padrões. Para medir WIN/LOSS da estratégia Sniper/Tendência, o painel oferece `demo_unlimited=true` e `pattern_only=false` (somente PRACTICE). A coleta continua nos dois modos. No modo aprendizado, ao iniciar o robô:
- consulta o Supabase; sem padrão aprovado, recusa operação com
  **SEM PADRÃO APROVADO / AMOSTRA INSUFICIENTE**;
- para cada nova seta Sniper ou sinal Mesa, calcula as MESMAS features
  apenas dos candles fechados e valida uma regra aprovada na mesma direção;
- mantém stops diário WIN e LOSS, limite por dia, pausa após 3 LOSS, pausa
  pelo rolling de 50, stake fixa no máximo 2% saldo DEMO, payout mínimo,
  1 ordem por vez, revisão de ordens incertas e trava de duplicidade.
- `demo_unlimited` e `pattern_only` não podem estar ativos simultaneamente.
  No teste contínuo, os stops diários são desabilitados de modo explícito;
  continuam obrigatórios payout, até 2% da banca por entrada, uma única ordem
  aberta, saldo válido e nenhuma entrada duplicada. Os resultados são salvos
  no histórico PRACTICE e também ajudam a avaliar a estratégia original.
- após WIN/LOSS, Supabase reavalia o padrão nas últimas 50 operações.
  Se ficar abaixo do equilíbrio, `active=false`, o próximo refresh bloqueia
  novas entradas desse padrão.

O histórico antigo de operações segue separado em `mesa_trade_history`.

## Como executar

1. Conecte Bullex PRACTICE no Render. **Não** clique em Iniciar para coletar;
   o scanner passivo começa na conexão.
2. Em Configurações veja Aprendizado de Padrões e o botão Atualizar padrões.
3. Observe a contagem de candles no banco e os erros de armazenamento.
4. Depois de **dados suficientes**, em ambiente confiável (PC/GitHub Actions):

```bash
pip install -r requirements-learning.txt
export MESA_HISTORY_API_URL="https://SEU-PROJETO.supabase.co/functions/v1/mesa-history"
export MESA_HISTORY_TOKEN="VALOR_APENAS_NO_AMBIENTE_PRIVADO"
python mesa_pattern_train.py --days 7 --train-days 2 --expiration 1 --report relatorio_mesa.json
```

Para ATIVAR somente regras que passarem na validação:

```bash
python mesa_pattern_train.py --days 7 --train-days 2 --expiration 1 --publish
```

**Nunca cole o token no GitHub, código, chat ou frontend.**
Um workflow semanal está preparado; depende de configurar duas
**Repository secrets** no GitHub:
`MESA_HISTORY_API_URL` e `MESA_HISTORY_TOKEN`. Antes de adicionar os
segredos, o workflow faz *skip* e NÃO reavalia padrões.

Para comparar expiração M5 sem enviar ordens:

```bash
python mesa_pattern_train.py --days 7 --train-days 2 --expiration 5
```

## Arquivos principais

- `sql/mesa_pattern_learning.sql` — tabelas RLS privadas, retenção,
  aprovação transacional e desativação por últimas 50.
- `mesa_market_capture.py`, `mesa_pattern_client.py` — coleta e upload.
- `mesa_pattern_features.py`, `mesa_pattern_train.py` — cálculo e mineração.
- `static/mesa-pattern-dashboard.js` — padrões aprovados, backtest vs ao vivo,
  nº de operações, cobertura e avisos.
- `tests/test_pattern_learning.py` — sem uso real de corretora.
- `mesa_pattern_data` — Supabase Edge Function nome real: `mesa-pattern-data`.

### Como interpretar resultados

- Um modelo pode ser mais correto que o benchmark na amostra histórica,
  mas falhar com baixa liquidez, OTC, rejeição de ordem ou regime novo.
- IC95% Wilson pressupõe observações aproximadamente independentes;
  candles e pares correlacionados reduzem o tamanho efetivo. Uma avaliação
  por bloco temporal separado é exigida e ainda pode ser insuficiente.
- A curvatura da banca, custo de oportunidade, baixa cobertura e payout
  variável importam tanto quanto acerto.
- **Se não existir padrão aprovado, o correto é NÃO OPERAR.**
- **Somente DEMO; sem martingale; sem garantia de lucro ou acerto 60–70%.**
