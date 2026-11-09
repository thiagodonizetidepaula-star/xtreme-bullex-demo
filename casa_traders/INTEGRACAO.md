# Casa dos Traders — integração Bullix PRACTICE

## Objetivo confirmado
A cena existente da **Casa dos Traders** está em
https://casa-traders-thiago.bnik33887.chatgpt.site.
Ela deve PRESERVAR o projeto visual existente (salas, Thiago, Beatriz,
funcionários, câmeras). Não substitua por uma cena fictícia ou outro app.

A conexão Bullix já existente é a do Xtreme Tiger Clean V1 (serviço
https://xtreme-bot-clean-v1.onrender.com), com validações da corretora,
ordens efetivamente confirmadas em conta **PRACTICE/DEMO**, histórico
persistido em Supabase e travas (saldo, payout, limite, uma ordem por vez).
Não copie login/senha da Bullix para frontend nem salve no ChatGPT Site.
**Nenhuma ordem com dinheiro financeiro está autorizada por esta branch.**

## Arquivos preparados nesta branch
- `casa_traders/bridge.py`: interpreta somente `xtreme_clean_demo_trades`
  onde uma ordem possui ID da corretora, status WIN/LOSS/EMPATE e P&L coerente;
  deduplica por order ID; faz classificação por estratégia e calcula mural;
  registra marcos de metas em P&L agregado confirmado.
- `casa_traders/effects.js`: biblioteca de interface que renderiza o mural
  e gera buzina quando NOVO WIN é confirmado, chime em LOSS, confete + buzina
  ao cruzar uma meta. Só reproduz som após clique do usuário para liberar
  WebAudio. Não toca retrospectivamente ao abrir a página.
- `test_casa_traders.py`: testes de atribuição, exclusão da Beatriz,
  deduplicação, filtros contra resultados não confirmados e marcos reais.
- `clean_v1/app.py` (somente nesta branch): acrescenta
  `GET /api/casa/scoreboard` com autenticação pré-existente e conta escopada.
  A rota é **read-only** e NÃO foi adicionada à branch live `xtreme-clean-v1`.

## Papéis / estratégias (rótulos personalizáveis no site)
| Personagem | Função | Atribuição do resultado |
| --- | --- | --- |
| Thiago | Gerente / trader | Xtreme Sniper + Tendência |
| Trader 1 | Trader | Price Action |
| Trader 2 | Trader | 1R Rompimento + Reteste |
| Trader 3 | Trader | Engolfo de Alta/Baixa |
| Trader 4 | Trader | Rompimentos e falsos rompimentos |
| Beatriz | Contabilidade | Fora da execução, placar e ranking |

Esta é uma distribuição inicial **a validar**, não uma afirmação sobre
o código visual atual. Se o Site tiver outros traders, mapear seus IDs reais.
Quando mais de uma família produzir o mesmo sinal, NÃO inventar um vencedor
nem atribuir a ordem a vários personagens. Quando a estratégia não
for identificável, mostrar como "não atribuída".

## Regra de execução real na PRACTICE
NÃO abrir cinco conexões nem cinco executores concorrentes para a Bullix.
Usar um **único executor**, uma **única sessão**, seleção de estratégia por
personagem, intertravamento de ordens e parada por risco. Cada trader
analisa o mercado de forma lógica; só a estratégia aprovada que originou a
ordem recebe crédito. Não marcar uma ordem como "WIN" antes de settlement.

`clean_v1/automation.py` atualmente aceita estratégias múltiplas, mas o
teste `video_1r` foi feito como experimento isolado e a UI valida seleção
exclusiva. Portanto, **não afirmar que as cinco operam ao mesmo tempo** sem
evoluir/testar o seletor e o motor dedicado na branch da Casa.
Não desativar os bloqueios de risco para acelerar operações.
A meta por trader só conta P&L confirmado de ordens atribuídas a ele,
não cliques no personagem, animações ou sinais sem ordem.

## Feed e confidencialidade
- Sem credenciais no navegador.
- Sem endpoint de saldo/histórico público. A rota em `app.py` requer
  cookie da sessão owner ou pareamento autenticado.
- NÃO adicionar CORS aberto com credenciais, nem expor token secreto no
  JavaScript da cena.
- O ChatGPT Site em outro domínio precisa de **proxy seguro no servidor**
  (autenticado ao backend e escopado à mesma conta) OU integração oficial
  pelo fluxo de consentimento do usuário; nunca capturar senha da Bullix
  no Site. O endpoint atual da branch não oferece token server-to-server:
  esta etapa ainda precisa ser implementada antes da ligação entre domínios.
- O back-end retorna `account_mode=PRACTICE`,
  `source=broker-confirmed-only`, `traders`, `events`, `goal_events`,
  `totals` e `accounting`. IDs de ordens são hash irreversível.
- Usar polling de 3–5 segundos ou push de servidor, com o cuidado de
  iniciar marcadores no primeiro carregamento para evitar festa antiga.

## Comemorações
- WIN confirmado: animação no personagem que operou + buzina curta.
- LOSS confirmado: sinal discreto e chime diferente, sem comemoração.
- Nova meta de lucro DEMO cruzada por settlement confirmado: confete,
  buzinas e destaque no mural; evento idempotente por order ID + target.
- Beatriz continua na rotina contábil da casa, sem clicar em "operar".
- Habilitar áudio no celular com botão, pois autoplay é bloqueado.
- Reduzir efeitos em `prefers-reduced-motion` e no modo economia.

## Status em 09/11/2026
✅ Lógica de ranking + deduplicação + efeitos + testes *adicionados em branch separada*.
✅ Rota server-side privada de leitura adicionada à mesma branch.
✅ Página responsiva `/casa` adicionada à mesma branch para testar o mural autenticado no mesmo domínio; inclui `/assets/casa_effects.js`.
✅ PR em rascunho #21 aberta para revisão.
✅ GitHub Actions: CI da Casa e testes legados de padrões ilustrados passaram nesta branch.
❌ Código da Casa ChatGPT Site NÃO foi modificado nesta conversa.
❌ Bridge NÃO foi publicada na produção; sem conexão cross-origin estabelecida. O Xtreme Tiger tem sessão PRACTICE ativa ou potencialmente ativa conforme logs; publicar provocaria reinício e não deve ocorrer durante operação pendente.
❌ Não houve execução ou confirmação de novas ordens.
❌ Classificação simultânea de todas as estratégias ainda exige motor dedicado
   e teste em conta PRACTICE antes de ativação.

### Como concluir no ChatGPT Sites
No projeto original, abrir **Sites → Casa dos Traders → Editar** e pedir ao
Codex/Work para usar esta branch como referência, importar
`casa_traders/effects.js`, integrar dados confirmados via backend seguro,
preservar todo o ambiente original e primeiro apresentar prévia para revisão.
Não publicar sem teste de autenticação, risco, bloqueio de duplicidades e
mapeamento das estratégias. Conforme o Help Center, alterações em Sites
são feitas no fluxo do editor do Site existente, não pelo serviço Render
do antigo `trader-office-3d` que redireciona para outro aplicativo.

### Teste pré-publicação
- CI verde: `Casa Traders - testes da integração PRACTICE` e `Verify illustrated patterns on clean-v1` no PR #21.
- Não disparar deploy automático do robô em produção enquanto um pedido de compra ou liquidação estiver pendente; verificar usuário/desligamento primeiro.
- Após implantação segura: conectar PRACTICE no Xtreme Tiger original e visitar `https://xtreme-bot-clean-v1.onrender.com/casa` em **mesmo navegador/sessão autenticada** para validar dados do mural. Este URL ainda não está publicado nesta branch.
- Depois utilizar no site original link para mural ou proxy autenticado de integração, sem iframe anônimo expondo resultados.
