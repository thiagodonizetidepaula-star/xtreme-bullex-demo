# Xtreme Bullex Demo — versão experimental para Render

Este pacote contém o servidor, painel mobile, estratégia própria e integração com a biblioteca não oficial CassDs/bullexapi. Não é uma cópia do algoritmo Life Changing. Não foi validado com uma conta Bullex; não há promessa de compatibilidade ou taxa de acerto.

## Publicar pelo celular
1. Crie um repositório privado no GitHub e envie os arquivos desta pasta à raiz. Não envie senhas.
2. No Render, escolha New > Blueprint e conecte esse repositório.
3. O render.yaml configura um serviço Free. Confira o plano antes de aplicar.
4. Depois de publicar, abra Environment no serviço e copie APP_ACCESS_KEY. É a chave de acesso ao painel (não é a senha Bullex).
5. Abra o endereço onrender.com do serviço no Chrome do celular e entre com essa chave.
6. Confira o ativo e o gerenciamento. Salve antes de conectar.
7. Digite email e senha da Bullex dentro do app. O servidor só libera o robô depois de confirmar PRACTICE e conseguir ler velas.
8. Clique Iniciar na DEMO. Pare pelo botão Parar. Uma ordem já enviada será acompanhada até o resultado.

## Limitações concretas
- Biblioteca de terceiro, revisão 3178f332db662ea60c570c842362b391aa618c57. Ela é baixada no build; não é redistribuída neste pacote. HTTPS e WebSocket exigem certificados válidos.
- Login com 2FA não implementado nesta versão. Recusas ou bloqueios da corretora interrompem o teste; não há tentativa de contorná-los.
- Estratégias selecionáveis: Retorno e Rejeição v1, Repetição M1 e Retomada de Tendência M1. Apenas velas encerradas; regras experimentais sem alegação de IA ou probabilidade de acerto.
- Uma ordem por vez, mão fixa, sem gale; mercado turbo M1 deve estar aberto e payout confirmado deve atingir o mínimo. Janela máxima de entrada: 5 segundos após fechamento. Não repete uma ordem após resposta incerta.
- Stops são deste processo/dia (Brasília), não incorporam operações feitas em outros apps ou manualmente. Não existe banco durável. Exportar o histórico é recomendado.
- Render Free suspende por inatividade e pode reiniciar. Histórico/configurações desaparecem nesses eventos. Robô nunca reinicia automaticamente nem guarda credenciais em disco. Confira o histórico Bullex antes de reconectar.
- Um único processo Gunicorn e uma conta por serviço. Não aumentar workers/instâncias: cada processo teria seu estado independente.
- Email/senha passam por HTTPS pelo seu servidor Render para autenticação Bullex. Permanecem na memória do processo de integração até desconectar ou encerrar. Não são gravados em logs do app.
- A sessão é protegida por chave privada, cookie HttpOnly/SameSite e token CSRF. A chave deve ser mantida em segredo.

## Testes e execução local opcional
Python 3.11+. Instalar requirements.txt; executar bootstrap.py para baixar a biblioteca; definir APP_ACCESS_KEY com 16 ou mais caracteres; executar python app.py. Testes: python -m unittest discover -s tests -v.

## Repetição M1 — teste comparativo
Selecione a estratégia no gerenciamento com o robô parado; salve e inicie na demo. Retorno e Rejeição v1 continua disponível. Repetição M1 é determinística e experimental, sem relação com regras privadas do Trader Extreme.

Usa somente velas fechadas: três candles da mesma direção, corpo maior que 10% da amplitude, EMA20 confirmada e amplitude de cada vela <= 2 vezes o ATR14 Wilder calculado antes das três velas. O catálogo turbo M1 precisa confirmar ativo aberto e payout >= mínimo configurado, inclusive OTC.

A biblioteca fixada expõe buy_by_raw_expirations, que envia option_type_id=3 e expired explícito. Repetição M1 envia expiração no fechamento da próxima vela (candle do sinal + 120 segundos), somente nos primeiros 2 segundos. Isso é expiração por relógio, cerca de 58–60 segundos desde o envio. Uma guarda valida o relógio também na chamada websocket. Compatibilidade foi verificada no código/protocolo e em mocks; aceitação dessa modalidade pela conta precisa ser validada em demo. Não se substitui por outra expiração se falhar.

Uma operação aberta por vez; deduplicação por ativo/candle usa o histórico da sessão e persiste entre parar/iniciar ou trocar de estratégia. Repetição M1 exige três velas novas após uma entrada. Timeout é incerto e bloqueia o robô, sem reenvio automático.

Stops podem ser desligados explicitamente pelas caixas de seleção. Valores vazios, zero ou inválidos continuam rejeitados; desligar não significa definir zero. Limite de ordens permanece ativo. Win/Loss/empates e lucro líquido só usam resultados confirmados. A tabela de comparação apresenta contagem e payout médio observado, sem inventar resultados.

Continuidade e armazenamento não foram ampliados nesta atualização: o bot executa no servidor enquanto o processo estiver ativo, mas Render Free pode suspender/reiniciar. Histórico, configurações e deduplicação são temporários; exporte antes de publicar/reiniciar. Não existe banco permanente nesta versão. Credenciais não são gravadas.

## Retomada de Tendência M1
Terceira opção experimental, sem substituir as anteriores. EMA20/50 alinhadas e ambas inclinadas na direção da entrada (comparação com três velas atrás); separação mínima 0,25 ATR14. Recuo de exatamente duas ou três velas contrárias seguido de rejeição na tendência. Região EMA20 com tolerância de 0,1 ATR; fechamento a no máximo 0,8 ATR da EMA20. Confirmação com pavio contrário >= metade do corpo e 25% da amplitude, fechamento nos 30% finais na direção da tendência, além da EMA20 e do fechamento anterior. Doji <=10% é descartado. Amplitudes do recuo e confirmação <=1,8 ATR14 Wilder anterior à confirmação. Exige 80 velas M1 fechadas válidas, sem lacunas.
Envia nos primeiros dois segundos, com a mesma guarda de relógio e expiração explícita turbo usada por Repetição M1. Payout >= mínimo configurado; conta demo, mão fixa e gerenciamento existente. Testes automatizados usam fixtures e mocks, não são evidência de rentabilidade. Não há validação ao vivo desta estratégia nem garantia de originalidade ou lucro.

## Scanner com streaming M1
Histórico inicial de 120 candles por ativo, preparado gradualmente fora dos primeiros cinco segundos do minuto. Assinaturas websocket M1 usam o receptor da biblioteca. A cada ciclo o servidor analisa em lote os ativos com candle atual recebido, excluindo a vela aberta. A disponibilidade do stream não garante entrega no prazo: atraso, lacunas e ausência de dados seguem bloqueando entrada. Catálogo é atualizado fora da janela quando já existe catálogo; payout e disponibilidade são verificados novamente antes da ordem. Uma operação por vez, sem aumentar a janela e sem relaxar estratégia. Preparação de muitos ativos pode levar minutos. Contador mede ativo/candle único durante a execução. Testes usam mocks, não comprovam latência ou aceitação reais da corretora.
