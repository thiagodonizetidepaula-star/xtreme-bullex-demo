# Market Edge Lab — fase 1: auditoria e retirada das estratégias

Escopo desta revisão: retirar todas as estratégias atuais da geração e execução, preservar registros e preparar a aplicação existente para a regra que o proprietário ainda enviará. Não constitui execução completa do plano de pesquisa anexado.

## 1. Arquitetura verificada no código

- Python/Flask em app.py; interface HTML/CSS/JavaScript em index.html; Gunicorn no Render.
- Analisador: worker.py recebe catálogos e velas M1 por integração não oficial; engine.py normaliza, avalia hipóteses e liquida observações teóricas. Esses resultados não equivalem a preços de entrada executados.
- Executor: execution.py gerencia ordens em executor_worker.py, em processo separado; verifica PRACTICE, prazo, payout e saldo. Não há modo real.
- Persistência: gateway privado Supabase, payload por conta e checkpoint compacto antes de cada envio. Eventos teóricos e ordens são separados; acumuladores de pesquisa preservam contagens.
- GitHub: branch xtreme-analista; publicação automática no serviço xtreme-analista do Render. Commit pai preserva ponto de restauração.
- Recursos preservados: conexão, gráfico, histórico, exportação, placar, logs de ordens e acumuladores. Todas as regras antigas estão inativas, mesmo com resultados históricos positivos.

## 2. Informações faltantes

Não recebida a regra da nova estratégia: código/fonte, indicadores, parâmetros, preço-fonte, compra/venda, momento da confirmação, timeframe, vencimentos e filtros. Também faltam documentação de API autorizada, condições oficiais atualizadas de automação e dados históricos de entrada/liquidação/payout adequados para replay fiel.

## 3. Fontes a pesquisar na fase seguinte

Documentação e termos oficiais da Bullex; alertas e decisões da CVM; documentação técnica primária dos indicadores; artigos e repositórios públicos legítimos com regras reproduzíveis. Registrar URL, data de consulta/publicação e limitações. Esta revisão não concluiu a pesquisa documental.

## 4. Verificação regulatória pendente

O arquivo menciona um alerta de 26/06/2025 relativo a Digital Smart LLC/Bullex. Essa referência veio do usuário e não foi verificada nesta revisão. Verificar o alerta e atualizações em fontes oficiais antes de qualquer conclusão sobre o status atual. A integração atual é não oficial; sua existência técnica não comprova autorização de uso.

## 5. Pesquisa de concorrentes proposta

Registrar somente regras e evidências públicas: metodologia, número de operações, período, payout, custos, teste fora da amostra e classificação da evidência. Não usar marketing ou capturas de tela como validação. Nenhuma candidata foi escolhida nesta fase.

## 6. Validação estatística proposta

Dividir cronologicamente desenvolvimento/validação antes de ajustar parâmetros. Comparar payout, expectativa por unidade, drawdown, sequências de perdas, cobertura de dados e sensibilidade de parâmetros. Registrar todas as variantes, inclusive rejeitadas, para controlar seleção oportunista. Sem dados de liquidação confiáveis, apresentar cenários hipotéticos. A regra antiga de 50% e a lista histórica de cinco WIN não são aprovação estatística. Martingale não participa da nova validação.

## 7. Integração proposta

Novo módulo isolado, identidade/versão próprias, contrato de sinal com instante, ativo, direção, timeframe, vencimento, parâmetros, motivos, filtros, fonte/qualidade e estado de validação. Primeiro simulação, sem ativação automática de ordens. Somente após regra definida e testes poderá ser considerada nova integração, sem herdar resultados anteriores.

## 8. Entregáveis e aceitação desta fase

- ACTIVE vazio e EXECUTABLE vazio: nenhuma seleção ou novo sinal de estratégia anterior.
- Endpoint de iniciar executor rejeita execução sem estratégia; processo da corretora também bloqueia novo envio.
- Gales de estratégias retiradas não são gerados; martingale não pode ser ativado.
- Histórico preservado e regras antigas mantidas apenas como referência testável/arquivada. Nada foi apagado no Supabase.
- Testes de regressão das regras antigas executam apenas sob configuração explícita de teste; testes adicionais verificam o bloqueio real de produção.
- Interface informa SEM OPERAÇÃO e aguarda a nova regra. Reversão possível pelo commit pai; não é automática.

Riscos/limitações: a publicação reinicia processos e exige reconexão; uma ordem já enviada na corretora não é cancelada pelo bloqueio de novas entradas. Ordens sem confirmação após reinício exigem conferência manual. O Render gratuito continua sujeito a suspensão. Nenhuma pesquisa regulatória, backtest fora da amostra ou estratégia nova foi concluída aqui.


## Atualização: especificação Multifiltros V1.0 recebida

Implementado módulo experimental somente PAPER/CSV conforme MULTIFILTER_V1.md. A hipótese possui regras rastreáveis, relatório e testes com dados fictícios. A geração por CSV não reativa as estratégias anteriores ou o executor. Pesquisa regulatória, API autorizada, dados reais e validação prospectiva continuam pendentes. A frase anterior sobre ausência de regra descrevia o estado da fase inicial, superado por esta atualização.
