# Xtreme Sniper IA — protótipo com candles PRACTICE

Esta primeira versão acrescenta um **bot de sinais informativos** ao projeto existente, sem substituir o app em produção. Não envia ordens.

## Arquivos

- `ai_engine.py`: normaliza candles fechados, agrega M5, compara padrões por k-NN e impede alertas atrasados.
- `ai_server.py`: API somente leitura. Reutiliza `server.py` e `worker.py` do repositório, protege as consultas por chave e confirma a conta PRACTICE.
- `xtreme.html`: interface animada e responsiva com candles recebidos, configurações, aviso de entrada/expiração e placar **simulado por candles**.
- `test_ai_engine.py`: testes offline sem corretora.

## Testar localmente com dados próprios (sem Bullex)

```bash
python -m unittest discover -s asian-signal-ai -p test_ai_engine.py -v
```

## Habilitar a leitura autorizada de candles PRACTICE

**Esta integração ainda não foi validada em uma conta real ou demo nesta atualização.** A biblioteca Bullex é de terceiros e pode não funcionar com a plataforma ou as regras atuais. Não contorne bloqueios de acesso.

No servidor que já tenha os requisitos deste repositório e a biblioteca integrada, configure **variáveis de ambiente** (não coloque segredos em arquivos públicos):

```text
BULLEX_EMAIL=<email usado somente no servidor>
BULLEX_PASSWORD=<senha usada somente no servidor>
XTREME_ACCESS_TOKEN=<chave única e aleatória com pelo menos 16 caracteres>
XTREME_WEB_ORIGIN=https://asian-signal-ai.onrender.com
PORT=10000
```

Inicie com `python asian-signal-ai/ai_server.py` (ou `python ai_server.py` se o diretório de execução for `asian-signal-ai`). É necessário instalar/configurar antes a biblioteca de terceiros usada pelo `worker.py`, conforme o projeto existente.

Hospede `xtreme.html` no endereço configurado em `XTREME_WEB_ORIGIN`. Abra a página, informe a URL da API e a chave de acesso, conecte e selecione o ativo. A chave de acesso NÃO é a senha da corretora. Credenciais Bullex ficam apenas no servidor.

A rota `GET /api/status` informa se a conta PRACTICE e os candles foram confirmados; `GET /api/markets` lista instrumentos; `GET /api/scan?asset=EURUSD&seconds=60` retorna a análise. As duas últimas rotas exigem o cabeçalho `X-Xtreme-Token`. A rota POST é bloqueada.

## Restrições importantes

1. O k-NN é um mecanismo estatístico **experimental**, não uma rede neural treinada e validada. A taxa de padrões similares **não é uma previsão calibrada nem uma promessa de assertividade**.
2. Candles inexistentes, desconectados, em formação, com lacunas, antigos ou sem payout geram **ESPERAR**. O sinal só aparece até 8 segundos após o fechamento da vela de referência; sinais atrasados são bloqueados.
3. M5 é formado com grupos de cinco candles M1 completos. Exige um histórico mínimo de candles.
4. O placar do frontend é **simulado** pela cor do candle, não por ordens na conta da Bullex. Não guarda dados nem resultados entre sessões.
5. O scanner é de **um ativo selecionado por vez**. Todos os ativos, autenticação individual com Supabase, auditoria, limites de API e histórico durável ainda precisam ser implementados antes de vender ou lançar publicamente.
6. Não publique credenciais, cookies, tokens do broker ou um token global para clientes. Esta chave temporária é apenas de teste; **não serve como autenticação multiusuário**.
7. A CVM publicou aviso em 26/06/2025 sobre atuação não autorizada da Digital Smart LLC (BULLEX) no Brasil. Avalie os requisitos legais e o risco antes de oferecer o produto comercialmente.

## Implantação

A branch de desenvolvimento **não é produção**. O serviço de API atualmente executa `server.py`, não `ai_server.py`. Alterar o comando de inicialização e publicar requer revisão e testes de conexão, além de um serviço que permaneça ativo.
