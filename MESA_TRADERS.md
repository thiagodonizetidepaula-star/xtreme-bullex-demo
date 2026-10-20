# Mesa de Traders · Bullex PRACTICE (experimental)

Este ramo isolado `mesa-traders-demo` contém a Mesa de Traders e preserva a versão anterior do bot no `main`.

## Funcionalidades

- Cinco personagens animados representando agentes de análise: Ana (RSI), Bruno (EMA9/EMA21), Carla (Bollinger), Diego (MACD) e Elisa (Price Action).
- Cada agente vota CALL, PUT ou NEUTRO com base em **candles M1 fechados vindos da corretora**, nunca em preços artificiais.
- O motor só produz entrada quando há consenso de **pelo menos 3 de 5** votos na mesma direção.
- A biblioteca não oficial `bullexapi` do projeto anterior executa ordens **somente em PRACTICE**, nunca em conta real; há validação redundante antes da ordem.
- Payout mínimo, ativo habilitado, uma ordem por vez, sem Martingale, limite diário e stop gain/loss.
- Gráfico de candlesticks, nomes e justificativas dos cinco agentes, placar, histórico da sessão e logs.
- A expiração M1 explícita usa a janela máxima de 2 segundos após fechamento da vela e timeout conservador. Se resposta de ordem for incerta, robô pausa.

**Importante**: esta versão **não foi validada em conta PRACTICE real**. A conectividade, compatibilidade da biblioteca não oficial, aceitação de ordens e resultados dependem da Bullex. Não existe garantia de rentabilidade nem backtest auditado. Nunca use credenciais com operações reais habilitadas para validar esta versão. Opções binárias são de alto risco.

## Serviço Render separado

Este ramo define `render.yaml` com serviço `mesa-traders-bullex-demo`, independente do bot antigo. Em Render, selecione a branch `mesa-traders-demo`, runtime Python 3.11, build `pip install -r requirements.txt && python bootstrap.py`, start `gunicorn app:app --workers 1 --threads 4 --timeout 180 --bind 0.0.0.0:$PORT`. O plano `free` pode suspender/reiniciar, ocasionando perda da sessão.

As variáveis de ambiente obrigatórias são `APP_ACCESS_KEY` (segredo aleatório com pelo menos 16 caracteres) e `SESSION_SECRET` (segredo aleatório). **Não comite credenciais da Bullex**. Defina-as como secrets no Render. No Blueprint, `generateValue: true` cria os valores.

## Como testar

1. Abra o novo endereço do serviço, entre com a chave privada APP_ACCESS_KEY.
2. Na seção Conexão, informe seu login da Bullex, clique **Conectar demo**. O servidor deve confirmar `PRACTICE` e velas antes de liberar o início.
3. Selecione ativo, valor por entrada, payout mínimo, stops e limite; clique **Salvar limites**.
4. Clique **Iniciar robô DEMO** e confira a mesa. O processo opera automaticamente apenas quando todas as condições forem atendidas.
5. Caso conexão falhe (por exemplo, 2FA, incompatibilidade ou timeout), não há ordem. Pare e revise; ordens incertas não são reenviadas.

## Limitações

- Integração com Bullex não oficial e sujeita a mudança; 2FA não implementado.
- Nenhuma persistência durável: reinício do Render pode limpar histórico, configurações e contas autenticadas; não retomar sem revisão.
- Estratégia quantitativa experimental; votos não representam probabilidade calibrada de acerto.
- O servidor de desenvolvimento é monoprocesso; preserve `workers 1` e não execute várias réplicas sem estado compartilhado.
- O comando de stop espera a confirmação de uma operação já enviada antes de concluir.
- Os logs contêm textos técnicos, não senhas.
- A autenticação é feita somente pela chave da aplicação, e os dados da corretora trafegam por HTTPS quando publicados.

## Testes

`python -m unittest discover -s tests -v` (não precisa conectar na corretora para executar os testes do consenso).
