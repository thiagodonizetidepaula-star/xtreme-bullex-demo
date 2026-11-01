# Pocket Lens — análise da Pocket Option

Aplicativo separado, somente de leitura. Usa autenticação Supabase do projeto Mesa Trader; nenhuma alteração de tabelas. A sessão do aplicativo usa cookie Secure/HttpOnly/SameSite=Strict, validade máxima de uma hora e inatividade máxima de 20 minutos. A sessão Pocket Option permanece apenas em memória. Nunca colocar credenciais no repositório.

## Executar

Python 3.11+. `pip install --require-hashes -r pocket-chart/requirements.txt`, depois `python pocket-chart/server.py`. Variáveis: `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` e `PORT`. Execute `cd pocket-chart && python -m unittest -v` para verificar.

## Conexão e dados

Entrar com conta existente Mesa Trader. A versão Android em `android/` abre a Pocket Option oficial e observa o pacote de sessão DEMO para encaminhá-lo ao backend próprio, sem cópia manual pelo usuário. O retorno ocorre apenas após autenticação e catálogo confirmados. Esse fluxo requer validação em aparelho real; não constitui API oficial da corretora. No navegador comum, permanece disponível a conexão manual via pacote auth. Os endpoints Socket.IO são não oficiais, herdados do adaptador existente, e podem mudar. Nenhuma conexão ao vivo foi verificada sem sessão do usuário.

Catálogo vem de updateAssets, inclui todos os instrumentos abertos reportados pela sessão, sem lista estática e sem limite a OTC. Um ativo é analisado por vez. Fechados não entram na seleção. Sem catálogo, não inventa ativos.

Gráficos: 5s, 15s, 30s, M1, M2, M3, M5, M10, M15, M30, H1, H4. Velas construídas de ticks da corretora e histórico pedido via loadHistoryPeriod, correlacionado por índice, ativo e geração. Se o histórico de um período não for suportado, aguarda ticks novos. Não preenche lacunas ou gera preços simulados. Velas incompletas não geram sinal. Histórico não emite sinais retroativos.

## Análise

Pivôs estritos com duas velas em cada lado. Suportes e resistências agrupados por tolerância de 0,3 da amplitude média das últimas 14 velas; mínimo de dois toques para gerar sinais. Linha ascendente por dois fundos crescentes e descendente por dois topos decrescentes, descartada após rompimento. Rejeição ou engolfo na região pode emitir BUY/SELL após fechamento, usando somente o contexto anterior. Sinais são experimentais e não possuem taxa de acerto validada.

Horizonte em segundos ou minutos é um parâmetro visual de análise, NÃO catálogo de expirações confirmado pela corretora. Não há envio de ordens, endpoint de operação ou eventos de negociação na allowlist. Sem cotações atuais, novos sinais são suspensos. Sinais anteriores permanecem identificados como anteriores.

## Limitações verificáveis

Testes automatizados cobrem integridade temporal, isolamento de ativos e períodos, auth demonstrativa, bloqueio de eventos de ordens e regras causais. Sem uma sessão autenticada Pocket Option fornecida pelo usuário, não é possível comprovar catálogo, cotação e histórico reais no ambiente publicado. A disponibilidade do feed pode depender de rede, região e validade da sessão. Render Free pode suspender em inatividade.
