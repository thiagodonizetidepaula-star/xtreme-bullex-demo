# Busca automática sequencial

Após conexão bem-sucedida, automatic=true. O scanner inicia rodadas de até 60s.
Sem candidato, aguarda 3s e tenta outra rodada. Com sinal, encerra a busca e não
inicia nenhuma outra enquanto existir PENDENTE, inclusive entre anúncio e entrada.
Após vencimento +2s busca dados de apuração. WIN/LOSS/EMPATE liberam nova busca.
Se o histórico recebido continuar insuficiente após vencimento +60s, marca SEM DADOS.
Falha de comunicação mantém mensagem de indisponibilidade; não inventa resultado.

Pausar busca automática desabilita retomada, encerra rodada e invalida seu token,
impedindo emissão por uma leitura que estava em andamento. Um sinal já anunciado
continua sendo apurado. Retomar durante um sinal somente habilita a próxima busca.
Desconexão interrompe a análise. Não há envio de ordens.

A atualização não altera o horário de entrada nem adiciona revalidação pré-entrada.
