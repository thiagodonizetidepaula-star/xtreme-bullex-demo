# Pocket Lens — análise da Pocket Option

Aplicativo separado, somente de leitura. Usa autenticação Supabase do projeto Mesa Trader; nenhuma alteração de tabelas. A sessão do aplicativo usa cookie Secure/HttpOnly/SameSite=Strict, validade máxima de uma hora e inatividade máxima de 20 minutos. A sessão Pocket Option permanece apenas em memória. Nunca colocar credenciais no repositório.

## Executar

Python 3.11+. `pip install --require-hashes -r pocket-chart/requirements.txt`, depois `python pocket-chart/server.py`. Variáveis: `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` e `PORT`. Execute `cd pocket-chart && python -m unittest -v` para verificar.

## Conexão e dados

Entrar com conta existente Mesa Trader. A versão Android em `android/` abre a Pocket Option oficial e utiliza a conexão WebSocket DEMO original no celular. Encaminha somente dados de mercado ao backend, sem SSID, cópia manual ou segundo login. O retorno ocorre apenas após a primeira cotação real atual. Esse fluxo requer validação em aparelho real; não constitui API oficial da corretora. No navegador comum, permanece disponível a conexão manual via pacote auth. Os endpoints Socket.IO são não oficiais, herdados do adaptador existente, e podem mudar. Nenhuma conexão ao vivo foi verificada sem sessão do usuário.

Catálogo vem de updateAssets, inclui todos os instrumentos abertos reportados pela sessão, sem lista estática e sem limite a OTC. Um ativo é analisado por vez. Fechados não entram na seleção. Sem catálogo, não inventa ativos.

Gráficos: 5s, 15s, 30s, M1, M2, M3, M5, M10, M15, M30, H1, H4. Velas construídas de ticks da corretora e histórico pedido via loadHistoryPeriod, correlacionado por índice, ativo e geração. Se o histórico de um período não for suportado, aguarda ticks novos. Não preenche lacunas ou gera preços simulados. Velas incompletas não geram sinal. Histórico não emite sinais retroativos.

## Análise

Pivôs estritos com duas velas em cada lado. Suportes e resistências agrupados por tolerância de 0,3 da amplitude média das últimas 14 velas; mínimo de dois toques para gerar sinais. Linha ascendente por dois fundos crescentes e descendente por dois topos decrescentes, descartada após rompimento. Rejeição ou engolfo na região pode emitir BUY/SELL após fechamento, usando somente o contexto anterior. Sinais são experimentais e não possuem taxa de acerto validada.

Horizonte em segundos ou minutos é um parâmetro visual de análise, NÃO catálogo de expirações confirmado pela corretora. Não há envio de ordens, endpoint de operação ou eventos de negociação na allowlist. Sem cotações atuais, novos sinais são suspensos. Sinais anteriores permanecem identificados como anteriores.

## Limitações verificáveis

Testes automatizados cobrem integridade temporal, isolamento de ativos e períodos, auth demonstrativa, bloqueio de eventos de ordens e regras causais. Sem uma sessão autenticada Pocket Option fornecida pelo usuário, não é possível comprovar catálogo, cotação e histórico reais no ambiente publicado. A disponibilidade do feed pode depender de rede, região e validade da sessão. Render Free pode suspender em inatividade.

## Validação temporal do relay

Timestamps Unix em segundos, milissegundos, microssegundos e nanossegundos são normalizados. Campos preço/tempo só são invertidos quando apenas um é um timestamp reconhecível. Uma fonte com diferença de relógio precisa de pelo menos quatro amostras distintas, ao longo de três segundos, avançando no mesmo ritmo do recebimento e com diferença estável. Preços congelados e rajadas antigas não validam o relógio. Saltos reiniciam contexto e sinais. A interface usa horário de recebimento para verificar interrupções; a diferença da fonte fica explícita no rodapé. Os horários originais das velas são preservados. A confirmação de sinais tem horário local separado. Essa validação é temporal, não uma garantia de rentabilidade nem prova independente do relógio da corretora.


### Alertas e placar teórico
O ativo selecionado é acompanhado continuamente. Após fechamento de um padrão aprovado pelos filtros, o primeiro tick da próxima vela registra uma referência teórica e emite alerta CALL verde ou PUT vermelho. Escolha a expiração e pressione Analisar para aplicar aos próximos sinais; sinais existentes mantêm seu prazo original. Não há envio de ordens.

O placar permanece somente na sessão do servidor (máximo 200 sinais; lista visual dos últimos 30). Reconexão, logout ou reinício do serviço descartam o placar. A avaliação compara o preço observado na emissão com o primeiro tick do mesmo ativo entre o vencimento e 2 segundos depois, com intervalo máximo de 3 segundos desde o tick anterior. Dados ausentes ou atrasados resultam em sem conclusão. Não há estimativa de payout ou lucro; o resultado é uma observação teórica, não o resultado oficial de uma operação. Padrões são calculados numericamente dos OHLC (pavios, corpos, rejeição, engolfo e reteste), sem alegar interpretação de emoções reais ou reconhecimento de imagens por IA.
